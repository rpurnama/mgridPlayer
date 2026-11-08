"""Dialogs: open network stream, custom grid size, media info, preferences, shortcuts, toast."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QPropertyAnimation, Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton, QSpinBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..formats import is_url
from ..grid_math import MAX_DIM


class OpenUrlDialog(QDialog):
    def __init__(self, history: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Open Network Stream")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Enter a network URL (http, https, rtsp, rtmp, udp, mms, hls…):"))
        self.combo = QComboBox()
        self.combo.setEditable(True)
        self.combo.addItems([h for h in history if is_url(h)])
        self.combo.setCurrentText("")
        self.combo.lineEdit().setPlaceholderText("https://example.com/stream.m3u8")
        lay.addWidget(self.combo)
        self.error = QLabel("")
        self.error.setStyleSheet("color:#ff6b6b;")
        lay.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Play")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _accept(self):
        if is_url(self.url()):
            self.accept()
        else:
            self.error.setText("That doesn't look like a supported URL.")

    def url(self) -> str:
        return self.combo.currentText().strip()


class GridSizeDialog(QDialog):
    def __init__(self, rows: int, cols: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Custom Grid Size")
        form = QFormLayout(self)
        self.rows = QSpinBox()
        self.cols = QSpinBox()
        for sb, v in ((self.rows, rows), (self.cols, cols)):
            sb.setRange(1, MAX_DIM)
            sb.setValue(v)
        form.addRow("Rows:", self.rows)
        form.addRow("Columns:", self.cols)
        self.total = QLabel()
        form.addRow("Tiles:", self.total)
        for sb in (self.rows, self.cols):
            sb.valueChanged.connect(self._update)
        self._update()
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _update(self):
        self.total.setText(str(self.rows.value() * self.cols.value()))

    def dims(self) -> tuple[int, int]:
        return self.rows.value(), self.cols.value()


class TableDialog(QDialog):
    def __init__(self, title: str, rows: list[tuple[str, str]], headers=("Property", "Value"), parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(560, 420)
        lay = QVBoxLayout(self)
        table = QTableWidget(len(rows), 2)
        table.setHorizontalHeaderLabels(list(headers))
        table.verticalHeader().hide()
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.setWordWrap(True)
        for r, (k, v) in enumerate(rows):
            table.setItem(r, 0, QTableWidgetItem(k))
            table.setItem(r, 1, QTableWidgetItem(v))
        table.resizeRowsToContents()
        lay.addWidget(table)
        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(self.reject)
        lay.addWidget(close)


class PreferencesDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setMinimumWidth(480)
        self.settings = settings
        lay = QVBoxLayout(self)

        ui = QGroupBox("Interface")
        f1 = QFormLayout(ui)
        self.theme = QComboBox()
        self.theme.addItems(["dark", "light"])
        self.theme.setCurrentText(settings.get("theme"))
        f1.addRow("Theme:", self.theme)
        self.bars = QCheckBox("Show a control strip under each grid tile")
        self.bars.setChecked(settings.get("show_tile_bars"))
        f1.addRow(self.bars)
        lay.addWidget(ui)

        grid = QGroupBox("Grid")
        f2 = QFormLayout(grid)
        self.follow = QCheckBox("Audio follows the focused tile (mute the others)")
        self.follow.setChecked(settings.get("audio_follows_focus"))
        self.grow = QCheckBox("Grow the grid automatically when opening more files than free tiles")
        self.grow.setChecked(settings.get("grow_grid"))
        f2.addRow(self.follow)
        f2.addRow(self.grow)
        lay.addWidget(grid)

        pb = QGroupBox("Playback")
        f3 = QFormLayout(pb)
        self.hw = QCheckBox("Hardware-accelerated decoding (takes effect after restart)")
        self.hw.setChecked(settings.get("hw_decoding"))
        f3.addRow(self.hw)
        row = QHBoxLayout()
        self.snap = QLineEdit(settings.snapshot_dir())
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        row.addWidget(self.snap, 1)
        row.addWidget(browse)
        w = QWidget()
        w.setLayout(row)
        row.setContentsMargins(0, 0, 0, 0)
        f3.addRow("Snapshot folder:", w)
        lay.addWidget(pb)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Snapshot folder", self.snap.text())
        if d:
            self.snap.setText(d)

    def _save(self):
        s = self.settings
        s.set("theme", self.theme.currentText())
        s.set("show_tile_bars", self.bars.isChecked())
        s.set("audio_follows_focus", self.follow.isChecked())
        s.set("grow_grid", self.grow.isChecked())
        s.set("hw_decoding", self.hw.isChecked())
        s.set("snapshot_dir", self.snap.text().strip())
        self.accept()


SHORTCUTS = [
    ("Space", "Play / pause"),
    ("S", "Stop"),
    ("F, double-click (single view)", "Toggle fullscreen"),
    ("Esc", "Exit fullscreen"),
    ("← / →", "Jump 10 s back / forward"),
    ("Shift+← / Shift+→", "Jump 3 s back / forward"),
    ("Ctrl+← / Ctrl+→", "Jump 1 min back / forward"),
    ("↑ / ↓, mouse wheel", "Volume up / down"),
    ("M", "Mute"),
    ("[ / ] / =", "Slower / faster / normal speed"),
    ("E", "Next frame"),
    ("L", "A-B loop (set A, set B, clear)"),
    ("R", "Cycle repeat mode"),
    ("N / P", "Next / previous playlist item"),
    ("V / B", "Cycle subtitle / audio track"),
    ("Shift+S", "Snapshot"),
    ("Ctrl+O / Ctrl+Shift+O", "Open files / open folder"),
    ("Ctrl+N", "Open network stream"),
    ("Ctrl+L", "Toggle playlist"),
    ("Ctrl+I", "Media information"),
    ("Ctrl+G", "Custom grid size"),
    ("Ctrl+1 … Ctrl+9", "Focus tile 1 … 9"),
    ("Tab / Shift+Tab", "Focus next / previous tile"),
    ("Z, double-click (grid)", "Maximize / restore focused tile"),
    ("A", "Toggle 'control all tiles'"),
    ("Y", "Sync all tiles to focused tile"),
    ("Ctrl+Space", "Play / pause all tiles"),
    ("Ctrl+W", "Close media in focused tile"),
    ("Ctrl+Q", "Quit"),
]


class Toast(QLabel):
    """Small transient notification shown over the main window."""

    def __init__(self, parent: QWidget):
        super().__init__(None)
        self._host = parent
        self.setObjectName("Toast")
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAlignment(Qt.AlignCenter)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade_out)
        self._anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._anim.finished.connect(self._after_anim)

    def show_message(self, text: str, ms: int = 1800):
        self.setText(text)
        self.adjustSize()
        host = self._host
        top_left = host.mapToGlobal(QPoint(0, 0))
        x = top_left.x() + (host.width() - self.width()) // 2
        y = top_left.y() + int(host.height() * 0.12)
        self.move(x, y)
        self._anim.stop()
        self.setWindowOpacity(1.0)
        self.show()
        self.raise_()
        self._timer.start(ms)

    def _fade_out(self):
        self._anim.setDuration(350)
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.start()

    def _after_anim(self):
        if self.windowOpacity() < 0.05:
            self.hide()
