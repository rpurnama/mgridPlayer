"""Main application window: menus, shortcuts, control bar binding, single view vs grid view."""

from __future__ import annotations

import os

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QCursor, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QLabel, QMainWindow, QMenu, QMessageBox, QVBoxLayout, QWidget,
    QWidgetAction,
)

from . import APP_NAME, __version__, icons
from .engine import ASPECT_RATIOS, CROP_RATIOS, vlc_version
from .formats import (
    display_name, expand_inputs, file_dialog_filter, is_url, subtitle_dialog_filter, write_m3u,
)
from .grid_math import PRESETS, auto_dims
from .theme import apply_theme
from .vlc_loader import resolved_lib_path
from .widgets.control_bar import ControlBar, GridPicker
from .widgets.dialogs import (
    SHORTCUTS, GridSizeDialog, OpenUrlDialog, PreferencesDialog, TableDialog, Toast,
)
from .widgets.grid_view import GridView
from .widgets.playlist_panel import PlaylistPanel
from .widgets.video_tile import VideoTile

REPEAT_MODES = ("none", "all", "one")


class MainWindow(QMainWindow):
    def __init__(self, settings, instance=None):
        super().__init__()
        self.settings = settings
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(icons.app_icon())
        self.resize(1280, 780)
        self.setAcceptDrops(True)

        self.master = False
        self.repeat_mode = settings.get("repeat_mode")
        if self.repeat_mode not in REPEAT_MODES:
            self.repeat_mode = "none"
        self.default_volume = settings.get("volume")
        self._bound_conns: list = []
        self._bound_tile: VideoTile | None = None
        self._icon_actions: list[tuple[QAction, str]] = []
        self._fs_state: dict = {}

        # ----- central area ----------------------------------------------------------------
        self.grid = GridView(instance=instance)
        self.grid.audio_follows_focus = settings.get("audio_follows_focus")
        self.grid.show_bars = settings.get("show_tile_bars")
        self.controls = ControlBar()
        central = QWidget()
        lay = QVBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.grid, 1)
        lay.addWidget(self.controls)
        self.setCentralWidget(central)

        self.playlist = PlaylistPanel(self)
        self.addDockWidget(Qt.RightDockWidgetArea, self.playlist)
        self.playlist.hide()
        self.playlist.visibilityChanged.connect(self.controls.playlist_btn.setChecked)

        self.toast = Toast(self)
        self.status_label = QLabel()
        self.statusBar().addPermanentWidget(self.status_label)

        for tile in self.grid.tiles:
            self._setup_tile(tile)
        self.grid.tileCreated.connect(self._setup_tile)
        self.grid.focusChanged.connect(self._bind_tile)
        self.grid.layoutChanged.connect(self._on_layout_changed)
        self.grid.maximizedChanged.connect(lambda _m: self._update_status())

        self._connect_controls()
        self._connect_playlist()
        self._build_menus()

        # fullscreen auto-hide
        self._idle_timer = QTimer(self)
        self._idle_timer.setInterval(250)
        self._idle_timer.timeout.connect(self._fullscreen_tick)
        self._last_cursor = QPoint()
        self._idle_ms = 0

        rows, cols = settings.get("grid_rows"), settings.get("grid_cols")
        self.grid.set_dims(rows, cols)
        self._bind_tile(self.grid.focused)
        self.controls.set_repeat_mode(self.repeat_mode)
        self.controls.set_volume(self.default_volume)
        self._on_layout_changed(self.grid.rows, self.grid.cols)

        geo = settings.raw().value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        state = settings.raw().value("window_state")
        if state is not None:
            self.restoreState(state)
            self.playlist.hide() if not settings.get("playlist_visible") else self.playlist.show()

    # ======================================================================================
    # Tiles / binding
    # ======================================================================================
    def _setup_tile(self, tile: VideoTile):
        c = tile.controller
        c.set_volume(self.default_volume)
        c.loop = self.repeat_mode == "one"
        tile.maximizeRequested.connect(self._on_tile_maximize)
        tile.openRequested.connect(self._open_into_tile)
        tile.openUrlRequested.connect(self._open_url_into_tile)
        tile.contextMenuRequested.connect(self._tile_context_menu)
        tile.errorOccurred.connect(lambda _t, msg: self._notify(msg))
        c.ended.connect(lambda t=tile: self._on_tile_ended(t))
        c.mediaChanged.connect(lambda _m: self._update_status())

    def _bind_tile(self, tile: VideoTile | None):
        for sig, slot in self._bound_conns:
            try:
                sig.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
        self._bound_conns = []
        self._bound_tile = tile
        if tile is None:
            return
        c = tile.controller
        conns = [
            (c.positionChanged, self.controls.set_position),
            (c.durationChanged, self.controls.set_duration),
            (c.stateChanged, self._on_focused_state),
            (c.volumeChanged, self.controls.set_volume),
            (c.muteChanged, self.controls.set_muted),
            (c.rateChanged, self.controls.set_rate),
            (c.mediaChanged, self._on_focused_media),
        ]
        for sig, slot in conns:
            sig.connect(slot)
        self._bound_conns = conns
        length = c.length
        self.controls.set_duration(length)
        self.controls.set_position((c.time / length) if length else 0.0, c.time)
        self.controls.set_volume(c.volume)
        self.controls.set_muted(c.muted)
        self.controls.set_rate(c.rate)
        self._on_focused_state(c.state)
        self._on_focused_media(c.mrl)

    @property
    def focused(self):
        return self.grid.focused.controller if self.grid.focused else None

    def targets(self):
        """Controllers affected by transport actions: all loaded tiles in master mode, else the focused one."""
        if self.master and not self.grid.is_single():
            loaded = [t.controller for t in self.grid.loaded_tiles()]
            return loaded or ([self.focused] if self.focused else [])
        return [self.focused] if self.focused else []

    def _on_focused_state(self, state: str):
        self.controls.set_playing(state == "playing")

    def _on_focused_media(self, mrl: str):
        self.controls.set_media_loaded(bool(mrl))
        self.playlist.set_current(mrl)
        title = display_name(mrl) if mrl else ""
        self.setWindowTitle(f"{title} — {APP_NAME}" if title else APP_NAME)
        self._update_status()

    def _on_layout_changed(self, rows: int, cols: int):
        self.controls.set_grid_label(rows, cols)
        self.grid.set_bars_visible(self.settings.get("show_tile_bars") and not self.grid.is_single())
        self._update_status()

    def _update_status(self):
        g = self.grid
        loaded = len(g.loaded_tiles())
        parts = [f"Grid {g.rows}×{g.cols}", f"{loaded} loaded"]
        if not g.is_single() and g.focused is not None:
            parts.append(f"tile {g.tiles.index(g.focused) + 1} focused")
            if g.maximized is not None:
                parts.append("maximized")
            if self.master:
                parts.append("controlling all")
        self.status_label.setText("  ·  ".join(parts))

    # ======================================================================================
    # Wiring
    # ======================================================================================
    def _connect_controls(self):
        cb = self.controls
        cb.playPauseClicked.connect(self.play_pause)
        cb.stopClicked.connect(lambda: [c.stop() for c in self.targets()])
        cb.prevClicked.connect(lambda: self.playlist_step(-1))
        cb.nextClicked.connect(lambda: self.playlist_step(1))
        cb.jumpClicked.connect(self.jump)
        cb.seekRequested.connect(lambda f: [c.seek(f) for c in self.targets()])
        cb.fullscreenClicked.connect(self.toggle_fullscreen)
        cb.playlistToggled.connect(self.playlist.setVisible)
        cb.gridPicked.connect(self.set_grid)
        cb.gridAutoClicked.connect(self.auto_grid)
        cb.gridCustomClicked.connect(self.custom_grid)
        cb.repeatClicked.connect(self.cycle_repeat)
        cb.masterToggled.connect(self.set_master)
        cb.syncClicked.connect(self.sync_tiles)
        cb.snapshotClicked.connect(self.snapshot)
        cb.rateSelected.connect(lambda r: [c.set_rate(r) for c in self.targets()])
        cb.muteClicked.connect(self.toggle_mute)
        cb.volumeChanged.connect(self.set_volume)

    def _connect_playlist(self):
        pl = self.playlist
        pl.playRequested.connect(self._play_in_focused)
        pl.loadIntoGridRequested.connect(self.open_in_grid)
        pl.addFilesRequested.connect(self._add_files_to_playlist)
        pl.addUrlRequested.connect(self.open_url)
        pl.openPlaylistRequested.connect(self.open_playlist_file)
        pl.savePlaylistRequested.connect(self.save_playlist)

    # ======================================================================================
    # Menus
    # ======================================================================================
    def _act(self, menu: QMenu, text: str, slot=None, shortcut=None, icon: str | None = None,
             checkable: bool = False, checked: bool = False) -> QAction:
        act = QAction(text, self)
        if shortcut:
            seqs = shortcut if isinstance(shortcut, (list, tuple)) else [shortcut]
            act.setShortcuts([QKeySequence(s) for s in seqs])
        if icon:
            act.setIcon(icons.icon(icon))
            self._icon_actions.append((act, icon))
        if checkable:
            act.setCheckable(True)
            act.setChecked(checked)
        if slot is not None:
            act.triggered.connect(slot)
        menu.addAction(act)
        self.addAction(act)  # keep shortcuts alive in fullscreen when the menu bar is hidden
        return act

    def _build_menus(self):
        mb = self.menuBar()

        # ----- Media -----
        m = mb.addMenu("&Media")
        self._act(m, "&Open File(s)…", self.open_files, "Ctrl+O", "folder")
        self._act(m, "Open Files in &Grid…", self.open_files_in_grid, "Ctrl+Shift+G", "grid")
        self._act(m, "Open &Folder…", self.open_folder, "Ctrl+Shift+O", "folder")
        self._act(m, "Open &Network Stream…", self.open_url, "Ctrl+N", "globe")
        self.recent_menu = m.addMenu("Open &Recent Media")
        self.recent_menu.aboutToShow.connect(self._fill_recent)
        m.addSeparator()
        self._act(m, "Open &Playlist…", self.open_playlist_file)
        self._act(m, "&Save Playlist…", self.save_playlist, "Ctrl+S", "save")
        m.addSeparator()
        self._act(m, "&Close Media in Tile", lambda: self.focused and self.focused.clear(), "Ctrl+W", "close")
        self._act(m, "&Quit", self.close, "Ctrl+Q")

        # ----- Playback -----
        m = mb.addMenu("&Playback")
        self._act(m, "&Play / Pause", self.play_pause, "Space", "play")
        self._act(m, "&Stop", lambda: [c.stop() for c in self.targets()], "S", "stop")
        self._act(m, "Pre&vious", lambda: self.playlist_step(-1), "P", "prev")
        self._act(m, "Ne&xt", lambda: self.playlist_step(1), "N", "next")
        m.addSeparator()
        self._act(m, "Jump Forward 10 s", lambda: self.jump(10000), "Right", "forward")
        self._act(m, "Jump Backward 10 s", lambda: self.jump(-10000), "Left", "rewind")
        self._act(m, "Jump Forward 3 s", lambda: self.jump(3000), "Shift+Right")
        self._act(m, "Jump Backward 3 s", lambda: self.jump(-3000), "Shift+Left")
        self._act(m, "Jump Forward 1 min", lambda: self.jump(60000), "Ctrl+Right")
        self._act(m, "Jump Backward 1 min", lambda: self.jump(-60000), "Ctrl+Left")
        self._act(m, "Next &Frame", lambda: [c.next_frame() for c in self.targets()], "E", "frame")
        speed = m.addMenu(icons.icon("speed"), "Spee&d")
        self._act(speed, "&Faster", lambda: [c.step_rate(1) for c in self.targets()], "]")
        self._act(speed, "&Normal Speed", lambda: [c.set_rate(1.0) for c in self.targets()], "=")
        self._act(speed, "&Slower", lambda: [c.step_rate(-1) for c in self.targets()], "[")
        rep = m.addMenu(icons.icon("repeat"), "&Repeat")
        grp = QActionGroup(self)
        self.repeat_actions = {}
        for mode, label in (("none", "Off"), ("all", "Repeat All"), ("one", "Repeat One")):
            a = self._act(rep, label, lambda _=False, md=mode: self.set_repeat(md), checkable=True,
                          checked=mode == self.repeat_mode)
            grp.addAction(a)
            self.repeat_actions[mode] = a
        rep.addSeparator()
        self._act(rep, "Cycle Repeat Mode", self.cycle_repeat, "R")
        self._act(m, "A→B &Loop", self.ab_loop, "L")
        m.addSeparator()
        self.master_action = self._act(m, "Control &All Tiles Together", self.set_master, "A", "link",
                                       checkable=True)
        self.controls.masterToggled.connect(self.master_action.setChecked)
        self._act(m, "S&ync Tiles to Focused", self.sync_tiles, "Y", "sync")
        self._act(m, "Play All Tiles", self.grid.play_all)
        self._act(m, "Pause All Tiles", self.grid.pause_all)
        self._act(m, "Play / Pause All Tiles", self.grid.toggle_all, "Ctrl+Space")
        self._act(m, "Stop All Tiles", self.grid.stop_all)

        # ----- Audio -----
        m = mb.addMenu("&Audio")
        self.audio_track_menu = m.addMenu("Audio &Track")
        self.audio_track_menu.aboutToShow.connect(
            lambda: self._fill_tracks(self.audio_track_menu, "audio"))
        self._act(m, "Cycle Audio Track", lambda: self._notify(self.focused.cycle_audio_track())
                  if self.focused else None, "B")
        m.addSeparator()
        self._act(m, "&Mute", self.toggle_mute, "M", "volume_mute")
        self._act(m, "Volume &Up", lambda: self.step_volume(5), ["Up", "Ctrl+Up"], "volume")
        self._act(m, "Volume &Down", lambda: self.step_volume(-5), ["Down", "Ctrl+Down"], "volume_low")
        m.addSeparator()
        self.follow_action = self._act(m, "Audio &Follows Focused Tile", self.set_audio_follows,
                                       checkable=True, checked=self.grid.audio_follows_focus)
        self._act(m, "Mute All Tiles", lambda: self.grid.set_all_muted(True))
        self._act(m, "Unmute All Tiles", lambda: self.grid.set_all_muted(False))

        # ----- Video -----
        m = mb.addMenu("&Video")
        self._act(m, "&Fullscreen", self.toggle_fullscreen, "F", "fullscreen")
        self._exit_fs_action = QAction(self)
        self._exit_fs_action.setShortcut(QKeySequence("Escape"))
        self._exit_fs_action.triggered.connect(lambda: self.isFullScreen() and self.toggle_fullscreen())
        self.addAction(self._exit_fs_action)
        self._ratio_menu(m, "&Aspect Ratio", ASPECT_RATIOS, lambda c, r: c.set_aspect_ratio(r))
        self._ratio_menu(m, "&Crop", CROP_RATIOS, lambda c, r: c.set_crop(r))
        self.deint_action = self._act(m, "&Deinterlace", lambda on: [c.set_deinterlace(on) for c in self.targets()],
                                      checkable=True)
        m.addSeparator()
        self._act(m, "Take &Snapshot", self.snapshot, "Shift+S", "camera")
        self._act(m, "Media &Information…", self.media_info, "Ctrl+I", "info")

        # ----- Subtitle -----
        m = mb.addMenu("&Subtitle")
        self._act(m, "&Add Subtitle File…", self.add_subtitle, None, "subtitle")
        self.sub_track_menu = m.addMenu("Sub &Track")
        self.sub_track_menu.aboutToShow.connect(lambda: self._fill_tracks(self.sub_track_menu, "spu"))
        self._act(m, "Cycle Subtitle Track", lambda: self._notify(self.focused.cycle_subtitle())
                  if self.focused else None, "V")

        # ----- Grid -----
        m = mb.addMenu("&Grid")
        picker = GridPicker(m)
        wa = QWidgetAction(m)
        wa.setDefaultWidget(picker)
        m.addAction(wa)
        picker.picked.connect(lambda r, c: (m.close(), self.set_grid(r, c)))
        presets = m.addMenu(icons.icon("grid"), "&Presets")
        for r, c in PRESETS:
            self._act(presets, f"{r} × {c}", lambda _=False, r=r, c=c: self.set_grid(r, c))
        self._act(m, "&Single View (1 × 1)", lambda: self.set_grid(1, 1), "Ctrl+0")
        self._act(m, "Auto &Fit to Loaded Videos", self.auto_grid)
        self._act(m, "&Custom Size…", self.custom_grid, "Ctrl+G")
        m.addSeparator()
        self._act(m, "&Maximize / Restore Focused Tile", lambda: self.grid.toggle_maximize(), "Z", "maximize")
        self._act(m, "Focus &Next Tile", lambda: self.grid.focus_step(1), "Tab")
        self._act(m, "Focus &Previous Tile", lambda: self.grid.focus_step(-1), "Shift+Tab")
        for i in range(9):
            a = QAction(self)
            a.setShortcut(QKeySequence(f"Ctrl+{i + 1}"))
            a.triggered.connect(lambda _=False, i=i: self.grid.focus_index(i))
            self.addAction(a)
        m.addSeparator()
        self.bars_action = self._act(m, "Show Tile &Controls", self.set_tile_bars, checkable=True,
                                     checked=self.settings.get("show_tile_bars"))
        self._act(m, "Close &All Media", self.grid.close_all, "Ctrl+Shift+W", "trash")

        # ----- View -----
        m = mb.addMenu("V&iew")
        pl = self.playlist.toggleViewAction()
        pl.setText("&Playlist")
        pl.setShortcut(QKeySequence("Ctrl+L"))
        pl.setIcon(icons.icon("playlist"))
        self._icon_actions.append((pl, "playlist"))
        m.addAction(pl)
        self.addAction(pl)
        self._act(m, "&Status Bar", lambda on: self.statusBar().setVisible(on), checkable=True, checked=True)
        self._act(m, "&Minimal Interface", self.toggle_minimal, "Ctrl+H")
        theme = m.addMenu("&Theme")
        tg = QActionGroup(self)
        for name in ("dark", "light"):
            a = self._act(theme, name.title(), lambda _=False, n=name: self.set_theme(n), checkable=True,
                          checked=self.settings.get("theme") == name)
            tg.addAction(a)
        m.addSeparator()
        self._act(m, "Pr&eferences…", self.preferences, "Ctrl+P", "settings")

        # ----- Help -----
        m = mb.addMenu("&Help")
        self._act(m, "&Keyboard Shortcuts", self.show_shortcuts, "F1", "keyboard")
        self._act(m, "&About", self.about, None, "info")
        self._act(m, "About &Qt", QApplication.aboutQt)

    def _ratio_menu(self, parent: QMenu, title: str, ratios, apply):
        menu = parent.addMenu(title)
        grp = QActionGroup(self)
        for r in ratios:
            a = QAction(r, self, checkable=True)
            a.setChecked(r == "Default")
            a.triggered.connect(lambda _=False, r=r: [apply(c, r) for c in self.targets()])
            grp.addAction(a)
            menu.addAction(a)

    def _fill_tracks(self, menu: QMenu, kind: str):
        menu.clear()
        c = self.focused
        if c is None or not c.has_media:
            menu.addAction("(no media)").setEnabled(False)
            return
        tracks = c.audio_tracks() if kind == "audio" else c.subtitle_tracks()
        current = c.audio_track() if kind == "audio" else c.subtitle_track()
        grp = QActionGroup(menu)
        for tid, name in tracks:
            a = menu.addAction(name or f"Track {tid}")
            a.setCheckable(True)
            a.setChecked(tid == current)
            grp.addAction(a)
            if kind == "audio":
                a.triggered.connect(lambda _=False, t=tid: c.set_audio_track(t))
            else:
                a.triggered.connect(lambda _=False, t=tid: c.set_subtitle_track(t))
        if not tracks:
            menu.addAction("(none)").setEnabled(False)

    def _fill_recent(self):
        self.recent_menu.clear()
        recent = self.settings.recent()
        for item in recent:
            a = self.recent_menu.addAction(display_name(item))
            a.setToolTip(item)
            a.triggered.connect(lambda _=False, i=item: self.handle_open([i]))
        if recent:
            self.recent_menu.addSeparator()
            self.recent_menu.addAction("Clear", self.settings.clear_recent)
        else:
            self.recent_menu.addAction("(empty)").setEnabled(False)

    def _tile_context_menu(self, tile: VideoTile, pos):
        c = tile.controller
        m = QMenu(self)
        m.addAction(icons.icon("folder"), "Open File into This Tile…", lambda: self._open_into_tile(tile))
        m.addAction(icons.icon("globe"), "Open URL into This Tile…", lambda: self._open_url_into_tile(tile))
        if c.has_media:
            m.addSeparator()
            m.addAction(icons.icon("pause" if c.is_playing else "play"),
                        "Pause" if c.is_playing else "Play", c.toggle_play)
            m.addAction(icons.icon("stop"), "Stop", c.stop)
            m.addAction(icons.icon("volume" if c.muted else "volume_mute"),
                        "Unmute" if c.muted else "Mute", c.toggle_mute)
            if not self.grid.is_single():
                m.addAction(icons.icon("maximize"),
                            "Restore" if self.grid.maximized is tile else "Maximize",
                            lambda: self.grid.toggle_maximize(tile))
                m.addAction(icons.icon("sync"), "Sync Other Tiles to This One", self.sync_tiles)
            at = m.addMenu("Audio Track")
            at.aboutToShow.connect(lambda: self._fill_tracks(at, "audio"))
            st = m.addMenu("Subtitle Track")
            st.aboutToShow.connect(lambda: self._fill_tracks(st, "spu"))
            m.addAction(icons.icon("subtitle"), "Add Subtitle File…", self.add_subtitle)
            m.addAction(icons.icon("camera"), "Snapshot", lambda: self._snap([c]))
            m.addAction(icons.icon("info"), "Media Information…", self.media_info)
            m.addSeparator()
            m.addAction(icons.icon("close"), "Close Media", c.clear)
        m.addSeparator()
        m.addAction(icons.icon("fullscreen"), "Exit Fullscreen" if self.isFullScreen() else "Fullscreen",
                    self.toggle_fullscreen)
        m.exec(pos)

    # ======================================================================================
    # Opening media
    # ======================================================================================
    def _remember(self, items):
        for item in reversed(items[:10]):
            self.settings.add_recent(item)

    def handle_open(self, items, into_grid: bool = False):
        """Open items: in single view play the first and queue the rest; in grid view fill free tiles."""
        items = expand_inputs(items)
        if not items:
            return
        self.playlist.add(items)
        self._remember(items)
        if into_grid or not self.grid.is_single():
            grow = into_grid or self.settings.get("grow_grid")
            left = self.grid.add_items(items, grow=grow)
            if left:
                self._notify(f"{len(left)} item(s) did not fit the grid and were added to the playlist")
        else:
            self.grid.focused.open(items[0])
            if len(items) > 1:
                self._notify(f"Playing “{display_name(items[0])}” · {len(items) - 1} more queued")

    def open_in_grid(self, items):
        self.handle_open(items, into_grid=True)

    def _ask_files(self, title="Open Media") -> list[str]:
        files, _ = QFileDialog.getOpenFileNames(self, title, self._last_dir(), file_dialog_filter())
        if files:
            self.settings.set("last_dir", os.path.dirname(files[0]))
        return files

    def _last_dir(self) -> str:
        return self.settings.raw().value("last_dir", os.path.expanduser("~"))

    def open_files(self):
        files = self._ask_files()
        if files:
            self.handle_open(files)

    def open_files_in_grid(self):
        files = self._ask_files("Open Media in Grid")
        if files:
            self.open_in_grid(files)

    def open_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Open Folder", self._last_dir())
        if d:
            self.settings.set("last_dir", d)
            self.handle_open([d])

    def open_url(self):
        dlg = OpenUrlDialog(self.settings.recent(), self)
        if dlg.exec():
            self.handle_open([dlg.url()])

    def _open_into_tile(self, tile: VideoTile):
        files = self._ask_files()
        if not files:
            return
        items = expand_inputs(files)
        if not items:
            return
        self.playlist.add(items)
        self._remember(items)
        tile.open(items[0])
        self.grid.focus_tile(tile)
        if len(items) > 1:
            self.grid.add_items(items[1:], grow=self.settings.get("grow_grid"))

    def _open_url_into_tile(self, tile: VideoTile):
        dlg = OpenUrlDialog(self.settings.recent(), self)
        if dlg.exec():
            self.playlist.add([dlg.url()])
            self._remember([dlg.url()])
            tile.open(dlg.url())
            self.grid.focus_tile(tile)

    def _play_in_focused(self, mrl: str):
        if self.grid.focused is not None:
            self.grid.focused.open(mrl)

    def _add_files_to_playlist(self):
        files = self._ask_files("Add to Playlist")
        if files:
            self.playlist.add(expand_inputs(files))

    def open_playlist_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Playlist", self._last_dir(),
                                              "Playlists (*.m3u *.m3u8 *.pls);;All files (*)")
        if path:
            self.handle_open([path])
            self.playlist.show()

    def save_playlist(self):
        items = self.playlist.items()
        if not items:
            self._notify("Playlist is empty")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save Playlist", os.path.join(self._last_dir(), "playlist.m3u"),
                                              "M3U playlist (*.m3u)")
        if path:
            if not path.lower().endswith((".m3u", ".m3u8")):
                path += ".m3u"
            write_m3u(path, items)
            self._notify(f"Saved playlist ({len(items)} items)")

    def add_subtitle(self):
        c = self.focused
        if c is None or not c.has_media:
            self._notify("Open a video first")
            return
        start = os.path.dirname(c.mrl) if not is_url(c.mrl) else self._last_dir()
        path, _ = QFileDialog.getOpenFileName(self, "Add Subtitle", start, subtitle_dialog_filter())
        if path:
            self._notify("Subtitle added" if c.add_subtitle_file(path) else "Could not load subtitle")

    # ----- drag & drop on the window -------------------------------------------------------
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        from .widgets.video_tile import urls_from_mime

        items = urls_from_mime(event.mimeData())
        if items:
            self.handle_open(items, into_grid=len(expand_inputs(items)) > 1)
            event.acceptProposedAction()

    # ======================================================================================
    # Playback actions
    # ======================================================================================
    def play_pause(self):
        targets = self.targets()
        if not targets:
            return
        if not any(c.has_media for c in targets):
            self.open_files()
            return
        if len(targets) > 1:
            self.grid.toggle_all()
        else:
            targets[0].toggle_play()

    def jump(self, ms: int):
        for c in self.targets():
            c.jump(ms)

    def set_volume(self, v: int):
        self.default_volume = v
        for c in self.targets():
            c.set_volume(v)

    def step_volume(self, delta: int):
        if self.focused:
            v = max(0, min(125, self.focused.volume + delta))
            self.set_volume(v)
            self.controls.set_volume(v)
            self._notify(f"Volume {v}%", 700)

    def toggle_mute(self):
        if not self.focused:
            return
        muted = not self.focused.muted
        for c in self.targets():
            c.set_muted(muted)
        self._notify("Muted" if muted else "Unmuted", 700)

    def set_master(self, on: bool):
        self.master = bool(on)
        self.controls.master_btn.blockSignals(True)
        self.controls.master_btn.setChecked(self.master)
        self.controls.master_btn.blockSignals(False)
        if hasattr(self, "master_action"):
            self.master_action.setChecked(self.master)
        self._notify("Controlling all tiles" if self.master else "Controlling focused tile", 900)
        self._update_status()

    def sync_tiles(self):
        if self.grid.is_single():
            return
        self.grid.sync_to_focused()
        self._notify("Tiles synced to focused tile")

    def ab_loop(self):
        if self.focused and self.focused.has_media:
            self._notify(self.focused.cycle_ab())

    def set_repeat(self, mode: str):
        self.repeat_mode = mode
        for t in self.grid.tiles:
            t.controller.loop = mode == "one"
        self.controls.set_repeat_mode(mode)
        if mode in self.repeat_actions:
            self.repeat_actions[mode].setChecked(True)
        self._notify({"none": "Repeat off", "all": "Repeat all", "one": "Repeat one"}[mode], 800)

    def cycle_repeat(self):
        self.set_repeat(REPEAT_MODES[(REPEAT_MODES.index(self.repeat_mode) + 1) % len(REPEAT_MODES)])

    def playlist_step(self, step: int):
        tile = self.grid.focused
        if tile is None:
            return
        nxt = self.playlist.neighbour(tile.controller.mrl, step, wrap=True)
        if nxt:
            tile.open(nxt)

    def _on_tile_ended(self, tile: VideoTile):
        if self.grid.is_single():
            nxt = self.playlist.neighbour(tile.controller.mrl, 1, wrap=self.repeat_mode == "all")
            if nxt and (len(self.playlist.items()) > 1 or self.repeat_mode == "all"):
                tile.open(nxt)
        elif self.repeat_mode == "all":
            tile.controller.play()

    def snapshot(self):
        self._snap(self.targets())

    def _snap(self, controllers):
        paths = [p for p in (c.snapshot(self.settings.snapshot_dir()) for c in controllers if c.has_media) if p]
        if paths:
            self._notify(f"Snapshot saved: {os.path.basename(paths[0])}" if len(paths) == 1
                         else f"{len(paths)} snapshots saved to {self.settings.snapshot_dir()}")
        else:
            self._notify("Nothing to snapshot")

    def media_info(self):
        c = self.focused
        if c is None or not c.has_media:
            self._notify("No media in the focused tile")
            return
        TableDialog(f"Media Information — {c.title}", c.media_info(), parent=self).exec()

    def set_audio_follows(self, on: bool):
        self.grid.set_audio_follows_focus(on)
        self.settings.set("audio_follows_focus", on)

    # ======================================================================================
    # Grid
    # ======================================================================================
    def set_grid(self, rows: int, cols: int):
        loaded = len(self.grid.loaded_tiles())
        if rows * cols < loaded:
            ans = QMessageBox.question(
                self, "Shrink grid",
                f"{loaded} tiles are playing but the new layout only has {rows * cols}.\n"
                "Extra videos will be closed. Continue?")
            if ans != QMessageBox.Yes:
                return
        self.grid.set_dims(rows, cols)

    def auto_grid(self):
        n = max(1, len(self.grid.loaded_tiles()))
        w, h = max(1, self.grid.width()), max(1, self.grid.height())
        self.set_grid(*auto_dims(n, w / h))

    def custom_grid(self):
        dlg = GridSizeDialog(self.grid.rows, self.grid.cols, self)
        if dlg.exec():
            self.set_grid(*dlg.dims())

    def set_tile_bars(self, on: bool):
        self.settings.set("show_tile_bars", on)
        self._on_layout_changed(self.grid.rows, self.grid.cols)

    def _on_tile_maximize(self, _tile):
        if self.grid.is_single():
            self.toggle_fullscreen()

    # ======================================================================================
    # Fullscreen / minimal / theme
    # ======================================================================================
    def toggle_fullscreen(self):
        if self.isFullScreen():
            self._idle_timer.stop()
            self.grid.unsetCursor()
            self.menuBar().setVisible(self._fs_state.get("menu", True))
            self.statusBar().setVisible(self._fs_state.get("status", True))
            self.playlist.setVisible(self._fs_state.get("playlist", False))
            self.controls.show()
            self.showMaximized() if self._fs_state.get("maximized") else self.showNormal()
            self.controls.set_fullscreen(False)
        else:
            self._fs_state = {"menu": self.menuBar().isVisible(), "status": self.statusBar().isVisible(),
                              "playlist": self.playlist.isVisible(), "maximized": self.isMaximized()}
            self.menuBar().hide()
            self.statusBar().hide()
            self.playlist.hide()
            self.showFullScreen()
            self.controls.set_fullscreen(True)
            self._idle_ms = 0
            self._last_cursor = QCursor.pos()
            self._idle_timer.start()

    def _fullscreen_tick(self):
        pos = QCursor.pos()
        local = self.mapFromGlobal(pos)
        near_bottom = local.y() > self.height() - self.controls.sizeHint().height() - 30
        if pos != self._last_cursor or near_bottom:
            self._last_cursor = pos
            self._idle_ms = 0
            if not self.controls.isVisible():
                self.controls.show()
            self.grid.unsetCursor()
        else:
            self._idle_ms += self._idle_timer.interval()
            if self._idle_ms >= 2500 and self.controls.isVisible():
                self.controls.hide()
                self.grid.setCursor(Qt.BlankCursor)

    def toggle_minimal(self):
        on = self.menuBar().isVisible()
        self.menuBar().setVisible(not on)
        self.statusBar().setVisible(not on)
        self._notify("Minimal interface — press Ctrl+H to restore" if on else "Full interface", 1500)

    def set_theme(self, name: str):
        self.settings.set("theme", name)
        apply_theme(QApplication.instance(), name)
        self.refresh_icons()

    def refresh_icons(self):
        for act, name in self._icon_actions:
            act.setIcon(icons.icon(name))
        self.controls.refresh_icons()
        self.controls.set_playing(self.focused.is_playing if self.focused else False)
        self.playlist.refresh_icons()
        for t in self.grid.tiles:
            t.refresh_icons()

    def preferences(self):
        old_theme = self.settings.get("theme")
        old_hw = self.settings.get("hw_decoding")
        if PreferencesDialog(self.settings, self).exec():
            if self.settings.get("theme") != old_theme:
                self.set_theme(self.settings.get("theme"))
            self.grid.set_audio_follows_focus(self.settings.get("audio_follows_focus"))
            self.follow_action.setChecked(self.settings.get("audio_follows_focus"))
            self.bars_action.setChecked(self.settings.get("show_tile_bars"))
            self._on_layout_changed(self.grid.rows, self.grid.cols)
            if self.settings.get("hw_decoding") != old_hw:
                self._notify("Hardware decoding change applies after restart", 2500)

    def show_shortcuts(self):
        TableDialog("Keyboard Shortcuts", SHORTCUTS, headers=("Keys", "Action"), parent=self).exec()

    def about(self):
        QMessageBox.about(
            self, f"About {APP_NAME}",
            f"<h3>{APP_NAME} {__version__}</h3>"
            "<p>A VLC-style media player that can play many videos at once in a grid.</p>"
            f"<p>Engine: libVLC {vlc_version()}<br>Library: {resolved_lib_path or 'system'}</p>"
            "<p>Built with Qt for Python (PySide6) and python-vlc.</p>")

    # ======================================================================================
    # Misc
    # ======================================================================================
    def _notify(self, text: str, ms: int = 1800):
        if not text:
            return
        self.statusBar().showMessage(text, max(ms, 3000))
        self.toast.show_message(text, ms)

    def changeEvent(self, event):
        if event.type() == QEvent.WindowStateChange:
            self.controls.set_fullscreen(self.isFullScreen())
        super().changeEvent(event)

    def closeEvent(self, event):
        s = self.settings
        if self.isFullScreen():
            self.toggle_fullscreen()
        s.set("geometry", self.saveGeometry())
        s.set("window_state", self.saveState())
        s.set("playlist_visible", self.playlist.isVisible())
        s.set("volume", self.default_volume)
        s.set("grid_rows", self.grid.rows)
        s.set("grid_cols", self.grid.cols)
        s.set("repeat_mode", self.repeat_mode)
        self.toast.close()
        self.grid.release()
        super().closeEvent(event)
