"""One cell of the grid: a video surface, an empty-state placeholder and a slim control strip."""

from __future__ import annotations

import itertools

from PySide6.QtCore import QMimeData, QPoint, Qt, Signal
from PySide6.QtGui import QDrag, QFontMetrics
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QStackedLayout,
    QToolButton, QVBoxLayout, QWidget,
)

from .. import icons
from ..engine import PlayerController, format_ms
from .seek_slider import SeekSlider
from .video_surface import VideoSurface

TILE_MIME = "application/x-mgridplayer-tile"
_ids = itertools.count(1)


def _tool(icon_name: str, tip: str, size: int = 16) -> QToolButton:
    b = QToolButton()
    b.setIcon(icons.icon(icon_name))
    b.setToolTip(tip)
    b.setFocusPolicy(Qt.NoFocus)
    b.setAutoRaise(True)
    b.setIconSize(b.iconSize().scaled(size, size, Qt.KeepAspectRatio))
    return b


class ElidedLabel(QLabel):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._full = text
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

    def setText(self, text):  # noqa: N802 - Qt naming
        self._full = text
        self.setToolTip(text)
        self._refresh()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refresh()

    def _refresh(self):
        super().setText(QFontMetrics(self.font()).elidedText(self._full, Qt.ElideMiddle, max(10, self.width())))


