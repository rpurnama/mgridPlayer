import os

from mgridplayer import vlc_loader


def test_bundled_paths_windows(tmp_path):
    (tmp_path / "libvlc.dll").write_bytes(b"")
    lib, plugins = vlc_loader.bundled_paths(str(tmp_path), "win32")
    assert lib == os.path.join(str(tmp_path), "libvlc.dll")
    assert plugins == os.path.join(str(tmp_path), "plugins")


def test_bundled_paths_linux(tmp_path):
    (tmp_path / "libvlc.so.5").write_bytes(b"")
    lib, plugins = vlc_loader.bundled_paths(str(tmp_path), "linux")
    assert lib.endswith("libvlc.so.5")
    assert plugins == os.path.join(str(tmp_path), "vlc", "plugins")


def test_bundled_paths_missing(tmp_path):
    lib, _ = vlc_loader.bundled_paths(str(tmp_path), "linux")
    assert lib is None


def test_not_frozen_uses_system(monkeypatch):
    monkeypatch.delattr("sys.frozen", raising=False)
    assert vlc_loader.bundle_dir() is None
    assert vlc_loader.configure_environment() is None


def test_frozen_sets_env(monkeypatch, tmp_path):
    (tmp_path / "libvlc.so.5").write_bytes(b"")
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setattr("sys._MEIPASS", str(tmp_path), raising=False)
    monkeypatch.setattr("sys.platform", "linux")
    for k in ("PYTHON_VLC_LIB_PATH", "PYTHON_VLC_MODULE_PATH", "VLC_PLUGIN_PATH"):
        monkeypatch.delenv(k, raising=False)
    lib = vlc_loader.configure_environment()
    assert lib == str(tmp_path / "libvlc.so.5")
    assert os.environ["PYTHON_VLC_MODULE_PATH"] == str(tmp_path / "vlc" / "plugins")
