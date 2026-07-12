#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

data_path="${1:-data/private-mac-fridge-status-2026-07-11.jsonl}"
terminal_video="${2:-artifacts/demo/terminal-live.mp4}"
output_dir="${3:-artifacts/demo/final}"

uv run python scripts/demo/render_assets.py \
  --data "$data_path" \
  --terminal-video "$terminal_video" \
  --output-dir "$output_dir"
