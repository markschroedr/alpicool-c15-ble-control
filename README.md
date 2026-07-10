# Alpicool C15 BLE Control

A small macOS controller for reading, changing and scheduling the temperature of a Bluetooth-enabled Alpicool compressor cooler.

I use it to regulate a DIY water-cooled mattress overnight. The controller starts with colder water, raises the target toward morning, switches the cooler off and records a status sample every 15 minutes. The same commands also work manually from Terminal.

The implementation has been tested with an Alpicool C15-style cooler. It auto-detects BLE names beginning with `A1-`, `AK1-`, `AK2-`, `AK3-` or `WT-`, but other models may use a different protocol.

## What it does

- Reads power, mode, battery voltage, current temperature and target temperature.
- Changes the target temperature and power state.
- Applies a JSON schedule without leaving a Python process running permanently.
- Records append-only JSONL measurements for later analysis.
- Reassembles BLE notifications that macOS delivers in multiple fragments.
- Builds a tiny local app wrapper so macOS can grant Bluetooth permission normally.

## Requirements

- macOS 13 or newer
- Python 3.11 or newer
- [`uv`](https://docs.astral.sh/uv/)
- A compatible Bluetooth-enabled Alpicool cooler

## Setup

Clone the repository, then run the setup check from its folder:

```bash
./setup-check.sh
```

If macOS asks for Bluetooth access for **Alpicool Control**, allow it. You can also open `Bluetooth Setup Check.command` directly in Finder to trigger the permission prompt.

## Manual control

```bash
./control.sh scan
./control.sh status
./control.sh set-temp 18
./control.sh apply --power on --temp 16
./control.sh apply --power off
./control.sh record-status
```

Auto-detection is enough when only one compatible cooler is nearby. If several are visible, pass the exact BLE name or macOS CoreBluetooth identifier:

```bash
./control.sh status --device AK1-EXAMPLE
```

## Scheduling

The included example uses the schedule from my sleep-cooling setup:

| Time | Action |
| --- | --- |
| 17:00 | power on, set `16 C` |
| 23:00 | set `18 C` |
| 02:00 | set `20 C` |
| 04:00 | power off |

Create your local schedule and edit it as needed:

```bash
cp schedule.example.json sleep-cooling-schedule.json
```

Install the macOS LaunchAgent:

```bash
./install-launchd.sh
```

It wakes every 15 minutes, records a status sample and reconciles the cooler with the state that should be active at that time. The Mac must be awake for this to run.

Measurements are appended to `data/fridge-status.jsonl`. The local schedule, logs, app bundle and measurements are excluded from Git.

Check or remove the LaunchAgent:

```bash
./launchd-status.sh
./uninstall-launchd.sh
```

For a manual overnight run:

```bash
caffeinate -dimsu ./control.sh schedule sleep-cooling-schedule.json
```

You can also double-click `Run Sleep Cooling.command`.

## Protocol notes

The cooler exposes BLE service `0x1234`, accepts commands on characteristic `0x1235` and sends responses on `0x1236`. Commands are unauthenticated and don't require pairing. See [docs/protocol-notes.md](docs/protocol-notes.md) for the tested packet behavior and the projects that documented the protocol before this implementation.

## Tests

```bash
uv run pytest
```

The protocol tests don't require a cooler. A real BLE smoke test still requires compatible hardware and macOS Bluetooth permission.

## License

MIT
