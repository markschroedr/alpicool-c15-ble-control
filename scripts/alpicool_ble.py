#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import struct
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, time as datetime_time, timedelta
from pathlib import Path
from typing import Iterable

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError


SERVICE_UUID = "00001234-0000-1000-8000-00805f9b34fb"
COMMAND_UUID = "00001235-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "00001236-0000-1000-8000-00805f9b34fb"

FRIDGE_NAME_PREFIXES = ("A1-", "AK1-", "AK2-", "AK3-", "WT-")

COMMAND_BIND = 0
COMMAND_QUERY = 1
COMMAND_SET = 2
COMMAND_RESET = 4
COMMAND_SET_UNIT1_TARGET = 5
COMMAND_SET_UNIT2_TARGET = 6
RETRYABLE_ERRORS = (BleakError, TimeoutError, RuntimeError, ValueError)


@dataclass(frozen=True)
class UnitStatus:
    temp_current: int
    temp_target: int
    hysteresis: int
    temp_corr_hot: int
    temp_corr_mid: int
    temp_corr_cold: int
    temp_corr_halt: int


@dataclass(frozen=True)
class FridgeStatus:
    timestamp: str
    device_name: str | None
    device_address: str
    power: bool
    controls_locked: bool
    mode: str
    battery_saver: str | int
    temp_max: int
    temp_min: int
    start_delay_minute: int
    temp_unit: str
    battery_charge_percent: int
    battery_voltage: float
    unit1: UnitStatus
    unit2: UnitStatus | None


BATTERY_SAVER_TO_VALUE = {"Low": 0, "Mid": 1, "High": 2}
MODE_TO_VALUE = {"Max": 0, "Eco": 1}
TEMP_UNIT_TO_VALUE = {"Celsius": 0, "Fahrenheit": 1}


class PacketAssembler:
    def __init__(self) -> None:
        self._buffer = bytearray()

    def feed(self, chunk: bytes | bytearray) -> list[bytes]:
        self._buffer.extend(chunk)
        packets: list[bytes] = []

        while len(self._buffer) >= 3:
            if self._buffer[:2] != b"\xfe\xfe":
                next_header = self._buffer.find(b"\xfe\xfe")
                if next_header == -1:
                    self._buffer.clear()
                    return packets
                del self._buffer[:next_header]

            total_length = 3 + self._buffer[2]
            if len(self._buffer) < total_length:
                return packets

            packets.append(bytes(self._buffer[:total_length]))
            del self._buffer[:total_length]

        return packets


def create_packet(data: bytes) -> bytes:
    packet = b"\xfe\xfe" + struct.pack("B", len(data) + 2) + data
    return packet + struct.pack(">H", sum(packet))


def decode_packet(packet: bytes) -> tuple[int, bytes]:
    if len(packet) < 6:
        raise ValueError(f"packet too short: {packet.hex()}")
    if packet[:2] != b"\xfe\xfe":
        raise ValueError(f"invalid packet header: {packet.hex()}")

    expected_payload_len = packet[2]
    actual_payload_len = len(packet) - 3
    if expected_payload_len != actual_payload_len:
        raise ValueError(
            f"invalid packet length: {expected_payload_len} != {actual_payload_len}"
        )

    expected_checksum = struct.unpack_from(">H", packet[-2:])[0]
    actual_checksum = sum(packet[:-2])
    if expected_checksum not in (actual_checksum, actual_checksum * 2):
        raise ValueError(
            f"invalid packet checksum: {expected_checksum:#x} != {actual_checksum:#x}"
        )

    data = packet[3:-2]
    return data[0], data[1:]


def _decode_unit1(payload: bytes) -> UnitStatus:
    target, hysteresis, corr_hot, corr_mid, corr_cold, corr_halt, current = (
        struct.unpack_from(">bxxbxxbbbbb", payload, 4)
    )
    return UnitStatus(
        temp_current=current,
        temp_target=target,
        hysteresis=hysteresis,
        temp_corr_hot=corr_hot,
        temp_corr_mid=corr_mid,
        temp_corr_cold=corr_cold,
        temp_corr_halt=corr_halt,
    )


