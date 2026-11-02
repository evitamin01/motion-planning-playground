#!/usr/bin/env bash
# Regenerate the screenshots in docs/images with headless Chrome/Chromium.
#
#   bash scripts/screenshots.sh            # uses ./.conda/bin/python if present
#   CHROME=/path/to/chrome PORT=8799 bash scripts/screenshots.sh
set -euo pipefail

cd "$(dirname "$0")/.."
PORT="${PORT:-8799}"
OUT="docs/images"
if [[ -z "${PYTHON:-}" ]]; then
  if [[ -x .conda/bin/python ]]; then PYTHON=.conda/bin/python; else PYTHON=python; fi
fi

if [[ -z "${CHROME:-}" ]]; then
  for candidate in \
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
    "/Applications/Chromium.app/Contents/MacOS/Chromium" \
    google-chrome google-chrome-stable chromium chromium-browser; do
    if command -v "$candidate" >/dev/null 2>&1 || [[ -x "$candidate" ]]; then
      CHROME="$candidate"
      break
    fi
  done
fi
[[ -n "${CHROME:-}" ]] || { echo "Chrome/Chromium not found; set CHROME=..." >&2; exit 1; }

mkdir -p "$OUT"
TMP="$(mktemp -d)"
"$PYTHON" -m mpplay serve --no-browser --port "$PORT" >/dev/null 2>&1 &
SERVER=$!
trap 'kill $SERVER 2>/dev/null; wait $SERVER 2>/dev/null; rm -rf "$TMP"' EXIT

for _ in $(seq 1 50); do
  curl -sf "http://127.0.0.1:$PORT/api/info" >/dev/null && break
  sleep 0.2
done

shoot() {  # shoot <file> <query> [width] [height]
  # A fresh profile per shot, so state saved by one page does not leak into the next.
  local profile
  profile="$(mktemp -d "$TMP/profile.XXXX")"
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars --user-data-dir="$profile" \
    --window-size="${3:-1600},${4:-960}" --virtual-time-budget=20000 \
    --screenshot="$OUT/$1" "http://127.0.0.1:$PORT/?$2" >/dev/null 2>&1
  # Headless Chrome may lay out a shorter viewport than it captures: trim the empty band.
  "$PYTHON" - "$OUT/$1" <<'PY'
import sys

from PIL import Image

path = sys.argv[1]
img = Image.open(path).convert("RGB")
w, h = img.size
bottom = img.getpixel((w // 2, h - 1))
last = h
while last > 1 and all(img.getpixel((x, last - 1)) == bottom for x in range(0, w, 7)):
    last -= 1
if last < h:
    img.crop((0, 0, w, last)).save(path, optimize=True)
PY
  echo "wrote $OUT/$1"
}

shoot screenshot.png "scenario=maze&planners=astar,dijkstra,rrt_star,prm&mode=split&tab=metrics&seed=1&plan&at=0.45"
shoot overlay-dark.png "scenario=bug_trap&planners=astar,greedy,rrt_star,potential_field&mode=overlay&theme=dark&tab=charts&seed=2&plan&at=1"
shoot narrow-passage.png "scenario=narrow_passage&planners=rrt,rrt_connect,informed_rrt_star,prm&mode=split&tab=metrics&seed=4&plan&at=0.6"
