#!/usr/bin/env bash
# Launch mgridPlayer. Any arguments (files, folders, URLs, -g 2x2, ...) are passed through.
#   ./mgridplayer.sh
#   ./mgridplayer.sh -g 2x2 ~/Videos
# Uses the project's virtualenv if present (always the latest code), otherwise the standalone build.
HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"

if [ -x "$HERE/.venv/bin/python" ]; then
  cd "$HERE" && exec "$HERE/.venv/bin/python" -m mgridplayer "$@"
elif [ -x "$HERE/dist/mgridPlayer/mgridPlayer" ]; then
  exec "$HERE/dist/mgridPlayer/mgridPlayer" "$@"
else
  echo "mgridPlayer is not set up yet. Run:  packaging/build_linux.sh" >&2
  exit 1
fi
