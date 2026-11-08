"""Persistent user preferences (QSettings)."""

from __future__ import annotations

import os

from PySide6.QtCore import QSettings, QStandardPaths

from . import APP_NAME

MAX_RECENT = 10

DEFAULTS = {
    "theme": "dark",
    "hw_decoding": True,
    "audio_follows_focus": True,
    "show_tile_bars": True,
    "grow_grid": True,
    "volume": 80,
    "grid_rows": 1,
    "grid_cols": 1,
    "repeat_mode": "none",       # none | one | all
    "snapshot_dir": "",
    "recent": [],
    "playlist_visible": False,
}


class Settings:
    def __init__(self):
        self._s = QSettings(APP_NAME, APP_NAME)

    def get(self, key: str):
        default = DEFAULTS.get(key)
        val = self._s.value(key, default)
        if isinstance(default, bool):
            return val if isinstance(val, bool) else str(val).lower() in ("1", "true", "yes")
        if isinstance(default, int):
            try:
                return int(val)
            except (TypeError, ValueError):
                return default
        if isinstance(default, list):
            if val is None:
                return []
            return [val] if isinstance(val, str) else list(val)
        return val

    def set(self, key: str, value):
        self._s.setValue(key, value)

    def raw(self) -> QSettings:
        return self._s

    # ----- recent files --------------------------------------------------------------------
    def recent(self) -> list[str]:
        return [r for r in self.get("recent") if r]

    def add_recent(self, item: str):
        items = [r for r in self.recent() if r != item]
        items.insert(0, item)
        self.set("recent", items[:MAX_RECENT])

    def clear_recent(self):
        self.set("recent", [])

    def snapshot_dir(self) -> str:
        d = self.get("snapshot_dir")
        if d:
            return d
        pictures = QStandardPaths.writableLocation(QStandardPaths.PicturesLocation) or os.path.expanduser("~")
        return os.path.join(pictures, APP_NAME)
