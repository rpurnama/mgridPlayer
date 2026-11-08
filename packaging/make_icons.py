"""Render the app icon to PNG/ICO for packaging: python packaging/make_icons.py"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from PySide6.QtGui import QGuiApplication  # noqa: E402

from mgridplayer.icons import app_icon_image  # noqa: E402

app = QGuiApplication([])
app_icon_image(256).save(os.path.join(HERE, "icon.png"))
if not app_icon_image(256).save(os.path.join(HERE, "icon.ico")):
    print("warning: could not write icon.ico (Qt ico plugin missing)")
print("icons written to", HERE)
