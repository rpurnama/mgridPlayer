"""Locate libVLC (bundled with the frozen app, or installed system-wide) and import python-vlc.

Must run before anything imports ``vlc``.
"""

from __future__ import annotations

import ctypes
import glob
import os
import sys

_vlc_module = None
resolved_lib_path: str | None = None


class VLCNotFoundError(RuntimeError):
    pass


def bundle_dir() -> str | None:
    """Directory of the PyInstaller bundle, or None when running from source."""
    return getattr(sys, "_MEIPASS", None) if getattr(sys, "frozen", False) else None


def bundled_paths(base: str, platform: str | None = None) -> tuple[str | None, str]:
    """Return (libvlc path, plugin dir) inside a bundle for the given platform."""
    platform = platform or sys.platform
    if platform.startswith("win"):
        lib = os.path.join(base, "libvlc.dll")
        plugins = os.path.join(base, "plugins")
    elif platform == "darwin":
        lib = os.path.join(base, "libvlc.dylib")
        plugins = os.path.join(base, "plugins")
    else:
        candidates = sorted(glob.glob(os.path.join(base, "libvlc.so*")))
        lib = candidates[0] if candidates else None
        plugins = os.path.join(base, "vlc", "plugins")
    if lib and not os.path.exists(lib):
        lib = None
    return lib, plugins


def configure_environment() -> str | None:
    """Point python-vlc at the bundled libVLC if there is one. Returns the lib path used."""
    base = bundle_dir()
    if not base:
        return None
    lib, plugins = bundled_paths(base)
    if not lib:
        return None
    os.environ["PYTHON_VLC_LIB_PATH"] = lib
    os.environ["PYTHON_VLC_MODULE_PATH"] = plugins
    os.environ["VLC_PLUGIN_PATH"] = plugins
    if sys.platform.startswith("win"):
        os.add_dll_directory(base)
    else:
        # Load libvlccore globally first so libvlc resolves it from the bundle.
        for core in sorted(glob.glob(os.path.join(base, "libvlccore.so*"))):
            try:
                ctypes.CDLL(core, mode=ctypes.RTLD_GLOBAL)
                break
            except OSError:
                pass
    return lib


def load_vlc():
    """Import and return the python-vlc module, raising VLCNotFoundError if libVLC is missing."""
    global _vlc_module, resolved_lib_path
    if _vlc_module is not None:
        return _vlc_module
    resolved_lib_path = configure_environment()
    try:
        import vlc  # noqa: PLC0415
        vlc.libvlc_get_version()
    except (OSError, ImportError, AttributeError, NameError) as exc:
        raise VLCNotFoundError(
            "libVLC could not be loaded.\n\n"
            "Install VLC media player (64-bit, same architecture as this app) "
            "or use the standalone build of mgridPlayer.\n\nDetails: " + str(exc)
        ) from exc
    if resolved_lib_path is None:
        dll = getattr(vlc, "dll", None)
        resolved_lib_path = getattr(dll, "_name", None)
    _vlc_module = vlc
    return vlc
