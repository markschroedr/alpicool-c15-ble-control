#!/usr/bin/env bash
set -euo pipefail

GUI_DOMAIN="gui/$(id -u)"
LABELS=(
  "com.alpicool.c15-ble-control.reconcile-schedule"
  "com.mark.alpicool.1700-power-on-cool-16"
  "com.mark.alpicool.2300-temp-18"
  "com.mark.alpicool.0200-temp-20"
  "com.mark.alpicool.0400-power-off"
  "com.mark.alpicool.track-status"
  "com.mark.alpicool.reconcile-schedule"
)

for label in "${LABELS[@]}"; do
  plist="$HOME/Library/LaunchAgents/$label.plist"
  launchctl bootout "$GUI_DOMAIN" "$plist" >/dev/null 2>&1 || true
  rm -f "$plist"
  echo "Removed $label"
done