def _decode_unit2(payload: bytes) -> UnitStatus | None:
    if len(payload) < 28:
        return None
    target, hysteresis, corr_hot, corr_mid, corr_cold, corr_halt, current = (
        struct.unpack_from(">bxxbbbbbb", payload, 18)
    )
    if current == -128:
        return None
    return UnitStatus(
        temp_current=current,
        temp_target=target,
        hysteresis=hysteresis,
        temp_corr_hot=corr_hot,
        temp_corr_mid=corr_mid,
        temp_corr_cold=corr_cold,
        temp_corr_halt=corr_halt,
    )


def decode_status(
    payload: bytes,
    *,
    device_name: str | None,
    device_address: str,
) -> FridgeStatus:
    if len(payload) < 18:
        raise ValueError(f"status payload too short: {payload.hex()}")

    (
        controls_locked,
        power,
        mode,
        battery_saver,
        temp_max,
        temp_min,
        start_delay,
        temp_unit,
        charge_percent,
        voltage_integer,
        voltage_fraction,
    ) = struct.unpack_from(">??BBxbbxBBxxxxxBBB", payload, 0)

    battery_saver_names = {0: "Low", 1: "Mid", 2: "High"}

    return FridgeStatus(
        timestamp=datetime.now().isoformat(timespec="seconds"),
        device_name=device_name,
        device_address=device_address,
        power=power,
        controls_locked=controls_locked,
        mode="Eco" if mode else "Max",
        battery_saver=battery_saver_names.get(battery_saver, battery_saver),
        temp_max=temp_max,
        temp_min=temp_min,
        start_delay_minute=start_delay,
        temp_unit="Fahrenheit" if temp_unit else "Celsius",
        battery_charge_percent=charge_percent,
        battery_voltage=voltage_integer + voltage_fraction / 10,
        unit1=_decode_unit1(payload),
        unit2=_decode_unit2(payload),
    )


def encode_set_state(status: FridgeStatus, *, power: bool | None = None, temp: int | None = None) -> bytes:
    powered_on = status.power if power is None else power
    target_temp = status.unit1.temp_target if temp is None else temp
    mode = MODE_TO_VALUE[status.mode]
    battery_saver = (
        status.battery_saver
        if isinstance(status.battery_saver, int)
        else BATTERY_SAVER_TO_VALUE[status.battery_saver]
    )
    temp_unit = TEMP_UNIT_TO_VALUE[status.temp_unit]

    return create_packet(
        struct.pack(
            ">B??BBbbbbBBbbbb",
            COMMAND_SET,
            status.controls_locked,
            powered_on,
            mode,
            battery_saver,
            target_temp,
            status.temp_max,
            status.temp_min,
            status.unit1.hysteresis,
            status.start_delay_minute,
            temp_unit,
            status.unit1.temp_corr_hot,
            status.unit1.temp_corr_mid,
            status.unit1.temp_corr_cold,
            status.unit1.temp_corr_halt,
        )
    )


def status_to_json(status: FridgeStatus) -> str:
    return json.dumps(asdict(status), indent=2)


def status_log_entry(status: FridgeStatus) -> dict:
    return {
        "timestamp": status.timestamp,
        "power": status.power,
        "temp_current": status.unit1.temp_current,
        "temp_target": status.unit1.temp_target,
        "temp_unit": status.temp_unit,
        "battery_voltage": status.battery_voltage,
        "battery_charge_percent": status.battery_charge_percent,
        "mode": status.mode,
        "battery_saver": status.battery_saver,
        "device_name": status.device_name,
        "device_address": status.device_address,
        "status": asdict(status),
    }


