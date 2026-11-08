"""Dark / light Qt style sheets."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from . import icons

ACCENT = "#ff7a1a"

PALETTES = {
    "dark": {
        "bg": "#121318", "panel": "#1a1c23", "panel2": "#22252e", "border": "#2c303b",
        "text": "#e6e6eb", "muted": "#9497a3", "hover": "#2b2f3a", "tile": "#000000",
        "placeholder": "#16171d",
    },
    "light": {
        "bg": "#eef0f4", "panel": "#ffffff", "panel2": "#f3f4f7", "border": "#d6d9e0",
        "text": "#1d1f26", "muted": "#626674", "hover": "#e6e8ee", "tile": "#000000",
        "placeholder": "#e2e5eb",
    },
}

_QSS = """
* {{ font-size: 10pt; }}
QMainWindow, QDialog {{ background: {bg}; color: {text}; }}
QWidget {{ color: {text}; }}
QToolTip {{ background: {panel2}; color: {text}; border: 1px solid {border}; padding: 4px 6px; border-radius: 4px; }}

QMenuBar {{ background: {panel}; border-bottom: 1px solid {border}; padding: 2px; }}
QMenuBar::item {{ padding: 4px 10px; border-radius: 4px; background: transparent; }}
QMenuBar::item:selected {{ background: {hover}; }}
QMenu {{ background: {panel}; border: 1px solid {border}; padding: 4px; border-radius: 6px; }}
QMenu::item {{ padding: 6px 28px 6px 26px; border-radius: 4px; }}
QMenu::item:selected {{ background: {accent}; color: #ffffff; }}
QMenu::item:disabled {{ color: {muted}; }}
QMenu::separator {{ height: 1px; background: {border}; margin: 4px 8px; }}
QMenu::icon {{ padding-left: 6px; }}

#ControlBar {{ background: {panel}; border-top: 1px solid {border}; }}
#ControlBar QLabel {{ color: {muted}; }}
#TimeLabel {{ font-family: "DejaVu Sans Mono", "Consolas", monospace; color: {text}; }}

QToolButton {{ background: transparent; border: none; border-radius: 6px; padding: 5px; }}
QToolButton:hover {{ background: {hover}; }}
QToolButton:pressed {{ background: {border}; }}
QToolButton:checked {{ background: {accent_soft}; }}
QToolButton::menu-indicator {{ image: none; width: 0; }}
#PlayButton {{ background: {accent}; border-radius: 20px; padding: 8px; }}
#PlayButton:hover {{ background: {accent_hover}; }}

QSlider::groove:horizontal {{ height: 4px; background: {border}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {accent}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: #ffffff; border: 2px solid {accent}; width: 10px; height: 10px; margin: -5px 0; border-radius: 7px; }}
QSlider::handle:horizontal:hover {{ background: {accent}; }}
#SeekSlider::groove:horizontal {{ height: 5px; }}

#GridView {{ background: {bg}; }}
#VideoTile {{ background: {tile}; border: 2px solid transparent; border-radius: 4px; }}
#VideoTile[focused="true"] {{ border: 2px solid {accent}; }}
#VideoTile[dropTarget="true"] {{ border: 2px dashed {accent}; }}
#TileBar {{ background: {panel}; }}
#TileBar QLabel {{ color: {text}; }}
#TileBar QToolButton {{ padding: 2px; border-radius: 4px; }}
#TileTime {{ color: {muted}; font-family: "DejaVu Sans Mono", "Consolas", monospace; font-size: 9pt; }}
#Placeholder {{ background: {placeholder}; border-radius: 3px; }}
#Placeholder QLabel {{ color: {muted}; }}
#PlaceholderTitle {{ font-size: 12pt; font-weight: 600; }}
#Placeholder QPushButton {{ background: {panel2}; border: 1px solid {border}; border-radius: 6px; padding: 6px 14px; }}
#Placeholder QPushButton:hover {{ border-color: {accent}; }}

QDockWidget {{ color: {text}; titlebar-close-icon: none; }}
QDockWidget::title {{ background: {panel}; padding: 6px 8px; border-bottom: 1px solid {border}; }}
QListWidget, QTableWidget, QTreeWidget {{ background: {panel}; border: none; outline: none; alternate-background-color: {panel2}; }}
QListWidget::item {{ padding: 6px; border-radius: 4px; }}
QListWidget::item:selected {{ background: {accent_soft}; color: {text}; }}
QListWidget::item:hover {{ background: {hover}; }}
QHeaderView::section {{ background: {panel2}; border: none; padding: 4px; color: {muted}; }}

QPushButton {{ background: {panel2}; border: 1px solid {border}; border-radius: 6px; padding: 6px 14px; }}
QPushButton:hover {{ border-color: {accent}; }}
QPushButton:default {{ background: {accent}; color: #fff; border-color: {accent}; }}
QLineEdit, QComboBox, QSpinBox {{ background: {panel2}; border: 1px solid {border}; border-radius: 6px; padding: 5px 8px; selection-background-color: {accent}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border-color: {accent}; }}
QComboBox QAbstractItemView {{ background: {panel}; border: 1px solid {border}; selection-background-color: {accent}; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px; border: 1px solid {border}; background: {panel2}; }}
QCheckBox::indicator:checked {{ background: {accent}; border-color: {accent}; }}
QGroupBox {{ border: 1px solid {border}; border-radius: 8px; margin-top: 12px; padding-top: 8px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {muted}; }}
QStatusBar {{ background: {panel}; color: {muted}; border-top: 1px solid {border}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; }}
QScrollBar::handle:vertical {{ background: {border}; border-radius: 5px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
#Toast {{ background: rgba(20,21,27,225); color: #ffffff; border-radius: 10px; padding: 10px 18px; font-size: 11pt; }}
#GridPicker {{ background: {panel}; }}
"""


def colors(name: str) -> dict:
    return PALETTES.get(name, PALETTES["dark"])


def apply_theme(app: QApplication, name: str):
    c = dict(colors(name))
    c.update(accent=ACCENT, accent_hover="#ff9440", accent_soft="rgba(255,122,26,0.28)")
    icons.set_icon_color(c["text"])
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(c["bg"]))
    pal.setColor(QPalette.WindowText, QColor(c["text"]))
    pal.setColor(QPalette.Base, QColor(c["panel"]))
    pal.setColor(QPalette.AlternateBase, QColor(c["panel2"]))
    pal.setColor(QPalette.Text, QColor(c["text"]))
    pal.setColor(QPalette.Button, QColor(c["panel2"]))
    pal.setColor(QPalette.ButtonText, QColor(c["text"]))
    pal.setColor(QPalette.Highlight, QColor(ACCENT))
    pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    pal.setColor(QPalette.ToolTipBase, QColor(c["panel2"]))
    pal.setColor(QPalette.ToolTipText, QColor(c["text"]))
    pal.setColor(QPalette.PlaceholderText, QColor(c["muted"]))
    app.setPalette(pal)
    app.setStyleSheet(_QSS.format(**c))