class Placeholder(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Placeholder")
        self.setAttribute(Qt.WA_StyledBackground, True)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(8)
        art = QLabel()
        art.setPixmap(icons.icon("drop").pixmap(44, 44))
        art.setAlignment(Qt.AlignCenter)
        title = QLabel("Drop media here")
        title.setObjectName("PlaceholderTitle")
        title.setAlignment(Qt.AlignCenter)
        hint = QLabel("or double-click a playlist item")
        hint.setAlignment(Qt.AlignCenter)
        row = QHBoxLayout()
        row.setAlignment(Qt.AlignCenter)
        self.open_btn = QPushButton(icons.icon("folder"), " Open file…")
        self.url_btn = QPushButton(icons.icon("globe"), " Open URL…")
        for b in (self.open_btn, self.url_btn):
            b.setFocusPolicy(Qt.NoFocus)
            b.setCursor(Qt.PointingHandCursor)
            row.addWidget(b)
        for w in (art, title, hint):
            lay.addWidget(w)
        lay.addLayout(row)
        self._compact = [hint, title]

    def resizeEvent(self, event):
        super().resizeEvent(event)
        small = self.height() < 150 or self.width() < 260
        for w in self._compact:
            w.setVisible(not small or w.objectName() == "PlaceholderTitle")
        self.url_btn.setVisible(self.width() >= 260)


class TileBar(QWidget):
    """Thin strip under each tile: index, title, mini seek bar, time and buttons. Draggable to swap tiles."""

    dragStarted = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TileBar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(28)
        self.setCursor(Qt.OpenHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 0, 2, 0)
        lay.setSpacing(4)
        self.index_label = QLabel("1")
        self.index_label.setStyleSheet("font-weight:700; color:#ff7a1a;")
        self.title = ElidedLabel("Empty")
        self.title.setMinimumWidth(60)
        self.seek = SeekSlider(self)
        self.seek.setMinimumWidth(40)
        self.time = QLabel("")
        self.time.setObjectName("TileTime")
        self.play_btn = _tool("play", "Play / pause")
        self.mute_btn = _tool("volume", "Mute this tile")
        self.max_btn = _tool("maximize", "Maximize / restore (double-click)")
        self.close_btn = _tool("close", "Close media")
        lay.addWidget(self.index_label)
        lay.addWidget(self.title, 5)
        lay.addWidget(self.seek, 4)
        lay.addWidget(self.time)
        for b in (self.play_btn, self.mute_btn, self.max_btn, self.close_btn):
            lay.addWidget(b)
        self._press_pos: QPoint | None = None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = self.width()
        self.seek.setVisible(w > 330)
        self.time.setVisible(w > 250)
        self.play_btn.setVisible(w > 200)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press_pos = event.position().toPoint()
        event.ignore()  # let the tile take focus too

    def mouseMoveEvent(self, event):
        if self._press_pos is not None and (event.buttons() & Qt.LeftButton):
            if (event.position().toPoint() - self._press_pos).manhattanLength() > QApplication.startDragDistance():
                self._press_pos = None
                self.dragStarted.emit()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._press_pos = None
        event.ignore()


class VideoTile(QFrame):
    focusRequested = Signal(object)
    maximizeRequested = Signal(object)
    openRequested = Signal(object)
    openUrlRequested = Signal(object)
    filesDropped = Signal(object, list)
    swapRequested = Signal(int, object)        # source tile id, destination tile
    contextMenuRequested = Signal(object, QPoint)
    errorOccurred = Signal(object, str)

    def __init__(self, parent=None, instance=None):
        super().__init__(parent)
        self.tile_id = next(_ids)
        self.setObjectName("VideoTile")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAcceptDrops(True)
        self.setProperty("focused", False)
        self.setProperty("dropTarget", False)
        self.setMinimumSize(120, 90)

        self.surface = VideoSurface()
        self.placeholder = Placeholder()
        self.bar = TileBar()

        holder = QWidget()
        self.stack = QStackedLayout(holder)
        self.stack.addWidget(self.placeholder)
        self.stack.addWidget(self.surface)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(0)
        lay.addWidget(holder, 1)
        lay.addWidget(self.bar)

        self.controller = PlayerController(self, instance=instance)
        self.controller.set_window(int(self.surface.winId()))

        c = self.controller
        c.mediaChanged.connect(self._on_media)
        c.positionChanged.connect(self._on_position)
        c.durationChanged.connect(self.bar.seek.set_duration)
        c.stateChanged.connect(self._on_state)
        c.muteChanged.connect(self._on_mute)
        c.errorOccurred.connect(lambda msg: self.errorOccurred.emit(self, msg))
        self.bar.seek.seekRequested.connect(c.seek)
        self.bar.play_btn.clicked.connect(c.toggle_play)
        self.bar.mute_btn.clicked.connect(c.toggle_mute)
        self.bar.max_btn.clicked.connect(lambda: self.maximizeRequested.emit(self))
        self.bar.close_btn.clicked.connect(c.clear)
        self.bar.dragStarted.connect(self._start_drag)
        for b in (self.bar.play_btn, self.bar.mute_btn, self.bar.max_btn, self.bar.close_btn):
            b.pressed.connect(lambda: self.focusRequested.emit(self))
        self.bar.seek.seekRequested.connect(lambda _f: self.focusRequested.emit(self))
        self.placeholder.open_btn.clicked.connect(lambda: self.openRequested.emit(self))
        self.placeholder.url_btn.clicked.connect(lambda: self.openUrlRequested.emit(self))
        self._on_media("")

    # ----- state ---------------------------------------------------------------------------
    @property
    def has_media(self) -> bool:
        return self.controller.has_media

    def open(self, item: str, play: bool = True):
        self.controller.open(item, play=play)

    def set_index(self, i: int):
        self.bar.index_label.setText(str(i + 1))

    def set_bar_visible(self, visible: bool):
        self.bar.setVisible(visible)

    def set_focused(self, focused: bool):
        if self.property("focused") != focused:
            self.setProperty("focused", focused)
            self._repolish()

    def _set_drop_target(self, on: bool):
        if self.property("dropTarget") != on:
            self.setProperty("dropTarget", on)
            self._repolish()

    def _repolish(self):
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def _on_media(self, mrl: str):
        self.stack.setCurrentWidget(self.surface if mrl else self.placeholder)
        self.bar.title.setText(self.controller.title if mrl else "Empty")
        self.bar.time.setText("")
        self.bar.seek.set_fraction(0)
        for w in (self.bar.seek, self.bar.play_btn, self.bar.close_btn):
            w.setEnabled(bool(mrl))

    def _on_position(self, fraction: float, ms: int):
        self.bar.seek.set_fraction(fraction)
        length = self.controller.length
        self.bar.time.setText(f"{format_ms(ms)} / {format_ms(length)}" if length else format_ms(ms))

    def _on_state(self, state: str):
        self.bar.play_btn.setIcon(icons.icon("pause" if state == "playing" else "play"))

    def _on_mute(self, muted: bool):
        self.bar.mute_btn.setIcon(icons.icon("volume_mute" if muted else "volume"))

    def refresh_icons(self):
        self._on_state(self.controller.state)
        self._on_mute(self.controller.muted)
        self.bar.max_btn.setIcon(icons.icon("maximize"))
        self.bar.close_btn.setIcon(icons.icon("close"))

    # ----- mouse ---------------------------------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() in (Qt.LeftButton, Qt.RightButton, Qt.MiddleButton):
            self.focusRequested.emit(self)
        if event.button() == Qt.MiddleButton:
            self.controller.toggle_play()
        event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.maximizeRequested.emit(self)
        event.accept()

    def contextMenuEvent(self, event):
        self.focusRequested.emit(self)
        self.contextMenuRequested.emit(self, event.globalPos())

    def wheelEvent(self, event):
        steps = event.angleDelta().y() / 120
        if steps and self.has_media:
            self.focusRequested.emit(self)
            self.controller.set_volume(self.controller.volume + int(steps * 5))
        event.accept()

    # ----- drag & drop ---------------------------------------------------------------------
    def _start_drag(self):
        if not self.has_media:
            return
        self.focusRequested.emit(self)
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(TILE_MIME, str(self.tile_id).encode())
        drag.setMimeData(mime)
        drag.setPixmap(self.bar.grab())
        drag.exec(Qt.MoveAction)

    def dragEnterEvent(self, event):
        md = event.mimeData()
        if md.hasFormat(TILE_MIME):
            if int(bytes(md.data(TILE_MIME)).decode()) != self.tile_id:
                self._set_drop_target(True)
                event.acceptProposedAction()
                return
        elif md.hasUrls() or md.hasText():
            self._set_drop_target(True)
            event.acceptProposedAction()
            return
        event.ignore()

    def dragLeaveEvent(self, event):
        self._set_drop_target(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self._set_drop_target(False)
        md = event.mimeData()
        if md.hasFormat(TILE_MIME):
            self.swapRequested.emit(int(bytes(md.data(TILE_MIME)).decode()), self)
            event.acceptProposedAction()
            return
        items = urls_from_mime(md)
        if items:
            self.filesDropped.emit(self, items)
            event.acceptProposedAction()

    def release(self):
        self.controller.release()


def urls_from_mime(md) -> list[str]:
    items: list[str] = []
    if md.hasUrls():
        for url in md.urls():
            items.append(url.toLocalFile() if url.isLocalFile() else url.toString())
    elif md.hasText():
        items = [ln.strip() for ln in md.text().splitlines() if ln.strip()]
    return items