async def scan_devices(timeout: float) -> list[dict]:
    devices = await BleakScanner.discover(timeout=timeout, return_adv=True)
    result = []
    for device, adv in devices.values():
        result.append(
            {
                "name": device.name,
                "address": device.address,
                "rssi": adv.rssi,
                "service_uuids": adv.service_uuids,
                "looks_like_alpicool": looks_like_fridge(device),
            }
        )
    return sorted(result, key=lambda item: (not item["looks_like_alpicool"], item["name"] or ""))


async def scan_fridge_rssi(device_selector: str | None, timeout: float) -> int | None:
    devices = await BleakScanner.discover(timeout=timeout, return_adv=True)
    for device, adv in devices.values():
        if device_selector and device_selector not in {device.address, device.name}:
            continue
        if not device_selector and not looks_like_fridge(device):
            continue
        return adv.rssi
    return None


def looks_like_fridge(device: BLEDevice) -> bool:
    return bool(device.name and device.name.startswith(FRIDGE_NAME_PREFIXES))


async def find_fridge(device_selector: str | None, timeout: float) -> BLEDevice:
    def matches(device: BLEDevice, _adv) -> bool:
        if device_selector:
            return device_selector in {device.address, device.name}
        return looks_like_fridge(device)

    device = await BleakScanner.find_device_by_filter(matches, timeout=timeout)
    if device is None:
        selector_text = device_selector or ", ".join(FRIDGE_NAME_PREFIXES)
        raise RuntimeError(f"No Alpicool-like BLE device found for {selector_text!r}")
    return device


async def run_with_retries(args: argparse.Namespace, operation):
    attempts = max(1, args.retries)
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            return await operation()
        except RETRYABLE_ERRORS as exc:
            last_error = exc
            if attempt >= attempts:
                break
            print(
                f"attempt {attempt}/{attempts} failed: {exc or exc.__class__.__name__}; retrying",
                file=sys.stderr,
                flush=True,
            )
            await asyncio.sleep(args.retry_delay)
    raise last_error


