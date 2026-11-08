"""Dockable playlist with reordering, m3u load/save and drag-out onto tiles."""

from __future__ import annotations

from PySide6.QtCore import QMimeData, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QDockWidget, QHBoxLayout, QListWidget, QListWidgetItem, QToolButton,
    QVBoxLayout, QWidget,
)

from .. import icons
from ..formats import display_name, expand_inputs, is_url
from .video_tile import urls_from_mime

ROLE_MRL = Qt.UserRole + 1


class PlaylistList(QListWidget):
    externalDrop = Signal(list, int)   # items, row

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setAcceptDrops(True)
        self.setAlternatingRowColors(False)
        self.setUniformItemSizes(True)

    def mimeData(self, items):  # noqa: N802 - Qt naming
        md = super().mimeData(items)
        urls = []
        for it in items:
            mrl = it.data(ROLE_MRL)
            urls.append(QUrl(mrl) if is_url(mrl) else QUrl.fromLocalFile(mrl))
        md.setUrls(urls)
        return md

    def dragEnterEvent(self, event):
        if event.source() is self or event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.source() is self:
            super().dragMoveEvent(event)
        elif event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if event.source() is self:
            super().dropEvent(event)
            return
        row = self.indexAt(event.position().toPoint()).row()
        self.externalDrop.emit(urls_from_mime(event.mimeData()), row)
        event.acceptProposedAction()


class PlaylistPanel(QDockWidget):
    playRequested = Signal(str)
    loadIntoGridRequested = Signal(list)
    addFilesRequested = Signal()
    addUrlRequested = Signal()
    openPlaylistRequested = Signal()
    savePlaylistRequested = Signal()

    def __init__(self, parent=None):
        super().__init__("Playlist", parent)
        self.setObjectName("PlaylistDock")
        self.setFeatures(QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetMovable |
                         QDockWidget.DockWidgetFloatable)
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)
        self.list = PlaylistList()
        self.list.itemDoubleClicked.connect(lambda it: self.playRequested.emit(it.data(ROLE_MRL)))
        self.list.externalDrop.connect(lambda items, row: self.add(expand_inputs(items), row))
        lay.addWidget(self.list, 1)

        bar = QHBoxLayout()
        bar.setSpacing(2)
        self._buttons = []

        def btn(icon_name, tip, slot):
            b = QToolButton()
            b.setIcon(icons.icon(icon_name))
            b.setIconSize(QSize(18, 18))
            b.setToolTip(tip)
            b.setFocusPolicy(Qt.NoFocus)
            b.setProperty("iconName", icon_name)
            b.clicked.connect(slot)
            bar.addWidget(b)
            self._buttons.append(b)
            return b

        btn("add", "Add files…", self.addFilesRequested)
        btn("globe", "Add network stream…", self.addUrlRequested)
        btn("remove", "Remove selected (Del)", self.remove_selected)
        btn("trash", "Clear playlist", self.list.clear)
        bar.addStretch(1)
        btn("grid", "Load selected (or all) into the grid", self._load_into_grid)
        btn("folder", "Open playlist file…", self.openPlaylistRequested)
        btn("save", "Save playlist…", self.savePlaylistRequested)
        lay.addLayout(bar)
        self.setWidget(body)
        self._current = ""

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete:
            self.remove_selected()
            return
        super().keyPressEvent(event)

    # ----- contents ------------------------------------------------------------------------
    def add(self, items: list[str], row: int = -1):
        existing = set(self.items())
        for item in items:
            if item in existing:
                continue
            it = QListWidgetItem(icons.icon("globe" if is_url(item) else "play"), display_name(item))
            it.setData(ROLE_MRL, item)
            it.setToolTip(item)
            if 0 <= row < self.list.count():
                self.list.insertItem(row, it)
                row += 1
            else:
                self.list.addItem(it)
            existing.add(item)
        self.set_current(self._current)

    def items(self) -> list[str]:
        return [self.list.item(i).data(ROLE_MRL) for i in range(self.list.count())]

    def remove_selected(self):
        for it in self.list.selectedItems():
            self.list.takeItem(self.list.row(it))

    def _load_into_grid(self):
        sel = [it.data(ROLE_MRL) for it in self.list.selectedItems()]
        self.loadIntoGridRequested.emit(sel or self.items())

    def set_current(self, mrl: str):
        self._current = mrl or ""
        for i in range(self.list.count()):
            it = self.list.item(i)
            f = QFont(it.font())
            f.setBold(self._norm(it.data(ROLE_MRL)) == self._norm(self._current))
            it.setFont(f)

    @staticmethod
    def _norm(mrl: str) -> str:
        import os

        return mrl if is_url(mrl) else os.path.abspath(mrl) if mrl else ""

    def neighbour(self, mrl: str, step: int, wrap: bool) -> str | None:
        items = self.items()
        if not items:
            return None
        norm = [self._norm(i) for i in items]
        cur = self._norm(mrl)
        if cur not in norm:
            return items[0] if step > 0 else items[-1]
        idx = norm.index(cur) + step
        if 0 <= idx < len(items):
            return items[idx]
        return items[idx % len(items)] if wrap else None

    def refresh_icons(self):
        for b in self._buttons:
            b.setIcon(icons.icon(b.property("iconName")))
        for i in range(self.list.count()):
            it = self.list.item(i)
            it.setIcon(icons.icon("globe" if is_url(it.data(ROLE_MRL)) else "play"))
