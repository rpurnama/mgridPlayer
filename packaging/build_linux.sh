#!/usr/bin/env bash
# Build a standalone Linux bundle (dist/mgridPlayer/) + tarball, and an AppImage if appimagetool is available.
# Requires: python3 (3.9+), VLC/libvlc installed on the build machine (e.g. `sudo apt install vlc libvlc-dev`).
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$PWD
PY=${PYTHON:-python3}

if [ ! -x .venv/bin/python ]; then
  "$PY" -m venv .venv
fi
.venv/bin/python -m pip install -q --upgrade pip
.venv/bin/python -m pip install -q -r requirements-dev.txt

.venv/bin/python packaging/make_icons.py
rm -rf build/mgridPlayer dist/mgridPlayer
.venv/bin/python -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging/mgridplayer.spec

INTERNAL=dist/mgridPlayer/_internal
[ -d "$INTERNAL" ] || INTERNAL=dist/mgridPlayer
# Regenerate the plugin cache for the bundled plugin tree (faster startup).
CACHEGEN=$(ls /usr/lib/*/vlc/vlc-cache-gen 2>/dev/null | head -1 || true)
if [ -n "$CACHEGEN" ]; then
  "$CACHEGEN" "$INTERNAL/vlc/plugins" || echo "warning: vlc-cache-gen failed (startup will just be a bit slower)"
fi

ARCH=$(uname -m)
VERSION=$(.venv/bin/python -c "import mgridplayer; print(mgridplayer.__version__)")
tar -C dist -czf "dist/mgridPlayer-$VERSION-linux-$ARCH.tar.gz" mgridPlayer
echo "Bundle:  $ROOT/dist/mgridPlayer/mgridPlayer"
echo "Tarball: $ROOT/dist/mgridPlayer-$VERSION-linux-$ARCH.tar.gz"

APPIMAGETOOL=${APPIMAGETOOL:-$(command -v appimagetool || true)}
if [ -n "$APPIMAGETOOL" ]; then
  APPDIR=build/AppDir
  rm -rf "$APPDIR"
  mkdir -p "$APPDIR/usr/lib"
  cp -a dist/mgridPlayer "$APPDIR/usr/lib/mgridPlayer"
  cp packaging/mgridplayer.desktop "$APPDIR/mgridplayer.desktop"
  cp packaging/icon.png "$APPDIR/mgridplayer.png"
  cat > "$APPDIR/AppRun" <<'RUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/lib/mgridPlayer/mgridPlayer" "$@"
RUN
  chmod +x "$APPDIR/AppRun"
  ARCH=$ARCH "$APPIMAGETOOL" "$APPDIR" "dist/mgridPlayer-$VERSION-$ARCH.AppImage"
  echo "AppImage: $ROOT/dist/mgridPlayer-$VERSION-$ARCH.AppImage"
else
  echo "(appimagetool not found: skipping AppImage. Get it from https://github.com/AppImage/appimagetool/releases and set APPIMAGETOOL=/path/to/it)"
fi
