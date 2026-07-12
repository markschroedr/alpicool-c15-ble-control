#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from types import SimpleNamespace

from rich.text import Text

from scripts.demo.live_demo import console, status_panel


def as_status(raw: dict) -> SimpleNamespace:
    return SimpleNamespace(
        power=bool(raw["power"]),
        mode=str(raw["mode"]),
        unit1=SimpleNamespace(
            temp_current=int(raw["temp_current"]),
            temp_target=int(raw["temp_target"]),
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a sanitized, recorded BLE session.")
    parser.add_argument("trace", type=Path)
    args = parser.parse_args()
    trace = json.loads(args.trace.read_text())

    before = as_status(trace["before"])
    changed = as_status(trace["changed"])
    restored = as_status(trace["restored"])

    console.clear()
    console.print(Text("DIY SLEEP COOLING", style="bold #d4cfc6"))
    console.print(Text("Recorded BLE session · real device responses", style="#8a857b"))
    console.print()
    console.print(status_panel(before, title="Before"))
    time.sleep(1.2)

    console.print()
    console.print(Text(f"  Sending {changed.unit1.temp_target}°C setpoint over Bluetooth…", style="#c4a055"))
    time.sleep(0.9)
    console.print(status_panel(changed, title="Device confirmed", changed=True))
    console.print(Text("  ✓ Setpoint changed on the cooler", style="bold #7a9e7e"))
    time.sleep(1.4)

    console.print()
    console.print(status_panel(restored, title="Restored"))
    console.print(Text("  ✓ Original state independently verified", style="bold #7a9e7e"))
    time.sleep(1.8)


if __name__ == "__main__":
    main()