class AlpicoolClient:
    def __init__(self, device: BLEDevice, *, verbose: bool = False) -> None:
        self.device = device
        self.verbose = verbose
        self._client = BleakClient(device, timeout=10)
        self._assembler = PacketAssembler()
        self._pending: dict[int, asyncio.Future] = {}

    async def __aenter__(self) -> AlpicoolClient:
        await self._client.connect()
        if not self._client.is_connected:
            raise RuntimeError("BLE client did not connect")

        service_uuids = {service.uuid for service in self._client.services}
        if SERVICE_UUID not in service_uuids:
            raise RuntimeError(f"Expected service {SERVICE_UUID} not found")

        await self._client.start_notify(NOTIFY_UUID, self._on_notify)
        return self

    async def __aexit__(self, _exc_type, _exc, _tb) -> None:
        try:
            if self._client.is_connected:
                await self._client.stop_notify(NOTIFY_UUID)
        finally:
            await self._client.disconnect()

    def _on_notify(self, _sender, chunk: bytearray) -> None:
        if self.verbose:
            print(f"notify_chunk={chunk.hex()}")
        for packet in self._assembler.feed(chunk):
            if self.verbose:
                print(f"notify_packet={packet.hex()}")
            command, payload = decode_packet(packet)
            future = self._pending.pop(command, None)
            if future and not future.done():
                future.set_result((command, payload))

    async def _send(
        self,
        command: int,
        payload: bytes = b"",
        *,
        response_commands: tuple[int, ...] | None = None,
        timeout: float = 5,
    ) -> tuple[int, bytes]:
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        for response_command in response_commands or (command,):
            self._pending[response_command] = future
        packet = create_packet(struct.pack("B", command) + payload)
        if self.verbose:
            print(f"write_packet={packet.hex()}")
        await self._client.write_gatt_char(COMMAND_UUID, packet, response=True)
        response_command, response_payload = await asyncio.wait_for(future, timeout=timeout)
        for pending_command, pending_future in list(self._pending.items()):
            if pending_future is future:
                del self._pending[pending_command]
        return response_command, response_payload

    async def _write_packet(
        self,
        packet: bytes,
        *,
        response_commands: tuple[int, ...],
        timeout: float = 5,
    ) -> tuple[int, bytes]:
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        for response_command in response_commands:
            self._pending[response_command] = future
        if self.verbose:
            print(f"write_packet={packet.hex()}")
        await self._client.write_gatt_char(COMMAND_UUID, packet, response=True)
        response_command, response_payload = await asyncio.wait_for(future, timeout=timeout)
        for pending_command, pending_future in list(self._pending.items()):
            if pending_future is future:
                del self._pending[pending_command]
        return response_command, response_payload

    async def query(self) -> FridgeStatus:
        _command, payload = await self._send(COMMAND_QUERY)
        return decode_status(
            payload,
            device_name=self.device.name,
            device_address=self.device.address,
        )

    async def set_temperature(self, temp: int, *, unit: int = 1) -> int:
        if unit not in {1, 2}:
            raise ValueError("unit must be 1 or 2")
        command = COMMAND_SET_UNIT1_TARGET if unit == 1 else COMMAND_SET_UNIT2_TARGET
        response_command, response = await self._send(
            command,
            struct.pack("b", temp),
            response_commands=(command, COMMAND_SET),
        )
        if response_command == COMMAND_SET:
            status = decode_status(
                response,
                device_name=self.device.name,
                device_address=self.device.address,
            )
            target_unit = status.unit1 if unit == 1 else status.unit2
            if target_unit is None:
                raise ValueError(f"unit {unit} not present in set response")
            return target_unit.temp_target
        if len(response) < 1:
            raise ValueError("empty set-temperature response")
        return struct.unpack_from("b", response, 0)[0]

    async def apply(self, *, power: bool | None = None, temp: int | None = None) -> FridgeStatus:
        current = await self.query()
        if temp is not None and (temp < current.temp_min or temp > current.temp_max):
            raise ValueError(
                f"Temperature {temp} outside selectable range "
                f"{current.temp_min}..{current.temp_max} {current.temp_unit}"
            )
        packet = encode_set_state(current, power=power, temp=temp)
        _command, response = await self._write_packet(
            packet,
            response_commands=(COMMAND_SET,),
        )
        return decode_status(
            response,
            device_name=self.device.name,
            device_address=self.device.address,
        )


async def run_status(args: argparse.Namespace) -> None:
    async def operation() -> FridgeStatus:
        device = await find_fridge(args.device, args.timeout)
        async with AlpicoolClient(device, verbose=args.verbose) as fridge:
            return await fridge.query()

    print(status_to_json(await run_with_retries(args, operation)))


async def run_set_temp(args: argparse.Namespace) -> None:
    async def operation() -> dict:
        device = await find_fridge(args.device, args.timeout)
        async with AlpicoolClient(device, verbose=args.verbose) as fridge:
            before = await fridge.query()
            if args.temp < before.temp_min or args.temp > before.temp_max:
                raise ValueError(
                    f"Temperature {args.temp} outside selectable range "
                    f"{before.temp_min}..{before.temp_max} {before.temp_unit}"
                )

            accepted_temp = await fridge.set_temperature(args.temp, unit=args.unit)
            after = await fridge.query()
            return {
                "accepted_temp": accepted_temp,
                "before": asdict(before),
                "after": asdict(after),
            }

    print(json.dumps(await run_with_retries(args, operation), indent=2))


async def run_apply(args: argparse.Namespace) -> None:
    if args.power is None and args.temp is None:
        raise ValueError("apply needs --power, --temp, or both")

    power = None
    if args.power == "on":
        power = True
    elif args.power == "off":
        power = False

    async def operation() -> dict:
        device = await find_fridge(args.device, args.timeout)
        async with AlpicoolClient(device, verbose=args.verbose) as fridge:
            before = await fridge.query()
            after = await fridge.apply(power=power, temp=args.temp)
            return {
                "before": asdict(before),
                "after": asdict(after),
            }

    print(json.dumps(await run_with_retries(args, operation), indent=2))


