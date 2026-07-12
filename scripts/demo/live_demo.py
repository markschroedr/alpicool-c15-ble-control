#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass

from rich.console import Console, Group
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from scripts.alpicool_ble import AlpicoolClient, FridgeStatus, find_fridge


console = Console(force_terminal=True, color_system="truecolor", width=70, height=24)


@dataclass(frozen=True)
class OriginalState:
    power: bool
    target: int


def status_panel(status: FridgeStatus, *, title: str, changed: bool = False) -> Group:
    table = Table.grid(expand=True, padding=(0, 1))
    table.add_column(justify="left")
    table.add_column(justify="center")
    table.add_column(justify="right")

    current = Text(f"{status.unit1.temp_current}°C", style="bold #d4cfc6")
    target_style = "bold #c4a055" if changed else "bold #d4cfc6"
    target = Text(f"{status.unit1.temp_target}°C", style=target_style)
    power = Text("ON" if status.power else "OFF", style="bold #7a9e7e" if status.power else "#8a857b")

    table.add_row(Text("WATER", style="#8a857b"), Text("TARGET", style="#8a857b"), Text("POWER", style="#8a857b"))
    table.add_row(current, target, power)

    return Group(
        Text(title, style="bold #8a857b"),
        Rule(style="#6b665e"),
        table,
    )


async def restore_state(
    device_selector: str | None,
    timeout: float,
    original: OriginalState,
    *,
    attempts: int = 8,
) -> FridgeStatus:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            device = await find_fridge(device_selector, timeout)
            async with AlpicoolClient(device) as fridge:
                restored = await fridge.apply(power=original.power, temp=original.target)
            if restored.power == original.power and restored.unit1.temp_target == original.target:
                return restored
            last_error = RuntimeError("cooler did not confirm the original state")
        except Exception as exc:  # Restoration deliberately retries the full BLE boundary.
            last_error = exc
        if attempt + 1 < attempts:
            await asyncio.sleep(2)
    raise RuntimeError(f"could not restore original cooler state: {last_error}")


async def query_status(
    device_selector: str | None,
    timeout: float,
    *,
    attempts: int = 5,
) -> FridgeStatus:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            device = await find_fridge(device_selector, timeout)
            async with AlpicoolClient(device) as fridge:
                return await fridge.query()
        except Exception as exc:
            last_error = exc
        if attempt + 1 < attempts:
            await asyncio.sleep(2)
    raise RuntimeError(f"could not connect to cooler after {attempts} attempts: {type(last_error).__name__}")


async def apply_temperature(
    device_selector: str | None,
    timeout: float,
    temperature: int,
    *,
    attempts: int = 5,
) -> FridgeStatus:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            device = await find_fridge(device_selector, timeout)
            async with AlpicoolClient(device) as fridge:
                changed = await fridge.apply(temp=temperature)
            if changed.unit1.temp_target == temperature:
                return changed
            last_error = RuntimeError("cooler did not confirm the demo target")
        except Exception as exc:
            last_error = exc
        if attempt + 1 < attempts:
            await asyncio.sleep(2)
    raise RuntimeError(f"could not apply demo target after {attempts} attempts: {type(last_error).__name__}")


async def run_demo(args: argparse.Namespace) -> None:
    console.clear()
    console.print(Text("DIY SLEEP COOLING", style="bold #d4cfc6"))
    console.print(Text("A camping fridge controlling a water-cooled mattress", style="#8a857b"))
    console.print()
    console.print(Text("  Connecting to the cooler over Bluetooth…", style="#8a857b"))

    before = await query_status(args.device, args.timeout)
    original = OriginalState(power=before.power, target=before.unit1.temp_target)
    demo_target = args.demo_temp
    if demo_target == original.target:
        demo_target = 18 if original.target != 18 else 16
    if not before.temp_min <= demo_target <= before.temp_max:
        raise ValueError(f"demo temperature must be between {before.temp_min} and {before.temp_max}°C")

    console.print(status_panel(before, title="Live cooler status"))
    await asyncio.sleep(1.1)

    mutation_started = False
    restored: FridgeStatus | None = None
    demo_error: BaseException | None = None
    try:
        console.print()
        console.print(Text(f"  Sending {demo_target}°C setpoint over Bluetooth…", style="#c4a055"))
        mutation_started = True
        changed = await apply_temperature(args.device, args.timeout, demo_target)

        await asyncio.sleep(0.8)
        console.print(status_panel(changed, title="Setpoint confirmed", changed=True))
        console.print(Text("  ✓ Real device response", style="bold #7a9e7e"))
        await asyncio.sleep(1.2)
    except BaseException as exc:
        demo_error = exc
    finally:
        if mutation_started:
            restored = await restore_state(args.device, args.timeout, original)

    if demo_error is not None:
        raise demo_error

    if restored is None:
        raise RuntimeError("demo ended without restoring the cooler")
    console.print()
    console.print(
        Text(
            f"  ✓ Original state restored · {restored.unit1.temp_target}°C · "
            f"power {'on' if restored.power else 'off'}",
            style="bold #7a9e7e",
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Record a privacy-safe live Alpicool demo.")
    parser.add_argument("--demo-temp", type=int, default=16)
    parser.add_argument("--device")
    parser.add_argument("--timeout", type=float, default=12)
    return parser


if __name__ == "__main__":
    try:
        asyncio.run(run_demo(build_parser().parse_args()))
    except Exception as exc:
        console.print()
        console.print(Text(f"  Demo stopped safely · {type(exc).__name__}", style="bold #c47070"))
        raise SystemExit(1) from None
