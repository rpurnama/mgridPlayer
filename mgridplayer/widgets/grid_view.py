"""The multi-video grid: owns the tiles, their layout, focus, maximize and master controls."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGridLayout, QWidget

from ..grid_math import MAX_DIM, compact_order, grow_to_fit
from .video_tile import VideoTile, urls_from_mime


class GridView(QWidget):
    focusChanged = Signal(object)          # VideoTile
    layoutChanged = Signal(int, int)       # rows, cols
    tileCreated = Signal(object)
    maximizedChanged = Signal(bool)

    def __init__(self, parent=None, instance=None):
        super().__init__(parent)
        self.setObjectName("GridView")
        self.setAcceptDrops(True)
        self._instance = instance
        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(4)
        self.tiles: list[VideoTile] = []
        self.rows = 0
        self.cols = 0
        self.focused: VideoTile | None = None
        self.maximized: VideoTile | None = None
        self.audio_follows_focus = True
        self.show_bars = True
        self.set_dims(1, 1)

    # ----- layout --------------------------------------------------------------------------
    def set_dims(self, rows: int, cols: int):
        rows = max(1, min(MAX_DIM, int(rows)))
        cols = max(1, min(MAX_DIM, int(cols)))
        capacity = rows * cols
        if len(self.tiles) > capacity:
            keep = set(compact_order([t.has_media for t in self.tiles], capacity))
            for i in sorted(set(range(len(self.tiles))) - keep, reverse=True):
                tile = self.tiles.pop(i)
                if tile is self.maximized:
                    self.maximized = None
                self._layout.removeWidget(tile)
                tile.release()
                tile.deleteLater()
        while len(self.tiles) < capacity:
            self.tiles.append(self._create_tile())
        self.rows, self.cols = rows, cols
        self._relayout()
        if self.focused not in self.tiles:
            self.focus_tile(self.tiles[0])
        else:
            self.apply_audio_focus()
        self.layoutChanged.emit(rows, cols)

    def _create_tile(self) -> VideoTile:
        tile = VideoTile(self, instance=self._instance)
        tile.set_bar_visible(self.show_bars)
        tile.focusRequested.connect(self.focus_tile)
        tile.maximizeRequested.connect(self.toggle_maximize)
        tile.swapRequested.connect(self._on_swap)
        tile.filesDropped.connect(self._on_tile_drop)
        self.tileCreated.emit(tile)
        return tile

    def _relayout(self):
        for tile in self.tiles:
            self._layout.removeWidget(tile)
        for r in range(MAX_DIM):
            self._layout.setRowStretch(r, 1 if r < self.rows else 0)
            self._layout.setColumnStretch(r, 1 if r < self.cols else 0)
        for i, tile in enumerate(self.tiles):
            r, c = divmod(i, self.cols)
            self._layout.addWidget(tile, r, c)
            tile.set_index(i)
            tile.setVisible(self.maximized is None or tile is self.maximized)
        if self.maximized is not None:
            # Span the maximized tile over the whole grid.
            self._layout.removeWidget(self.maximized)
            self._layout.addWidget(self.maximized, 0, 0, self.rows, self.cols)

    def set_bars_visible(self, visible: bool):
        self.show_bars = visible
        for t in self.tiles:
            t.set_bar_visible(visible)

    def is_single(self) -> bool:
        return self.rows * self.cols == 1

    # ----- focus / maximize / swap ---------------------------------------------------------
    def focus_tile(self, tile: VideoTile):
        if tile not in self.tiles:
            return
        changed = tile is not self.focused
        self.focused = tile
        for t in self.tiles:
            t.set_focused(t is tile and len(self.tiles) > 1)
        self.apply_audio_focus()
        if changed:
            self.focusChanged.emit(tile)

    def focus_index(self, index: int):
        if 0 <= index < len(self.tiles):
            self.focus_tile(self.tiles[index])

    def focus_step(self, delta: int):
        if not self.tiles:
            return
        i = self.tiles.index(self.focused) if self.focused in self.tiles else 0
        nxt = self.tiles[(i + delta) % len(self.tiles)]
        self.focus_tile(nxt)
        if self.maximized is not None:
            self.maximized = nxt
            self._relayout()

    def apply_audio_focus(self):
        follow = self.audio_follows_focus and len(self.tiles) > 1
        for t in self.tiles:
            t.controller.set_focus_muted(follow and t is not self.focused)

    def set_audio_follows_focus(self, on: bool):
        self.audio_follows_focus = on
        self.apply_audio_focus()

    def toggle_maximize(self, tile: VideoTile | None = None):
        tile = tile or self.focused
        if len(self.tiles) <= 1 or tile is None:
            return
        self.maximized = None if self.maximized is tile else tile
        self.focus_tile(tile)
        self._relayout()
        self.maximizedChanged.emit(self.maximized is not None)

    def _on_swap(self, source_id: int, dest: VideoTile):
        src = next((t for t in self.tiles if t.tile_id == source_id), None)
        if src is None or src is dest:
            return
        a, b = self.tiles.index(src), self.tiles.index(dest)
        self.tiles[a], self.tiles[b] = self.tiles[b], self.tiles[a]
        self._relayout()
        self.focus_tile(src)

    # ----- loading -------------------------------------------------------------------------
    def free_tiles(self) -> list[VideoTile]:
        return [t for t in self.tiles if not t.has_media]

    def loaded_tiles(self) -> list[VideoTile]:
        return [t for t in self.tiles if t.has_media]

    def add_items(self, items: list[str], grow: bool = True, start: VideoTile | None = None) -> list[str]:
        """Load items into empty tiles (growing the grid if allowed). Returns items that did not fit."""
        items = list(items)
        if not items:
            return []
        if grow:
            needed = len(self.loaded_tiles()) + len(items)
            if start is not None and start.has_media:
                needed -= 1
            if needed > len(self.tiles):
                self.set_dims(*grow_to_fit(self.rows, self.cols, needed))
        targets = []
        if start is not None and start in self.tiles:
            targets.append(start)
        targets += [t for t in self.free_tiles() if t not in targets]
        first = None
        for tile, item in zip(targets, items):
            tile.open(item)
            first = first or tile
        if first is not None:
            self.focus_tile(first)
        return items[len(targets):]

    def _on_tile_drop(self, tile: VideoTile, items: list):
        from ..formats import expand_inputs

        items = expand_inputs(items)
        if not items:
            return
        tile.open(items[0])
        self.focus_tile(tile)
        if len(items) > 1:
            self.add_items(items[1:])

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        from ..formats import expand_inputs

        items = expand_inputs(urls_from_mime(event.mimeData()))
        if items:
            self.add_items(items)
            event.acceptProposedAction()

    # ----- master controls -----------------------------------------------------------------
    def any_playing(self) -> bool:
        return any(t.controller.is_playing for t in self.tiles)

    def play_all(self):
        for t in self.loaded_tiles():
            t.controller.play()

    def pause_all(self):
        for t in self.loaded_tiles():
            t.controller.pause()

    def toggle_all(self):
        self.pause_all() if self.any_playing() else self.play_all()

    def stop_all(self):
        for t in self.loaded_tiles():
            t.controller.stop()

    def set_all_muted(self, muted: bool):
        for t in self.tiles:
            t.controller.set_muted(muted)

    def sync_to_focused(self):
        """Seek every loaded tile to the focused tile's playback time."""
        ref = self.focused
        if ref is None or not ref.has_media:
            return
        ms = ref.controller.time
        for t in self.loaded_tiles():
            if t is not ref:
                t.controller.set_time(ms)
                if ref.controller.is_playing:
                    t.controller.play()

    def close_all(self):
        for t in self.tiles:
            t.controller.clear()

    def release(self):
        for t in self.tiles:
            t.release()