async def run_record_status(args: argparse.Namespace) -> None:
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    async def operation() -> FridgeStatus:
        device = await find_fridge(args.device, args.timeout)
        async with AlpicoolClient(device, verbose=args.verbose) as fridge:
            return await fridge.query()

    status = await run_with_retries(args, operation)
    entry = status_log_entry(status)
    with output.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, separators=(",", ":")) + "\n")

    print(json.dumps(entry, indent=2))


def summarize_numbers(values: list[float | int]) -> dict | None:
    if not values:
        return None
    ordered = sorted(values)
    return {
        "count": len(values),
        "min": ordered[0],
        "median": ordered[len(ordered) // 2],
        "max": ordered[-1],
        "mean": round(sum(ordered) / len(ordered), 3),
    }


async def run_diagnose_connection(args: argparse.Namespace) -> None:
    results = []

    for attempt in range(1, args.attempts + 1):
        started = time.perf_counter()
        rssi = await scan_fridge_rssi(args.device, args.scan_timeout)
        status = None
        error = None

        try:
            device = await find_fridge(args.device, args.timeout)
            async with AlpicoolClient(device, verbose=args.verbose) as fridge:
                status = await fridge.query()
        except (BleakError, TimeoutError, RuntimeError, ValueError) as exc:
            error = str(exc) or exc.__class__.__name__

        elapsed = round(time.perf_counter() - started, 3)
        result = {
            "attempt": attempt,
            "ok": status is not None,
            "elapsed_seconds": elapsed,
            "scan_rssi": rssi,
            "error": error,
        }
        if status is not None:
            result.update(
                {
                    "power": status.power,
                    "temp_current": status.unit1.temp_current,
                    "temp_target": status.unit1.temp_target,
                    "battery_voltage": status.battery_voltage,
                }
            )
        results.append(result)
        print(json.dumps(result, separators=(",", ":")), flush=True)

        if attempt < args.attempts and args.pause > 0:
            await asyncio.sleep(args.pause)

    successes = [result for result in results if result["ok"]]
    rssis = [result["scan_rssi"] for result in results if result["scan_rssi"] is not None]
    latencies = [result["elapsed_seconds"] for result in successes]

    summary = {
        "attempts": args.attempts,
        "successes": len(successes),
        "failures": args.attempts - len(successes),
        "success_rate": round(len(successes) / args.attempts, 3),
        "rssi": summarize_numbers(rssis),
        "latency_seconds": summarize_numbers(latencies),
        "interpretation": interpret_connection(len(successes), args.attempts, rssis),
    }
    print(json.dumps({"summary": summary}, indent=2))


def interpret_connection(successes: int, attempts: int, rssis: list[int]) -> str:
    success_rate = successes / attempts if attempts else 0
    median_rssi = sorted(rssis)[len(rssis) // 2] if rssis else None

    if success_rate == 1 and median_rssi is not None and median_rssi >= -75:
        return "good"
    if success_rate >= 0.95 and median_rssi is not None and median_rssi >= -85:
        return "usable"
    if success_rate >= 0.9:
        return "marginal-but-probably-usable-for-scheduled-one-shot-commands"
    return "poor"


def parse_schedule(path: Path) -> list[dict]:
    entries = json.loads(path.read_text())
    if not isinstance(entries, list):
        raise ValueError("schedule file must contain a JSON list")

    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("each schedule entry must be an object")
        if "time" not in entry:
            raise ValueError("each schedule entry needs a time")
        datetime.strptime(entry["time"], "%H:%M")
        if "temp" not in entry and "power" not in entry:
            raise ValueError("each schedule entry needs temp, power, or both")
        if "temp" in entry:
            int(entry["temp"])
        if int(entry.get("unit", 1)) != 1:
            raise ValueError("scheduled control currently supports unit 1 only")
        if "power" in entry and entry["power"] not in {"on", "off", True, False}:
            raise ValueError("schedule power must be on/off or true/false")
    return entries


def schedule_entry_time(entry: dict) -> datetime_time:
    return datetime.strptime(entry["time"], "%H:%M").time()


def active_schedule_entry(entries: list[dict], *, now: datetime | None = None) -> dict:
    if not entries:
        raise ValueError("schedule file must contain at least one entry")

    now = now or datetime.now()
    ordered = sorted(entries, key=schedule_entry_time)
    current_time = now.time().replace(second=0, microsecond=0)
    active = ordered[-1]
    for entry in ordered:
        if schedule_entry_time(entry) <= current_time:
            active = entry
        else:
            break
    return active


def schedule_power(entry: dict) -> bool | None:
    if "power" not in entry:
        return None
    value = entry["power"]
    if value in {"on", True}:
        return True
    if value in {"off", False}:
        return False
    raise ValueError("schedule power must be on/off or true/false")


def schedule_temp(entry: dict) -> int | None:
    if "temp" not in entry:
        return None
    return int(entry["temp"])


def status_matches_schedule(status: FridgeStatus, entry: dict) -> bool:
    desired_power = schedule_power(entry)
    desired_temp = schedule_temp(entry)
    if desired_power is not None and status.power != desired_power:
        return False
    if desired_temp is not None and status.unit1.temp_target != desired_temp:
        return False
    return True


def next_occurrence(time_text: str, *, now: datetime | None = None) -> datetime:
    now = now or datetime.now()
    hour, minute = map(int, time_text.split(":"))
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


async def run_schedule(args: argparse.Namespace) -> None:
    entries = parse_schedule(Path(args.schedule_file))
    print(f"Loaded {len(entries)} schedule entries.")
    while True:
        upcoming = sorted(
            ((next_occurrence(entry["time"]), entry) for entry in entries),
            key=lambda item: item[0],
        )
        scheduled_at, entry = upcoming[0]
        wait_seconds = (scheduled_at - datetime.now()).total_seconds()
        print(
            f"Next change at {scheduled_at.isoformat(timespec='minutes')}: "
            f"{json.dumps(entry, separators=(',', ':'))}"
        )
        await asyncio.sleep(max(0, wait_seconds))

        device = await find_fridge(args.device, args.timeout)
        async with AlpicoolClient(device, verbose=args.verbose) as fridge:
            before = await fridge.query()
            temp = schedule_temp(entry)
            if temp is not None and (temp < before.temp_min or temp > before.temp_max):
                raise ValueError(
                    f"Scheduled temperature {temp} outside selectable range "
                    f"{before.temp_min}..{before.temp_max} {before.temp_unit}"
                )
            after = await fridge.apply(power=schedule_power(entry), temp=temp)
            print(
                json.dumps(
                    {
                        "scheduled_at": scheduled_at.isoformat(timespec="seconds"),
                        "before": asdict(before),
                        "after": asdict(after),
                    },
                    indent=2,
                )
            )


async def run_reconcile_schedule(args: argparse.Namespace) -> None:
    entries = parse_schedule(Path(args.schedule_file))
    active_entry = active_schedule_entry(entries)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    async def operation() -> dict:
        device = await find_fridge(args.device, args.timeout)
        async with AlpicoolClient(device, verbose=args.verbose) as fridge:
            before = await fridge.query()
            if status_matches_schedule(before, active_entry):
                return {
                    "action": "noop",
                    "active_schedule": active_entry,
                    "before": before,
                    "after": before,
                }

            temp = schedule_temp(active_entry)
            if temp is not None and (temp < before.temp_min or temp > before.temp_max):
                raise ValueError(
                    f"Scheduled temperature {temp} outside selectable range "
                    f"{before.temp_min}..{before.temp_max} {before.temp_unit}"
                )
            after = await fridge.apply(power=schedule_power(active_entry), temp=temp)
            return {
                "action": "apply",
                "active_schedule": active_entry,
                "before": before,
                "after": after,
            }

    result = await run_with_retries(args, operation)
    entry = status_log_entry(result["after"])
    entry["schedule_action"] = result["action"]
    entry["active_schedule"] = result["active_schedule"]
    entry["before"] = asdict(result["before"])
    with output.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, separators=(",", ":")) + "\n")

    print(json.dumps(entry, indent=2))


