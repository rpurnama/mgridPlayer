"""Playback engine: a shared libVLC instance and a Qt-friendly per-tile player controller."""

from __future__ import annotations

import os
import sys
import time

from PySide6.QtCore import QObject, Qt, QTimer, Signal

from .formats import display_name, is_audio_file, is_url
from .vlc_loader import load_vlc

vlc = load_vlc()

RATE_STEPS = (0.25, 0.5, 0.67, 0.75, 0.8, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0)
ASPECT_RATIOS = ("Default", "16:9", "4:3", "1:1", "16:10", "2.21:1", "2.35:1", "2.39:1", "5:4")
CROP_RATIOS = ("Default", "16:9", "4:3", "1:1", "16:10", "2.21:1", "2.35:1", "2.39:1", "5:4")

_instance = None
_visual_instance = None
_instance_args: list[str] = []
VISUAL_ARGS = ["--audio-visual=visual", "--effect-list=spectrum"]


def create_instance(hw_decoding: bool = True, extra_args=None):
    """Create (once) the libVLC instance shared by every player."""
    global _instance, _instance_args
    if _instance is not None:
        return _instance
    args = [
        "--quiet",
        "--no-video-title-show",
        "--no-snapshot-preview",
        "--no-stats",
        "--avcodec-hw=" + ("any" if hw_decoding else "none"),
    ]
    if extra_args:
        args.extend(extra_args)
    _instance_args = args
    _instance = vlc.Instance(args)
    if _instance is None:
        raise RuntimeError("libVLC failed to initialise with arguments: " + " ".join(args))
    return _instance


def get_instance():
    return _instance if _instance is not None else create_instance()


def get_visual_instance():
    """Second instance with an audio visualizer, used for audio-only media.

    libVLC applies --audio-visual per audio output, so it can't be enabled per media;
    enabling it on the main instance would pop up a spectrum window for every video.
    """
    global _visual_instance
    if _visual_instance is None:
        get_instance()
        _visual_instance = vlc.Instance(_instance_args + VISUAL_ARGS)
    return _visual_instance


def vlc_version() -> str:
    return vlc.libvlc_get_version().decode(errors="ignore")


def _decode(value) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value) if value is not None else ""


def to_mrl(path_or_url: str) -> str:
    if is_url(path_or_url):
        return path_or_url
    return os.path.abspath(os.path.expanduser(path_or_url))


