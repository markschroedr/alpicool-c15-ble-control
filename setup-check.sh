#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

echo "Checking runtime..."
command -v uv
uv run python --version

echo
echo "Scanning for Alpicool-like BLE devices..."
./control.sh scan --timeout 10

echo
echo "Trying fridge status..."
./control.sh status