async def run_scan(args: argparse.Namespace) -> None:
    print(json.dumps(await scan_devices(args.timeout), indent=2))


def add_common_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--device",
        help="Exact BLE name or macOS CoreBluetooth address. If omitted, auto-detect A1-/AK*/WT- devices.",
    )
    parser.add_argument("--timeout", type=float, default=10, help="BLE scan/connect timeout.")
    parser.add_argument("--verbose", action="store_true", help="Print raw BLE packets.")
    parser.add_argument("--retries", type=int, default=5, help="Retry count for BLE connect/query actions.")
    parser.add_argument("--retry-delay", type=float, default=5, help="Seconds to wait between retries.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Control an Alpicool-compatible BLE fridge.")
    subcommands = parser.add_subparsers(dest="command", required=True)

    scan = subcommands.add_parser("scan", help="List nearby BLE devices.")
    scan.add_argument("--timeout", type=float, default=10)
    scan.set_defaults(func=run_scan)

    status = subcommands.add_parser("status", help="Read current fridge status.")
    add_common_flags(status)
    status.set_defaults(func=run_status)

    set_temp = subcommands.add_parser("set-temp", help="Set target temperature.")
    add_common_flags(set_temp)
    set_temp.add_argument("temp", type=int)
    set_temp.add_argument("--unit", type=int, default=1, choices=[1, 2])
    set_temp.set_defaults(func=run_set_temp)

    apply = subcommands.add_parser("apply", help="Apply power and/or temperature in one BLE write.")
    add_common_flags(apply)
    apply.add_argument("--power", choices=["on", "off"])
    apply.add_argument("--temp", type=int)
    apply.set_defaults(func=run_apply)

    record_status = subcommands.add_parser(
        "record-status",
        help="Read status and append one JSONL tracking sample.",
    )
    add_common_flags(record_status)
    record_status.add_argument(
        "--output",
        default="data/fridge-status.jsonl",
        help="JSONL output path.",
    )
    record_status.set_defaults(func=run_record_status)

    diagnose = subcommands.add_parser(
        "diagnose-connection",
        help="Run repeated scan/status attempts and summarize connection quality.",
    )
    add_common_flags(diagnose)
    diagnose.add_argument("--attempts", type=int, default=12)
    diagnose.add_argument("--scan-timeout", type=float, default=3)
    diagnose.add_argument("--pause", type=float, default=1)
    diagnose.set_defaults(func=run_diagnose_connection)

    schedule = subcommands.add_parser("schedule", help="Run a local schedule loop.")
    add_common_flags(schedule)
    schedule.add_argument("schedule_file", help="JSON schedule file.")
    schedule.set_defaults(func=run_schedule)

    reconcile_schedule = subcommands.add_parser(
        "reconcile-schedule",
        help="Apply the schedule state that should be active now and append one tracking sample.",
    )
    add_common_flags(reconcile_schedule)
    reconcile_schedule.add_argument("schedule_file", help="JSON schedule file.")
    reconcile_schedule.add_argument(
        "--output",
        default="data/fridge-status.jsonl",
        help="JSONL output path.",
    )
    reconcile_schedule.set_defaults(func=run_reconcile_schedule)

    return parser


async def main_async(argv: Iterable[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        await args.func(args)
    except (BleakError, TimeoutError, RuntimeError, ValueError) as exc:
        raise SystemExit(f"error: {exc}") from exc


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
