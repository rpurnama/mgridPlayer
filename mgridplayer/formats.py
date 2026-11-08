"""Supported media formats and helpers for classifying user input."""

from __future__ import annotations

import os
import re
from urllib.parse import unquote, urlparse

VIDEO_EXTS = (
    "mp4", "mkv", "avi", "mov", "wmv", "flv", "webm", "m4v", "mpg", "mpeg", "mpe",
    "ts", "mts", "m2ts", "3gp", "3g2", "ogv", "vob", "mxf", "rm", "rmvb", "asf",
    "divx", "xvid", "f4v", "dv", "y4m", "nut", "hevc", "h264", "h265", "av1",
)
AUDIO_EXTS = (
    "mp3", "flac", "wav", "aac", "ogg", "oga", "m4a", "opus", "wma", "ac3", "dts",
    "mka", "aiff", "aif", "ape", "wv", "mid", "midi",
)
PLAYLIST_EXTS = ("m3u", "m3u8", "pls")
SUBTITLE_EXTS = ("srt", "ass", "ssa", "sub", "vtt", "idx", "smi", "txt")

URL_SCHEMES = (
    "http", "https", "rtsp", "rtmp", "rtmps", "rtp", "udp", "mms", "mmsh", "ftp",
    "sftp", "smb", "dvd", "bluray", "file", "srt", "hls",
)

_SCHEME_RE = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.-]*)://")


def _ext(path: str) -> str:
    return os.path.splitext(path)[1].lower().lstrip(".")


def is_url(text: str) -> bool:
    m = _SCHEME_RE.match(text.strip())
    return bool(m) and m.group(1).lower() in URL_SCHEMES


def is_media_file(path: str) -> bool:
    return _ext(path) in VIDEO_EXTS + AUDIO_EXTS


def is_audio_file(path: str) -> bool:
    return _ext(path) in AUDIO_EXTS


def is_playlist_file(path: str) -> bool:
    """True for local playlists we expand ourselves (not HLS manifests)."""
    if _ext(path) not in PLAYLIST_EXTS or not os.path.isfile(path):
        return False
    if _ext(path) == "m3u8":
        try:
            with open(path, encoding="utf-8", errors="ignore") as fh:
                head = fh.read(4096)
        except OSError:
            return False
        return "#EXT-X-" not in head  # HLS manifests are played directly by VLC
    return True


def is_subtitle_file(path: str) -> bool:
    return _ext(path) in SUBTITLE_EXTS


def display_name(mrl: str) -> str:
    """Human-friendly name for a path or URL."""
    if is_url(mrl):
        parsed = urlparse(mrl)
        if parsed.scheme == "file":
            return os.path.basename(unquote(parsed.path)) or mrl
        tail = os.path.basename(parsed.path.rstrip("/"))
        return unquote(tail) if tail else parsed.netloc or mrl
    return os.path.basename(mrl) or mrl


def _patterns(exts) -> str:
    return " ".join(f"*.{e}" for e in exts) + " " + " ".join(f"*.{e.upper()}" for e in exts)


def file_dialog_filter() -> str:
    return ";;".join([
        f"Media files ({_patterns(VIDEO_EXTS + AUDIO_EXTS + PLAYLIST_EXTS)})",
        f"Video files ({_patterns(VIDEO_EXTS)})",
        f"Audio files ({_patterns(AUDIO_EXTS)})",
        f"Playlists ({_patterns(PLAYLIST_EXTS)})",
        "All files (*)",
    ])


def subtitle_dialog_filter() -> str:
    return f"Subtitles ({_patterns(SUBTITLE_EXTS)});;All files (*)"


def parse_playlist(path: str) -> list[str]:
    """Expand a local .m3u/.m3u8/.pls playlist into a list of paths/URLs."""
    base = os.path.dirname(os.path.abspath(path))
    entries: list[str] = []
    try:
        with open(path, encoding="utf-8-sig", errors="ignore") as fh:
            lines = [ln.strip() for ln in fh]
    except OSError:
        return entries

    if _ext(path) == "pls":
        raw = [ln.split("=", 1)[1].strip() for ln in lines
               if re.match(r"(?i)^file\d+=", ln)]
    else:
        raw = [ln for ln in lines if ln and not ln.startswith("#")]

    for item in raw:
        if is_url(item):
            entries.append(item)
        else:
            item = os.path.expanduser(item.replace("\\", os.sep) if os.sep == "/" else item)
            entries.append(os.path.normpath(item if os.path.isabs(item) else os.path.join(base, item)))
    return entries


def expand_inputs(items) -> list[str]:
    """Turn files / folders / playlists / URLs into a flat list of playable items."""
    out: list[str] = []
    for item in items:
        if not item:
            continue
        if is_url(item):
            parsed = urlparse(item)
            if parsed.scheme == "file":
                out.extend(expand_inputs([unquote(parsed.path)]))
            else:
                out.append(item)
        elif os.path.isdir(item):
            for name in sorted(os.listdir(item), key=str.lower):
                full = os.path.join(item, name)
                if os.path.isfile(full) and is_media_file(full):
                    out.append(full)
        elif is_playlist_file(item):
            out.extend(parse_playlist(item))
        else:
            out.append(item)
    return out


def write_m3u(path: str, items) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("#EXTM3U\n")
        for item in items:
            fh.write(f"#EXTINF:-1,{display_name(item)}\n{item}\n")
