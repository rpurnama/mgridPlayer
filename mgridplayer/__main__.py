"""Entry point: ``python -m mgridplayer [files or URLs...]``."""

from __future__ import annotations

import argparse
import ctypes
import os
import sys


def _prepare_platform():
    if sys.platform.startswith("linux"):
        # libVLC can only embed video into X11 windows; run Qt through XWayland on Wayland sessions.
        if os.environ.get("WAYLAND_DISPLAY") and not os.environ.get("QT_QPA_PLATFORM"):
            os.environ["QT_QPA_PLATFORM"] = "xcb"
        # libVLC's Xlib-based outputs need Xlib to be thread-safe before anything touches X.
        try:
            ctypes.CDLL("libX11.so.6").XInitThreads()
        except OSError:
            pass
    elif sys.platform.startswith("win"):
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("mgridPlayer.mgridPlayer")
        except (AttributeError, OSError):
            pass


def parse_args(argv):
    p = argparse.ArgumentParser(prog="mgridplayer", description="VLC-style multi-video grid player")
    p.add_argument("media", nargs="*", help="files, folders, playlists or URLs to open")
    p.add_argument("-g", "--grid", metavar="RxC", help="start with a grid layout, e.g. 2x2")
    p.add_argument("--single", action="store_true", help="queue multiple files instead of filling a grid")
    p.add_argument("--no-hw", action="store_true", help="disable hardware decoding")
    p.add_argument("--vlc-args", default="", help="extra libVLC arguments (space separated)")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    _prepare_platform()

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QMessageBox

    from . import APP_NAME, __version__

    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName(APP_NAME)
    app.setDesktopFileName("mgridplayer")

    from . import icons
    from .settings import Settings
    from .theme import apply_theme
    from .vlc_loader import VLCNotFoundError, load_vlc

    app.setWindowIcon(icons.app_icon())
    settings = Settings()
    apply_theme(app, settings.get("theme"))

    try:
        load_vlc()
    except VLCNotFoundError as exc:
        QMessageBox.critical(None, APP_NAME, str(exc))
        return 1

    from .engine import create_instance
    from .main_window import MainWindow

    extra = [a for a in args.vlc_args.split() if a]
    try:
        create_instance(hw_decoding=settings.get("hw_decoding") and not args.no_hw, extra_args=extra)
    except RuntimeError as exc:
        QMessageBox.critical(None, APP_NAME, str(exc))
        return 1

    win = MainWindow(settings)
    if args.grid:
        try:
            r, c = (int(x) for x in args.grid.lower().replace("×", "x").split("x"))
            win.grid.set_dims(r, c)
        except ValueError:
            print(f"Ignoring invalid --grid value: {args.grid}", file=sys.stderr)
    win.show()

    if args.media:
        many = len(args.media) > 1 or (len(args.media) == 1 and os.path.isdir(args.media[0]))
        QTimer.singleShot(0, lambda: win.handle_open(args.media, into_grid=many and not args.single))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
