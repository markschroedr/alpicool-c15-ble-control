import struct
from datetime import datetime
from pathlib import Path

from scripts.alpicool_ble import (
    COMMAND_QUERY,
    PacketAssembler,
    active_schedule_entry,
    create_packet,
    decode_packet,
    decode_status,
    parse_schedule,
    schedule_power,
    schedule_temp,
    status_log_entry,
    status_matches_schedule,
)


STATUS_PACKET_HEX = (
    "fefe2101000100011314ec0201000000"
    "fd0014640e03000000000000000080000100053d"
)


def test_create_query_packet():
    assert create_packet(struct.pack("B", COMMAND_QUERY)).hex() == "fefe03010200"


def test_packet_assembler_reassembles_fragmented_notification():
    packet = bytes.fromhex(STATUS_PACKET_HEX)
    assembler = PacketAssembler()

    assert assembler.feed(packet[:16]) == []
    assert assembler.feed(packet[16:20]) == []
    assert assembler.feed(packet[20:]) == [packet]


def test_decode_status_packet():
    command, payload = decode_packet(bytes.fromhex(STATUS_PACKET_HEX))
    status = decode_status(payload, device_name="AK1-EXAMPLE", device_address="test")

    assert command == COMMAND_QUERY
    assert status.power is True
    assert status.mode == "Max"
    assert status.temp_min == -20
    assert status.temp_max == 20
    assert status.temp_unit == "Celsius"
    assert status.battery_voltage == 14.3
    assert status.unit1.temp_target == 19
    assert status.unit1.temp_current == 20
    assert status.unit2 is None


def test_status_log_entry_contains_flat_tracking_fields():
    _command, payload = decode_packet(bytes.fromhex(STATUS_PACKET_HEX))
    status = decode_status(payload, device_name="AK1-EXAMPLE", device_address="test")
    entry = status_log_entry(status)

    assert entry["power"] is True
    assert entry["temp_current"] == 20
    assert entry["temp_target"] == 19
    assert entry["temp_unit"] == "Celsius"
    assert entry["battery_voltage"] == 14.3
    assert entry["status"]["unit1"]["temp_current"] == 20


def test_active_schedule_entry_wraps_overnight():
    entries = [
        {"time": "04:00", "power": "off"},
        {"time": "17:00", "power": "on", "temp": 16},
        {"time": "23:00", "temp": 18},
        {"time": "02:00", "temp": 20},
    ]

    assert active_schedule_entry(entries, now=datetime(2026, 7, 6, 1, 30))["temp"] == 18
    assert active_schedule_entry(entries, now=datetime(2026, 7, 6, 2, 30))["temp"] == 20
    assert active_schedule_entry(entries, now=datetime(2026, 7, 6, 16, 30))["power"] == "off"
    assert active_schedule_entry(entries, now=datetime(2026, 7, 6, 17, 30))["temp"] == 16


def test_example_schedule_supports_temperature_and_power_actions():
    entries = parse_schedule(Path(__file__).resolve().parents[1] / "schedule.example.json")

    assert any(entry == {"time": "04:00", "power": "off"} for entry in entries)
    assert any(entry.get("power") == "on" and entry.get("temp") == 16 for entry in entries)


def test_schedule_helpers_and_match_status():
    _command, payload = decode_packet(bytes.fromhex(STATUS_PACKET_HEX))
    status = decode_status(payload, device_name="AK1-EXAMPLE", device_address="test")

    assert schedule_power({"power": "on"}) is True
    assert schedule_power({"power": "off"}) is False
    assert schedule_power({}) is None
    assert schedule_temp({"temp": "19"}) == 19
    assert schedule_temp({}) is None

    assert status_matches_schedule(status, {"power": "on", "temp": 19}) is True
    assert status_matches_schedule(status, {"temp": 20}) is False
    assert status_matches_schedule(status, {"power": "off"}) is False
