#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"
LOG_DIR="$HOME/Server/logs/alpicool"
GUI_DOMAIN="gui/$(id -u)"
APP="$ROOT/Alpicool Control.app"
LABEL="com.alpicool.c15-ble-control.reconcile-schedule"
SCHEDULE="$ROOT/sleep-cooling-schedule.json"

mkdir -p "$LAUNCH_AGENTS" "$LOG_DIR" "$ROOT/launchd"
"$ROOT/build-app.sh" >/dev/null

if [[ ! -f "$SCHEDULE" ]]; then
  cp "$ROOT/schedule.example.json" "$SCHEDULE"
  echo "Created $SCHEDULE from schedule.example.json"
fi

remove_plist() {
  local label="$1"
  local installed_plist="$LAUNCH_AGENTS/$label.plist"
  launchctl bootout "$GUI_DOMAIN" "$installed_plist" >/dev/null 2>&1 || true
  rm -f "$installed_plist" "$ROOT/launchd/$label.plist"
}

write_interval_plist() {
  local label="$1"
  local interval_seconds="$2"
  shift 2

  local plist="$ROOT/launchd/$label.plist"
  local installed_plist="$LAUNCH_AGENTS/$label.plist"

  {
    printf '%s\n' '<?xml version="1.0" encoding="UTF-8"?>'
    printf '%s\n' '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">'
    printf '%s\n' '<plist version="1.0">'
    printf '%s\n' '<dict>'
    printf '%s\n' '  <key>Label</key>'
    printf '  <string>%s</string>\n' "$label"
    printf '%s\n' '  <key>ProgramArguments</key>'
    printf '%s\n' '  <array>'
    printf '%s\n' '    <string>/usr/bin/open</string>'
    printf '%s\n' '    <string>-gj</string>'
    printf '    <string>%s</string>\n' "$APP"
    printf '%s\n' '    <string>--args</string>'
    for arg in "$@"; do
      printf '    <string>%s</string>\n' "$arg"
    done
    printf '%s\n' '  </array>'
    printf '%s\n' '  <key>StartInterval</key>'
    printf '  <integer>%s</integer>\n' "$interval_seconds"
    printf '%s\n' '  <key>EnvironmentVariables</key>'
    printf '%s\n' '  <dict>'
    printf '%s\n' '    <key>PATH</key>'
    printf '%s\n' '    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>'
    printf '%s\n' '  </dict>'
    printf '%s\n' '  <key>StandardOutPath</key>'
    printf '  <string>%s/%s.out.log</string>\n' "$LOG_DIR" "$label"
    printf '%s\n' '  <key>StandardErrorPath</key>'
    printf '  <string>%s/%s.err.log</string>\n' "$LOG_DIR" "$label"
    printf '%s\n' '</dict>'
    printf '%s\n' '</plist>'
  } > "$plist"

  plutil -lint "$plist" >/dev/null
  cp "$plist" "$installed_plist"
  launchctl bootout "$GUI_DOMAIN" "$installed_plist" >/dev/null 2>&1 || true
  launchctl bootstrap "$GUI_DOMAIN" "$installed_plist"
  launchctl enable "$GUI_DOMAIN/$label"
  echo "Installed $label every ${interval_seconds}s: $*"
}

remove_plist "com.mark.alpicool.1700-power-on-cool-16"
remove_plist "com.mark.alpicool.2300-temp-18"
remove_plist "com.mark.alpicool.0200-temp-20"
remove_plist "com.mark.alpicool.0400-power-off"
remove_plist "com.mark.alpicool.track-status"
remove_plist "com.mark.alpicool.reconcile-schedule"
remove_plist "$LABEL"

write_interval_plist \
  "$LABEL" \
  900 \
  reconcile-schedule \
  "$SCHEDULE"

echo
echo "Installed Alpicool LaunchAgents."
echo "Logs: $LOG_DIR"
echo "Tracking data: $ROOT/data/fridge-status.jsonl"
echo "Inspect one job with:"
echo "launchctl print $GUI_DOMAIN/$LABEL"
