"""Exercises PlayerController with real libVLC but dummy audio/video outputs."""

import shutil
import subprocess

import pytest

pytest.importorskip("vlc")

from mgridplayer import engine  # noqa: E402


@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not available")
    out = tmp_path_factory.mktemp("media") / "clip.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25",
                    "-f", "lavfi", "-i", "sine", "-t", "4", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", str(out)], check=True)
    return str(out)


@pytest.fixture(scope="module")
def instance():
    return engine.vlc.Instance(["--quiet", "--vout=dummy", "--aout=dummy", "--avcodec-hw=none"])


def test_play_seek_end(qtbot, instance, clip):
    c = engine.PlayerController(instance=instance)
    states = []
    c.stateChanged.connect(states.append)
    with qtbot.waitSignal(c.durationChanged, timeout=5000, check_params_cb=lambda ms: ms > 0):
        c.open(clip)
    qtbot.waitUntil(lambda: c.state == "playing", timeout=5000)
    assert 3500 <= c.length <= 4500
    c.set_volume(40)
    assert c.volume == 40
    c.set_rate(2.0)
    c.step_rate(1)
    assert c.rate == 2.5
    c.set_rate(1.0)
    c.set_time(3000)
    with qtbot.waitSignal(c.ended, timeout=6000):
        pass
    assert "playing" in states and c.state == "ended"
    c.release()


def test_loop_and_ab(qtbot, instance, clip):
    c = engine.PlayerController(instance=instance)
    c.loop = True
    c.open(clip)
    qtbot.waitUntil(lambda: c.state == "playing", timeout=5000)
    c.set_time(3500)
    qtbot.wait(1500)
    assert c.state == "playing", "loop should restart instead of ending"
    c.set_time(500)
    qtbot.wait(300)
    assert "A set" in c.cycle_ab()
    qtbot.wait(700)
    assert "→" in c.cycle_ab()
    a, b = c.ab_loop
    assert 0 <= a < b
    assert c.cycle_ab() == "A-B loop cleared"
    c.release()


def test_mute_layers(instance):
    c = engine.PlayerController(instance=instance)
    c.set_focus_muted(True)
    assert not c.muted and c.focus_muted
    c.toggle_mute()
    assert c.muted
    c.release()


def test_format_ms():
    assert engine.format_ms(0) == "00:00"
    assert engine.format_ms(61_000) == "01:01"
    assert engine.format_ms(3_725_000) == "1:02:05"
    assert engine.format_ms(-1) == "--:--"
