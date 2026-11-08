"""Click-to-seek slider with a hover time tooltip."""

from __future__ import annotations

import time

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QSlider, QStyle, QStyleOptionSlider, QToolTip

from ..engine import format_ms

RESOLUTION = 10000


class SeekSlider(QSlider):
    seekRequested = Signal(float)

    def __init__(self, parent=None, show_tooltip: bool = True):
        super().__init__(Qt.Horizontal, parent)
        self.setRange(0, RESOLUTION)
        self.setFocusPolicy(Qt.NoFocus)
        self.setMouseTracking(True)
        self.setObjectName("SeekSlider")
        self._duration = 0
        self._show_tooltip = show_tooltip
        self._last_emit = 0.0
        self.sliderMoved.connect(self._on_moved)
        self.sliderReleased.connect(lambda: self.seekRequested.emit(self.value() / RESOLUTION))

    def set_duration(self, ms: int):
        self._duration = max(0, ms)

    def set_fraction(self, fraction: float):
        if not self.isSliderDown():
            self.blockSignals(True)
            self.setValue(int(round(fraction * RESOLUTION)))
            self.blockSignals(False)

    def _value_at(self, x: int) -> int:
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        groove = self.style().subControlRect(QStyle.CC_Slider, opt, QStyle.SC_SliderGroove, self)
        handle = self.style().subControlRect(QStyle.CC_Slider, opt, QStyle.SC_SliderHandle, self)
        span = max(1, groove.width() - handle.width())
        pos = x - groove.x() - handle.width() // 2
        return QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), pos, span)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.isEnabled():
            value = self._value_at(int(event.position().x()))
            self.setValue(value)
            self.seekRequested.emit(value / RESOLUTION)
            self.setSliderDown(True)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        value = self._value_at(int(event.position().x()))
        if self._show_tooltip and self._duration > 0:
            QToolTip.showText(event.globalPosition().toPoint(),
                              format_ms(int(self._duration * value / RESOLUTION)), self)
        if self.isSliderDown():
            self.setValue(value)
            self._on_moved(value)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.isSliderDown() and event.button() == Qt.LeftButton:
            self.setSliderDown(False)
            self.seekRequested.emit(self.value() / RESOLUTION)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _on_moved(self, value: int):
        now = time.monotonic()
        if now - self._last_emit > 0.08:  # throttle seeking while dragging
            self._last_emit = now
            self.seekRequested.emit(value / RESOLUTION)
