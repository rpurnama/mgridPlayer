import os

from mgridplayer import formats


def test_classification():
    assert formats.is_media_file("a/b/movie.MKV")
    assert formats.is_media_file("song.flac")
    assert not formats.is_media_file("notes.txt")
    assert formats.is_audio_file("x.mp3") and not formats.is_audio_file("x.mp4")
    assert formats.is_url("https://x.org/live.m3u8")
    assert formats.is_url("rtsp://cam.local/stream")
    assert not formats.is_url("C:/videos/a.mp4")
    assert formats.is_subtitle_file("movie.srt")


def test_display_name():
    assert formats.display_name("/tmp/x/My Movie.mp4") == "My Movie.mp4"
    assert formats.display_name("https://host/path/clip%20one.mp4") == "clip one.mp4"
    assert formats.display_name("rtsp://cam.local") == "cam.local"


def test_filter_contains_formats():
    f = formats.file_dialog_filter()
    for ext in ("*.mp4", "*.mkv", "*.avi", "*.webm", "*.mp3", "*.m3u"):
        assert ext in f
    assert "All files (*)" in f


def test_m3u_roundtrip(tmp_path):
    (tmp_path / "a.mp4").write_bytes(b"")
    (tmp_path / "b.mkv").write_bytes(b"")
    pl = tmp_path / "list.m3u"
    formats.write_m3u(str(pl), [str(tmp_path / "a.mp4"), "http://example.com/s.ts"])
    assert formats.parse_playlist(str(pl)) == [str(tmp_path / "a.mp4"), "http://example.com/s.ts"]


def test_relative_and_pls(tmp_path):
    (tmp_path / "rel.m3u").write_text("#EXTM3U\nsub/v.mp4\n")
    assert formats.parse_playlist(str(tmp_path / "rel.m3u")) == [os.path.join(str(tmp_path), "sub", "v.mp4")]
    (tmp_path / "x.pls").write_text("[playlist]\nFile1=http://radio/1\nTitle1=x\nFile2=/abs/a.mp3\n")
    assert formats.parse_playlist(str(tmp_path / "x.pls")) == ["http://radio/1", "/abs/a.mp3"]


def test_hls_manifest_is_not_expanded(tmp_path):
    hls = tmp_path / "stream.m3u8"
    hls.write_text("#EXTM3U\n#EXT-X-VERSION:3\nseg0.ts\n")
    assert not formats.is_playlist_file(str(hls))
    assert formats.expand_inputs([str(hls)]) == [str(hls)]


def test_expand_folder(tmp_path):
    for n in ("b.mp4", "a.MKV", "c.txt"):
        (tmp_path / n).write_bytes(b"")
    out = formats.expand_inputs([str(tmp_path), "https://x/y.mp4"])
    assert [os.path.basename(p) for p in out[:2]] == ["a.MKV", "b.mp4"]
    assert out[2] == "https://x/y.mp4"
