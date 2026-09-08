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
    from generate_thermal_config import outputs
    for path, content in outputs().items():
        if args.write_crc:
            path.write_text(content, encoding="utf-8")
        elif path.read_text() != content:
            errors.append(f"Stale generated thermal configuration: {path.name}")
    if errors:
        print("\n".join(errors))
        return 1
    print("thermal configuration OK: protocol constants and all generated fields match")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
