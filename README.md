# mgridPlayer

A VLC-style desktop media player that can also **play many videos at once in a grid**.
It is built on the real VLC engine (libVLC), so it plays everything VLC plays, and its Qt (PySide6) GUI is dark and modern.
It runs on **Linux and Windows** and ships as a standalone bundle.

## Download

Get the latest version from this repository's **Releases** page (right-hand side on GitHub). You don't need Python or VLC installed.

- **Windows:** download `mgridPlayer-<version>-windows-x64.zip`, extract it, and run `mgridPlayer\mgridPlayer.exe`.
  - Windows may show a SmartScreen warning because the app isn't code-signed. Click *More info → Run anyway*.
- **Linux, AppImage:** download `mgridPlayer-<version>-x86_64.AppImage`, then run:

  ```bash
  chmod +x mgridPlayer-*.AppImage && ./mgridPlayer-*.AppImage
  ```

- **Linux, tarball:** download `mgridPlayer-<version>-linux-x86_64.tar.gz`, then run:

  ```bash
  tar xzf mgridPlayer-*.tar.gz && ./mgridPlayer/mgridPlayer
  ```

## Features

**VLC-style player**
- Plays every format libVLC supports, for example:
  - Video: MP4, MKV, AVI, MOV, WebM, WMV, FLV, MPEG-TS/M2TS, 3GP, OGV, VOB, MXF, RM/RMVB…
  - Audio: MP3, FLAC, WAV, AAC, OGG, Opus, M4A, WMA… (audio files show a spectrum visualizer)
  - Network streams: HTTP(S), HLS, RTSP, RTMP, UDP, MMS…
  - Playlists: M3U, M3U8, PLS
- Play/pause/stop, click-to-seek with a hover time preview, ±3 s / 10 s / 1 min jumps, frame stepping
- Speed from 0.25× to 4×, A→B loop, and repeat off/all/one
- Audio and subtitle track selection, external subtitle files, aspect ratio, crop, deinterlace
- Snapshots, a media information dialog, recent media, and a playlist dock (drag to reorder, load/save `.m3u`)
- Fullscreen with an auto-hiding control bar and cursor, plus a minimal interface mode
- VLC-like keyboard shortcuts (press **F1** in the app for the full list), a dark or light theme, and preferences that persist between runs

**Multi-video grid**
- Layouts from 1×1 to 8×8. Pick one with the hover grid picker, a preset, a custom size, or **Auto fit**.
- Opening several files (or a folder) fills the grid, growing it when needed.
- Click a tile to focus it. The main control bar then drives that tile, and **audio follows focus**, so only the focused tile is heard (this can be turned off).
- **Control all tiles** (`A`): play, pause, seek, speed and volume apply to every tile.
- **Sync** (`Y`): seeks every tile to the focused tile's position.
- Double-click (or `Z`) maximizes a tile inside the window; double-click again restores it.
- Drag files from your file manager or the playlist onto any tile.
- Drag a tile's title strip onto another tile to swap their positions.
- Each tile has its own strip with title, seek bar, time, play, mute, maximize and close.

## Run from source

Requires Python 3.9+ and VLC 3.x installed on the system: on Linux `sudo apt install vlc`, on Windows 64-bit VLC from videolan.org.

```bash
python3 -m venv .venv
```

```bash
.venv/bin/pip install -r requirements.txt
```

```bash
.venv/bin/python -m mgridplayer
```

Command-line options:

```text
python -m mgridplayer [media ...] [-g 3x3] [--single] [--no-hw] [--vlc-args "..."]
  media        files, folders, playlists or URLs (several => opened in a grid)
  -g RxC       start with a grid layout
  --single     queue multiple files in the playlist instead of filling a grid
  --no-hw      disable hardware decoding
```

## Build a standalone app

Each build bundles libVLC and its plugins with PyInstaller, so the result needs neither Python nor VLC on the target machine.
PyInstaller can't cross-compile, so build each OS on that OS (or let the GitHub Actions workflow in `.github/workflows/build.yml` build both).

**Linux**

```bash
packaging/build_linux.sh
```

- Output: `dist/mgridPlayer/mgridPlayer` plus `dist/mgridPlayer-<ver>-linux-x86_64.tar.gz`.
- If [`appimagetool`](https://github.com/AppImage/appimagetool/releases) is on `PATH` (or set in `APPIMAGETOOL`), it also produces an AppImage.
- The bundle depends on the glibc of the build machine, so build on the oldest distro you want to support. CI uses Ubuntu 22.04.

**Windows** (PowerShell, 64-bit Python and 64-bit VLC installed)

```bash
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
```

- Output: `dist\mgridPlayer\mgridPlayer.exe` plus a zip.
- If VLC isn't in `C:\Program Files\VideoLAN\VLC`, pass `-VlcDir <path>`.

## Tests

```bash
.venv/bin/pip install -r requirements-dev.txt
```

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
```

## Project layout

```
mgridplayer/
  __main__.py        entry point / CLI
  vlc_loader.py      finds bundled or system libVLC before importing python-vlc
  engine.py          shared libVLC instance + PlayerController (Qt signals, thread-safe events)
  grid_math.py       pure grid layout helpers
  formats.py         supported formats, playlist parsing/writing
  main_window.py     menus, shortcuts, single/grid behaviour, fullscreen
  widgets/           grid view, video tile, control bar, seek slider, playlist, dialogs
  theme.py icons.py settings.py
packaging/           PyInstaller spec, build scripts, icon, .desktop
tests/               pytest suite
```

## Notes

- **Linux/Wayland:** libVLC can only embed video into X11 windows, so on Wayland the app runs Qt through XWayland automatically (`QT_QPA_PLATFORM=xcb`).
- **Windows:** libVLC's video window would swallow mouse clicks on Windows, so the app disables that child window to let clicks reach the tile. Tile focus also works by clicking a tile's control strip.
- **Performance:** many simultaneous HD/4K videos need a decent CPU or GPU. Hardware decoding is on by default (Preferences → Playback).
- **License:** libVLC is LGPL-2.1+, and PySide6 is LGPL-3. A redistributed bundle must comply with those licenses: keep the VLC plugins and libraries as separate shared files (as this build does) and include their license texts.
