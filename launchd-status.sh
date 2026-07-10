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
  echo "== $label =="
  launchctl print "$GUI_DOMAIN/$label" 2>/dev/null | sed -n '1,80p' || echo "not loaded"
  echo
done
