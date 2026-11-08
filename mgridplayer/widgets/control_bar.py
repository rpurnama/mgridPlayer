"""VLC-style bottom control bar plus the hover grid-size picker."""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QMenu, QSizePolicy, QSlider, QToolButton, QVBoxLayout, QWidget,
    QWidgetAction,
)

from .. import icons
from ..engine import RATE_STEPS, format_ms
from ..grid_math import MAX_DIM, PRESETS
from ..theme import ACCENT
from .seek_slider import SeekSlider


class GridPicker(QWidget):
    """Word-style table picker: hover to choose rows × columns, click to apply."""

    picked = Signal(int, int)
    CELL = 22

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("GridPicker")
        self.setMouseTracking(True)
        self._hover = (1, 1)
        self.setFixedSize(QSize(MAX_DIM * self.CELL + 16, MAX_DIM * self.CELL + 40))

    def _cell_at(self, pos) -> tuple[int, int]:
        c = min(MAX_DIM, max(1, int((pos.x() - 8) // self.CELL) + 1))
        r = min(MAX_DIM, max(1, int((pos.y() - 8) // self.CELL) + 1))
        return r, c

    def mouseMoveEvent(self, event):
        self._hover = self._cell_at(event.position())
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.picked.emit(*self._cell_at(event.position()))

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        hr, hc = self._hover
        text = self.palette().windowText().color()
        for r in range(MAX_DIM):
            for c in range(MAX_DIM):
                rect = QRect(8 + c * self.CELL, 8 + r * self.CELL, self.CELL - 4, self.CELL - 4)
                on = r < hr and c < hc
                p.setPen(QPen(QColor(ACCENT) if on else QColor(128, 130, 140, 140), 1))
                p.setBrush(QColor(255, 122, 26, 150) if on else QColor(0, 0, 0, 0))
                p.drawRoundedRect(rect, 3, 3)
        p.setPen(text)
        p.drawText(QRect(0, MAX_DIM * self.CELL + 10, self.width(), 24), Qt.AlignCenter,
                   f"{hr} × {hc}  ({hr * hc} videos)")


def _button(icon_name: str, tip: str, size: int = 20, checkable: bool = False) -> QToolButton:
    b = QToolButton()
    b.setIcon(icons.icon(icon_name))
    b.setIconSize(QSize(size, size))
    b.setToolTip(tip)
    b.setFocusPolicy(Qt.NoFocus)
    b.setCheckable(checkable)
    b.setCursor(Qt.PointingHandCursor)
    b.setProperty("iconName", icon_name)
    return b


class ControlBar(QWidget):
    playPauseClicked = Signal()
    stopClicked = Signal()
    prevClicked = Signal()
    nextClicked = Signal()
    jumpClicked = Signal(int)
    fullscreenClicked = Signal()
    playlistToggled = Signal(bool)
    gridPicked = Signal(int, int)
    gridAutoClicked = Signal()
    gridCustomClicked = Signal()
    repeatClicked = Signal()
    masterToggled = Signal(bool)
    syncClicked = Signal()
    snapshotClicked = Signal()
    rateSelected = Signal(float)
    muteClicked = Signal()
    volumeChanged = Signal(int)
    seekRequested = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ControlBar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 6, 12, 8)
        outer.setSpacing(4)

        # Row 1: time / seek / duration
        row1 = QHBoxLayout()
        self.time_label = QLabel("00:00")
        self.time_label.setObjectName("TimeLabel")
        self.duration_label = QLabel("00:00")
        self.duration_label.setObjectName("TimeLabel")
        self.seek = SeekSlider(self)
        self.seek.seekRequested.connect(self.seekRequested)
        row1.addWidget(self.time_label)
        row1.addWidget(self.seek, 1)
        row1.addWidget(self.duration_label)
        outer.addLayout(row1)

        # Row 2: buttons
        row2 = QHBoxLayout()
        row2.setSpacing(2)
        self.play_btn = _button("play", "Play / Pause (Space)", 22)
        self.play_btn.setObjectName("PlayButton")
        self.prev_btn = _button("prev", "Previous in playlist (P)")
        self.stop_btn = _button("stop", "Stop (S)")
        self.next_btn = _button("next", "Next in playlist (N)")
        self.back_btn = _button("rewind", "Jump back 10 s (←)")
        self.fwd_btn = _button("forward", "Jump forward 10 s (→)")
        self.play_btn.clicked.connect(self.playPauseClicked)
        self.stop_btn.clicked.connect(self.stopClicked)
        self.prev_btn.clicked.connect(self.prevClicked)
        self.next_btn.clicked.connect(self.nextClicked)
        self.back_btn.clicked.connect(lambda: self.jumpClicked.emit(-10000))
        self.fwd_btn.clicked.connect(lambda: self.jumpClicked.emit(10000))
        row2.addWidget(self.play_btn)
        row2.addSpacing(6)
        for b in (self.prev_btn, self.stop_btn, self.next_btn, self.back_btn, self.fwd_btn):
            row2.addWidget(b)
        row2.addWidget(self._separator())

        self.fullscreen_btn = _button("fullscreen", "Fullscreen (F)")
        self.fullscreen_btn.clicked.connect(self.fullscreenClicked)
        self.playlist_btn = _button("playlist", "Show playlist (Ctrl+L)", checkable=True)
        self.playlist_btn.toggled.connect(self.playlistToggled)
        self.repeat_btn = _button("repeat", "Repeat: off (R)", checkable=True)
        self.repeat_btn.clicked.connect(self.repeatClicked)
        self.snapshot_btn = _button("camera", "Take snapshot (Shift+S)")
        self.snapshot_btn.clicked.connect(self.snapshotClicked)
        for b in (self.fullscreen_btn, self.playlist_btn, self.repeat_btn, self.snapshot_btn):
            row2.addWidget(b)
        row2.addWidget(self._separator())

        # Grid controls
        self.grid_btn = _button("grid", "Grid layout (Ctrl+G)")
        self.grid_btn.setPopupMode(QToolButton.InstantPopup)
        self.grid_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.grid_btn.setText("1×1")
        self.grid_btn.setMenu(self._build_grid_menu())
        self.master_btn = _button("link", "Control all tiles together (A)", checkable=True)
        self.master_btn.toggled.connect(self.masterToggled)
        self.sync_btn = _button("sync", "Sync all tiles to the focused tile's time (Y)")
        self.sync_btn.clicked.connect(self.syncClicked)
        for b in (self.grid_btn, self.master_btn, self.sync_btn):
            row2.addWidget(b)

        row2.addStretch(1)

        self.rate_btn = QToolButton()
        self.rate_btn.setText("1.00×")
        self.rate_btn.setToolTip("Playback speed ([ / ])")
        self.rate_btn.setFocusPolicy(Qt.NoFocus)
        self.rate_btn.setPopupMode(QToolButton.InstantPopup)
        rate_menu = QMenu(self.rate_btn)
        for r in RATE_STEPS:
            act = rate_menu.addAction(f"{r:g}×")
            act.triggered.connect(lambda _=False, r=r: self.rateSelected.emit(r))
        self.rate_btn.setMenu(rate_menu)
        row2.addWidget(self.rate_btn)

        self.mute_btn = _button("volume", "Mute (M)")
        self.mute_btn.clicked.connect(self.muteClicked)
        self.volume = QSlider(Qt.Horizontal)
        self.volume.setRange(0, 125)
        self.volume.setFixedWidth(110)
        self.volume.setFocusPolicy(Qt.NoFocus)
        self.volume.setToolTip("Volume (↑ / ↓, mouse wheel)")
        self.volume.valueChanged.connect(self._on_volume)
        self.volume_label = QLabel("100%")
        self.volume_label.setMinimumWidth(38)
        row2.addWidget(self.mute_btn)
        row2.addWidget(self.volume)
        row2.addWidget(self.volume_label)
        outer.addLayout(row2)

        self._icon_buttons = [self.play_btn, self.prev_btn, self.stop_btn, self.next_btn, self.back_btn,
                              self.fwd_btn, self.fullscreen_btn, self.playlist_btn, self.repeat_btn,
                              self.snapshot_btn, self.grid_btn, self.master_btn, self.sync_btn, self.mute_btn]
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

    def _separator(self) -> QWidget:
        w = QWidget()
        w.setFixedSize(13, 22)
        w.setStyleSheet("border-left: 1px solid rgba(128,128,140,0.35); margin-left: 6px;")
        return w

    def _build_grid_menu(self) -> QMenu:
        menu = QMenu(self)
        picker = GridPicker(menu)
        act = QWidgetAction(menu)
        act.setDefaultWidget(picker)
        menu.addAction(act)
        picker.picked.connect(lambda r, c: (menu.close(), self.gridPicked.emit(r, c)))
        menu.addSeparator()
        for r, c in PRESETS:
            a = menu.addAction(f"{r} × {c}")
            a.triggered.connect(lambda _=False, r=r, c=c: self.gridPicked.emit(r, c))
        menu.addSeparator()
        menu.addAction("Auto (fit loaded videos)").triggered.connect(self.gridAutoClicked)
        menu.addAction("Custom size…").triggered.connect(self.gridCustomClicked)
        return menu

    def wheelEvent(self, event):
        steps = event.angleDelta().y() / 120
        if steps:
            self.volume.setValue(self.volume.value() + int(steps * 5))

    # ----- updates from the focused player -------------------------------------------------
    def _on_volume(self, v: int):
        self.volume_label.setText(f"{v}%")
        self.volumeChanged.emit(v)

    def set_volume(self, v: int):
        self.volume.blockSignals(True)
        self.volume.setValue(v)
        self.volume.blockSignals(False)
        self.volume_label.setText(f"{v}%")

    def set_muted(self, muted: bool):
        self.mute_btn.setProperty("iconName", "volume_mute" if muted else "volume")
        self.mute_btn.setIcon(icons.icon(self.mute_btn.property("iconName")))

    def set_playing(self, playing: bool):
        self.play_btn.setProperty("iconName", "pause" if playing else "play")
        self.play_btn.setIcon(icons.icon(self.play_btn.property("iconName"), "#ffffff"))

    def set_position(self, fraction: float, ms: int):
        self.seek.set_fraction(fraction)
        self.time_label.setText(format_ms(ms))

    def set_duration(self, ms: int):
        self.seek.set_duration(ms)
        self.duration_label.setText(format_ms(ms) if ms > 0 else "--:--")

    def set_rate(self, rate: float):
        self.rate_btn.setText(f"{rate:.2f}×")

    def set_grid_label(self, rows: int, cols: int):
        self.grid_btn.setText(f"{rows}×{cols}")
        multi = rows * cols > 1
        self.master_btn.setEnabled(multi)
        self.sync_btn.setEnabled(multi)

    def set_repeat_mode(self, mode: str):
        name = "repeat_one" if mode == "one" else "repeat"
        self.repeat_btn.setProperty("iconName", name)
        self.repeat_btn.setIcon(icons.icon(name))
        self.repeat_btn.setChecked(mode != "none")
        self.repeat_btn.setToolTip({"none": "Repeat: off", "all": "Repeat: all", "one": "Repeat: one"}[mode] + " (R)")

    def set_fullscreen(self, fs: bool):
        self.fullscreen_btn.setProperty("iconName", "fullscreen_exit" if fs else "fullscreen")
        self.fullscreen_btn.setIcon(icons.icon(self.fullscreen_btn.property("iconName")))

    def set_media_loaded(self, loaded: bool):
        for w in (self.seek, self.stop_btn, self.back_btn, self.fwd_btn, self.snapshot_btn):
            w.setEnabled(loaded)

    def refresh_icons(self):
        for b in self._icon_buttons:
            b.setIcon(icons.icon(b.property("iconName"), "#ffffff" if b is self.play_btn else None))
