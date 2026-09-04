"""Check (or refresh) firmware constants against the shared thermal JSON."""
from __future__ import annotations

import argparse
import binascii
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "thermal_system.json"
FIRMWARE = ROOT / "arduino" / "teensy41" / "albatross_thermal_node"
PROTOCOL_HEADER = FIRMWARE / "thermal_protocol.h"
SENSOR_SOURCE = FIRMWARE / "sensor_config.cpp"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-crc", action="store_true")
    args = parser.parse_args()
    payload = CONFIG.read_bytes()
    config = json.loads(payload)
    protocol = config["protocol"]
    header = PROTOCOL_HEADER.read_text(encoding="utf-8")
    expected = {
        "VERSION": protocol["version"], "NODE_ID": protocol["node_id"],
        "CAN_BITRATE": protocol["can_bitrate"], "HEARTBEAT_ID": protocol["heartbeat_id"],
        "VALUE_BASE_ID": protocol["value_base_id"], "STATUS_BASE_ID": protocol["status_base_id"],
        "CONFIG_ID": protocol["config_id"], "FAULT_BASE_ID": protocol["fault_base_id"],
        "RAW_BASE_ID": protocol["raw_base_id"],
    }
    errors: list[str] = []
    for name, value in expected.items():
        match = re.search(rf"\b{name}\s*=\s*(0x[0-9A-Fa-f]+|\d+)", header)
        if not match or int(match.group(1), 0) != value:
            errors.append(f"{name}: firmware does not match JSON value {value}")
    source = SENSOR_SOURCE.read_text(encoding="utf-8")
    firmware_rows = re.findall(r"(?:TC|NTC|CLT|RTD|OFF)\((\d+),\"([^\"]+)\"", source)
    expected_rows = [(str(sensor["id"]), sensor["key"]) for sensor in config["sensors"]]
    if firmware_rows != expected_rows:
        errors.append("firmware sensor ID/key order does not match JSON channels 1..32")
    for sensor in config["sensors"]:
        if f'"{sensor["key"]}"' not in source:
            errors.append(f'{sensor["key"]}: missing from firmware sensor table')
    crc = binascii.crc32(payload) & 0xFFFFFFFF
    if args.write_crc:
        header = re.sub(r"CONFIG_CRC32\s*=\s*0x[0-9A-Fa-f]+UL", f"CONFIG_CRC32 = 0x{crc:08X}UL", header)
        PROTOCOL_HEADER.write_text(header, encoding="utf-8")
    else:
        match = re.search(r"CONFIG_CRC32\s*=\s*0x([0-9A-Fa-f]+)UL", header)
        if not match or int(match.group(1), 16) != crc:
            errors.append(f"CONFIG_CRC32: run {Path(__file__).name} --write-crc")
    if errors:
        print("\n".join(errors))
        return 1
    print(f"thermal configuration OK: 32 channels, CRC32 0x{crc:08X}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
