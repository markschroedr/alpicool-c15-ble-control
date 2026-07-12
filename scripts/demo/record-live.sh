#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."
mkdir -p artifacts/demo
rm -f artifacts/demo/terminal-live.cast artifacts/demo/terminal-live.mp4 artifacts/demo/terminal-live.gif

if ! command -v asciinema >/dev/null 2>&1 || ! command -v agg >/dev/null 2>&1; then
  echo "asciinema and agg are required: brew install asciinema agg" >&2
  exit 1
fi

asciinema record \
  --headless \
  --overwrite \
  --return \
  --window-size 64x18 \
  --idle-time-limit 1.2 \
  --title "Live Alpicool BLE control" \
  --command "uv run python -m scripts.demo.live_demo --demo-temp 16" \
  artifacts/demo/terminal-live.cast

agg \
  --theme kanagawa-dragon \
  --font-size 24 \
  --line-height 1.25 \
  --speed 1.35 \
  --idle-time-limit 1.2 \
  --last-frame-duration 1.8 \
  artifacts/demo/terminal-live.cast \
  artifacts/demo/terminal-live.gif

ffmpeg -y \
  -i artifacts/demo/terminal-live.gif \
  -vf "fps=30,scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p" \
  -an \
  -c:v libx264 \
  -preset slow \
  -crf 18 \
  -movflags +faststart \
  artifacts/demo/terminal-live.mp4
