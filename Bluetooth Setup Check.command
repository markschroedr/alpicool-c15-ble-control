#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
clear

echo "Alpicool Bluetooth setup check"
echo
echo "If macOS asks for Bluetooth permission for Alpicool Control, allow it."
echo

./build-app.sh
open -W "$PWD/Alpicool Control.app" --args status || true

echo
echo "Recent app log:"
tail -n 80 logs/app.log 2>/dev/null || true

echo
echo "Recent app error log:"
tail -n 80 logs/app.err.log 2>/dev/null || true

echo
read -r -n 1 -s -p "Done. Press any key to close this window."
echo