class PlayerController(QObject):
    """Wraps one ``vlc.MediaPlayer`` and exposes its state through Qt signals.

    libVLC fires events on its own threads; they are funnelled through ``_vlcEvent``
    with a queued connection so all handling (and all libVLC calls) happen on the GUI thread.
    """

    positionChanged = Signal(float, int)   # fraction 0..1, time ms
    durationChanged = Signal(int)          # ms
    stateChanged = Signal(str)             # "idle" | "opening" | "playing" | "paused" | "stopped" | "ended" | "error"
    mediaChanged = Signal(str)             # mrl ("" when cleared)
    volumeChanged = Signal(int)
    muteChanged = Signal(bool)
    rateChanged = Signal(float)
    tracksChanged = Signal()
    abLoopChanged = Signal(int, int)       # A ms, B ms (-1 when unset)
    ended = Signal()
    errorOccurred = Signal(str)

    _vlcEvent = Signal(int, int)  # player generation, event type

    _EVENTS = {
        "MediaPlayerOpening": "opening",
        "MediaPlayerPlaying": "playing",
        "MediaPlayerPaused": "paused",
        "MediaPlayerStopped": "stopped",
        "MediaPlayerEndReached": "ended",
        "MediaPlayerEncounteredError": "error",
        "MediaPlayerLengthChanged": "length",
        "MediaPlayerESAdded": "tracks",
        "MediaPlayerESDeleted": "tracks",
        "MediaPlayerVout": "tracks",
    }

    def __init__(self, parent=None, instance=None):
        super().__init__(parent)
        self._fixed_instance = instance
        self._vlc_instance = instance or get_instance()
        self._visual = False
        self._generation = 0
        self.player = None
        self.mrl = ""
        self.state = "idle"
        self.loop = False
        self._volume = 100
        self._user_muted = False
        self._focus_muted = False
        self._rate = 1.0
        self._length = 0
        self._ab = [-1, -1]
        self._win_id = None
        self._released = False
        self._pending_seek: float | None = None

        self._event_ids = {int(getattr(vlc.EventType, n).value): k for n, k in self._EVENTS.items()}
        self._vlcEvent.connect(self._handle_event, Qt.QueuedConnection)
        self._create_player()

        self._poll = QTimer(self)
        self._poll.setInterval(200)
        self._poll.timeout.connect(self._tick)

    # ----- player lifecycle ----------------------------------------------------------------
    def _create_player(self):
        self._generation += 1
        self.player = self._vlc_instance.media_player_new()
        self.player.video_set_mouse_input(False)
        self.player.video_set_key_input(False)
        em = self.player.event_manager()
        for name in self._EVENTS:
            em.event_attach(getattr(vlc.EventType, name), self._on_vlc_event, self._generation)
        if self._win_id is not None:
            self.set_window(self._win_id)

    def _destroy_player(self):
        if self.player is None:
            return
        try:
            em = self.player.event_manager()
            for name in self._EVENTS:
                em.event_detach(getattr(vlc.EventType, name))
        except Exception:  # noqa: BLE001
            pass
        self.player.stop()
        self.player.release()
        self.player = None

    def _use_visual(self, visual: bool):
        """Switch to a player from the visualizer instance (audio files) or the normal one."""
        if self._fixed_instance is not None or visual == self._visual:
            return
        self._poll.stop()
        self._destroy_player()
        self._visual = visual
        self._vlc_instance = get_visual_instance() if visual else get_instance()
        self._create_player()

    # ----- libVLC thread -> GUI thread -----------------------------------------------------
    def _on_vlc_event(self, event, generation):
        # Runs on a libVLC thread: never call libVLC here, just hand off.
        try:
            self._vlcEvent.emit(generation, int(event.type.value))
        except RuntimeError:
            pass  # QObject already deleted

    def _handle_event(self, generation: int, etype: int):
        if self._released or generation != self._generation:
            return  # stale event from a player that has been replaced
        key = self._event_ids.get(etype)
        if key == "length":
            self._length = max(0, self.player.get_length())
            self.durationChanged.emit(self._length)
        elif key == "tracks":
            self.tracksChanged.emit()
            self._fix_child_windows()
        elif key == "playing":
            self._apply_audio()
            if self._pending_seek is not None:
                self.player.set_position(self._pending_seek)
                self._pending_seek = None
            self._set_state("playing")
            self._poll.start()
            length = self.player.get_length()
            if length > 0 and length != self._length:
                self._length = length
                self.durationChanged.emit(length)
        elif key == "ended":
            self._poll.stop()
            self.positionChanged.emit(1.0, self._length)
            if self.loop and self.mrl:
                self._restart()
            else:
                self._set_state("ended")
                self.ended.emit()
        elif key == "error":
            self._poll.stop()
            self._set_state("error")
            self.errorOccurred.emit(f"Cannot play “{display_name(self.mrl)}”.")
        elif key in ("paused", "stopped", "opening"):
            if key != "opening":
                self._poll.stop()
            self._set_state(key)
            if key == "stopped":
                self.positionChanged.emit(0.0, 0)

    def _set_state(self, state: str):
        if state != self.state:
            self.state = state
            self.stateChanged.emit(state)

    def _tick(self):
        if self._released:
            return
        t = self.player.get_time()
        pos = self.player.get_position()
        a, b = self._ab
        if a >= 0 and b > a and t >= b:
            self.player.set_time(a)
            t = a
        self.positionChanged.emit(max(0.0, pos), max(0, t))

    def _restart(self):
        media = self.player.get_media()
        if media is not None:
            self.player.set_media(media)
        self.player.play()

    # ----- window embedding ----------------------------------------------------------------
    def set_window(self, win_id: int):
        self._win_id = int(win_id)
        if sys.platform.startswith("win"):
            self.player.set_hwnd(self._win_id)
        elif sys.platform == "darwin":
            self.player.set_nsobject(self._win_id)
        else:
            self.player.set_xwindow(self._win_id)

    def _fix_child_windows(self):
        """On Windows libVLC's child window swallows mouse clicks; disable it so the parent gets them."""
        if not sys.platform.startswith("win") or not self._win_id:
            return
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

            def disable(hwnd, _lparam):
                user32.EnableWindow(hwnd, False)
                return True

            user32.EnumChildWindows(wintypes.HWND(self._win_id), proc_type(disable), 0)
        except Exception:  # noqa: BLE001 - best effort only
            pass

    # ----- media ---------------------------------------------------------------------------
    def open(self, path_or_url: str, play: bool = True, start_ms: int = 0):
        mrl = to_mrl(path_or_url)
        self._use_visual(is_audio_file(mrl))
        media = self._vlc_instance.media_new(mrl) if is_url(mrl) else self._vlc_instance.media_new_path(mrl)
        if start_ms > 0:
            media.add_option(f":start-time={start_ms / 1000:.3f}")
        self.player.set_media(media)
        media.release()
        self.mrl = mrl
        self._length = 0
        self._ab = [-1, -1]
        self.abLoopChanged.emit(-1, -1)
        self.mediaChanged.emit(mrl)
        self.durationChanged.emit(0)
        self.positionChanged.emit(0.0, 0)
        if play:
            self.play()

    def clear(self):
        self.stop()
        self.player.set_media(None)
        self.mrl = ""
        self._length = 0
        self._set_state("idle")
        self.mediaChanged.emit("")
        self.durationChanged.emit(0)

    @property
    def has_media(self) -> bool:
        return bool(self.mrl)

    @property
    def title(self) -> str:
        return display_name(self.mrl) if self.mrl else ""

    # ----- transport -----------------------------------------------------------------------
    def play(self):
        if not self.mrl:
            return
        if self.state in ("ended", "error"):
            self._restart()
        else:
            self.player.play()

    def pause(self):
        if self.player.is_playing():
            self.player.set_pause(1)

    def toggle_play(self):
        if self.player.is_playing():
            self.pause()
        else:
            self.play()

    def stop(self):
        self._poll.stop()
        self.player.stop()

    @property
    def is_playing(self) -> bool:
        return bool(self.player.is_playing())

    @property
    def length(self) -> int:
        return self._length if self._length > 0 else max(0, self.player.get_length())

    @property
    def time(self) -> int:
        return max(0, self.player.get_time())

    def seek(self, fraction: float):
        if not self.mrl:
            return
        fraction = min(max(fraction, 0.0), 0.999)
        if self.state in ("ended", "stopped", "error"):
            self._pending_seek = fraction  # applied once playback has restarted
            self._restart()
        else:
            self.player.set_position(fraction)
        self.positionChanged.emit(fraction, int(fraction * self.length))

    def set_time(self, ms: int):
        if not self.mrl:
            return
        length = self.length
        if length > 0:
            ms = min(max(0, ms), length - 250)
        self.player.set_time(max(0, int(ms)))
        if length > 0:
            self.positionChanged.emit(ms / length, ms)

    def jump(self, delta_ms: int):
        self.set_time(self.time + delta_ms)

    def next_frame(self):
        if self.mrl:
            self.player.next_frame()

    # ----- audio ---------------------------------------------------------------------------
    def _apply_audio(self):
        self.player.audio_set_mute(self._user_muted or self._focus_muted)
        self.player.audio_set_volume(self._volume)
        if abs(self.player.get_rate() - self._rate) > 1e-3:
            self.player.set_rate(self._rate)

    @property
    def volume(self) -> int:
        return self._volume

    def set_volume(self, vol: int):
        vol = int(min(max(vol, 0), 200))
        self._volume = vol
        self.player.audio_set_volume(vol)
        if vol > 0 and self._user_muted:
            self.set_muted(False)
        self.volumeChanged.emit(vol)

    @property
    def muted(self) -> bool:
        return self._user_muted

    def set_muted(self, muted: bool):
        self._user_muted = bool(muted)
        self.player.audio_set_mute(self._user_muted or self._focus_muted)
        self.muteChanged.emit(self._user_muted)

    def toggle_mute(self):
        self.set_muted(not self._user_muted)

    @property
    def focus_muted(self) -> bool:
        return self._focus_muted

    def set_focus_muted(self, muted: bool):
        """Mute caused by 'audio follows focus' - separate from the user's own mute."""
        self._focus_muted = bool(muted)
        self.player.audio_set_mute(self._user_muted or self._focus_muted)

    def audio_tracks(self) -> list[tuple[int, str]]:
        return [(i, _decode(n)) for i, n in (self.player.audio_get_track_description() or [])]

    def audio_track(self) -> int:
        return self.player.audio_get_track()

    def set_audio_track(self, track_id: int):
        self.player.audio_set_track(track_id)
        self.tracksChanged.emit()

    # ----- speed ---------------------------------------------------------------------------
    @property
    def rate(self) -> float:
        return self._rate

    def set_rate(self, rate: float):
        self._rate = float(min(max(rate, 0.25), 4.0))
        self.player.set_rate(self._rate)
        self.rateChanged.emit(self._rate)

    def step_rate(self, direction: int):
        cur = self._rate
        if direction > 0:
            nxt = next((r for r in RATE_STEPS if r > cur + 1e-3), RATE_STEPS[-1])
        else:
            nxt = next((r for r in reversed(RATE_STEPS) if r < cur - 1e-3), RATE_STEPS[0])
        self.set_rate(nxt)

    # ----- A-B loop ------------------------------------------------------------------------
    def cycle_ab(self) -> str:
        """First call marks A, second marks B, third clears. Returns a status message."""
        a, b = self._ab
        t = self.time
        if a < 0:
            self._ab = [t, -1]
            msg = f"A-B loop: A set at {format_ms(t)}"
        elif b < 0 and t > a:
            self._ab = [a, t]
            msg = f"A-B loop: {format_ms(a)} → {format_ms(t)}"
        else:
            self._ab = [-1, -1]
            msg = "A-B loop cleared"
        self.abLoopChanged.emit(*self._ab)
        return msg

    @property
    def ab_loop(self) -> tuple[int, int]:
        return tuple(self._ab)

    # ----- subtitles -----------------------------------------------------------------------
    def subtitle_tracks(self) -> list[tuple[int, str]]:
        return [(i, _decode(n)) for i, n in (self.player.video_get_spu_description() or [])]

    def subtitle_track(self) -> int:
        return self.player.video_get_spu()

    def set_subtitle_track(self, track_id: int):
        self.player.video_set_spu(track_id)
        self.tracksChanged.emit()

    def add_subtitle_file(self, path: str) -> bool:
        uri = path if is_url(path) else "file://" + _path_to_uri(os.path.abspath(path))
        ok = self.player.add_slave(vlc.MediaSlaveType.subtitle, uri, True) == 0
        self.tracksChanged.emit()
        return ok

    @staticmethod
    def _cycle(tracks, current) -> int | None:
        if not tracks:
            return None
        ids = [t[0] for t in tracks]
        idx = ids.index(current) if current in ids else -1
        return ids[(idx + 1) % len(ids)]

    def cycle_subtitle(self) -> str:
        tracks = self.subtitle_tracks()
        nxt = self._cycle(tracks, self.subtitle_track())
        if nxt is None:
            return "No subtitles"
        self.set_subtitle_track(nxt)
        return "Subtitle: " + dict(tracks)[nxt]

    def cycle_audio_track(self) -> str:
        tracks = [t for t in self.audio_tracks() if t[0] != -1]
        nxt = self._cycle(tracks, self.audio_track())
        if nxt is None:
            return "No audio tracks"
        self.set_audio_track(nxt)
        return "Audio track: " + dict(tracks)[nxt]

    # ----- video ---------------------------------------------------------------------------
    def set_aspect_ratio(self, ratio: str | None):
        self.player.video_set_aspect_ratio(None if not ratio or ratio == "Default" else ratio)

    def set_crop(self, ratio: str | None):
        self.player.video_set_crop_geometry(None if not ratio or ratio == "Default" else ratio)

    def set_deinterlace(self, enabled: bool):
        self.player.video_set_deinterlace("yadif" if enabled else None)

    def snapshot(self, directory: str) -> str | None:
        if not self.mrl:
            return None
        os.makedirs(directory, exist_ok=True)
        stem = os.path.splitext(self.title)[0] or "snapshot"
        stem = "".join(c if c.isalnum() or c in "-_ ." else "_" for c in stem)[:60]
        path = os.path.join(directory, f"{stem}_{time.strftime('%Y%m%d-%H%M%S')}_{self.time // 1000}s.png")
        return path if self.player.video_take_snapshot(0, path, 0, 0) == 0 else None

    def media_info(self) -> list[tuple[str, str]]:
        info: list[tuple[str, str]] = []
        if not self.mrl:
            return info
        info.append(("Location", self.mrl))
        media = self.player.get_media()
        if media is not None:
            for key in ("Title", "Artist", "Album", "Date", "Genre", "EncodedBy"):
                val = media.get_meta(getattr(vlc.Meta, key))
                if val and key != "Title" or (key == "Title" and val and val != self.title):
                    info.append((key, _decode(val)))
        info.append(("Duration", format_ms(self.length)))
        w, h = self.player.video_get_size(0) or (0, 0)
        if w and h:
            info.append(("Resolution", f"{w} × {h}"))
        fps = self.player.get_fps()
        if fps:
            info.append(("Frame rate", f"{fps:.3f} fps"))
        # Note: Media.tracks_get() can crash python-vlc, so use the player's track descriptions.
        for label, tracks in (("Video tracks", self.player.video_get_track_description()),
                              ("Audio tracks", self.player.audio_get_track_description()),
                              ("Subtitle tracks", self.player.video_get_spu_description())):
            names = [_decode(n) for i, n in (tracks or []) if i != -1]
            if names:
                info.append((label, ", ".join(names)))
        return info

    # ----- teardown ------------------------------------------------------------------------
    def release(self):
        if self._released:
            return
        self._poll.stop()
        self._released = True
        self._destroy_player()


def _path_to_uri(path: str) -> str:
    from urllib.parse import quote

    path = path.replace("\\", "/")
    if not path.startswith("/"):
        path = "/" + path  # Windows drive letter
    return quote(path)


def format_ms(ms: int) -> str:
    if ms is None or ms < 0:
        return "--:--"
    s = int(ms // 1000)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"
