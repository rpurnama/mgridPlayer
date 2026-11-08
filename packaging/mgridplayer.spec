# PyInstaller spec for mgridPlayer — bundles libVLC + plugins so the app runs standalone.
#   Linux:   pyinstaller packaging/mgridplayer.spec          (uses the system VLC install)
#   Windows: set VLC_DIR=C:\Program Files\VideoLAN\VLC && pyinstaller packaging\mgridplayer.spec
# -*- mode: python -*-
import glob
import os
import sys

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
IS_WIN = sys.platform.startswith("win")

# Plugin categories never needed by an embedded player (and some would drag in Qt5 / big deps).
SKIP_PLUGIN_DIRS = {"gui", "control", "services_discovery", "stream_out", "access_output",
                    "mux", "notify", "keystore", "lua", "video_splitter"}
SKIP_PLUGIN_FILES = ("libvdpau_", "libgoom_", "libprojectm_", "libglspectrum_", "libchromecast")


def collect_plugins(plugin_root, dest_root):
    out = []
    for path in glob.glob(os.path.join(plugin_root, "**", "*"), recursive=True):
        if not os.path.isfile(path) or not path.endswith((".so", ".dll")):
            continue
        rel = os.path.relpath(path, plugin_root)
        top = rel.split(os.sep)[0]
        if top in SKIP_PLUGIN_DIRS or os.path.basename(path).startswith(SKIP_PLUGIN_FILES):
            continue
        out.append((path, os.path.join(dest_root, os.path.dirname(rel))))
    return out


binaries = []
if IS_WIN:
    vlc_dir = os.environ.get("VLC_DIR", r"C:\Program Files\VideoLAN\VLC")
    if not os.path.isfile(os.path.join(vlc_dir, "libvlc.dll")):
        raise SystemExit(f"libvlc.dll not found in VLC_DIR={vlc_dir!r} (install 64-bit VLC or set VLC_DIR)")
    binaries += [(os.path.join(vlc_dir, n), ".") for n in ("libvlc.dll", "libvlccore.dll")]
    binaries += collect_plugins(os.path.join(vlc_dir, "plugins"), "plugins")
else:
    libdir = os.environ.get("VLC_LIB_DIR", "/usr/lib/x86_64-linux-gnu")
    libs = sorted(glob.glob(os.path.join(libdir, "libvlc.so.*")) + glob.glob(os.path.join(libdir, "libvlccore.so.*")))
    if not libs:
        raise SystemExit(f"libvlc.so not found in {libdir} (install libvlc-dev / vlc, or set VLC_LIB_DIR)")
    # keep only the real files + the soname links python-vlc / libvlc look for
    binaries += [(p, ".") for p in libs if p.count(".so.") == 1 and len(p.split(".so.")[1].split(".")) == 1]
    binaries += collect_plugins(os.environ.get("VLC_PLUGIN_DIR", os.path.join(libdir, "vlc", "plugins")),
                                os.path.join("vlc", "plugins"))

icon_file = os.path.join(SPECPATH, "icon.ico" if IS_WIN else "icon.png")

a = Analysis(
    [os.path.join(ROOT, "packaging", "launcher.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=[],
    hiddenimports=["vlc"],
    excludes=["tkinter", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtWebEngineCore",
              "PySide6.QtPdf", "PySide6.Qt3DCore", "PySide6.QtCharts"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="mgridPlayer",
    console=False,
    icon=icon_file if os.path.exists(icon_file) else None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="mgridPlayer")
