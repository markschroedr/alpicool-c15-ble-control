#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
clear

echo "Starting Alpicool sleep-cooling schedule"
echo "Schedule file: sleep-cooling-schedule.json"
echo
echo "Keep this window open. Press Control-C to stop."
echo

if [[ ! -f sleep-cooling-schedule.json ]]; then
  cp schedule.example.json sleep-cooling-schedule.json
  echo "Created sleep-cooling-schedule.json from the example."
  echo
fi

caffeinate -dimsu ./control.sh schedule sleep-cooling-schedule.json
