"""Replay recorded thermal JSONL through the live thermal model interface."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

from .model import SensorStatus, ThermalReading, ThermalSnapshot


def replay_jsonl(path: Path | str) -> Iterator[ThermalSnapshot]:
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            readings = {
                key: ThermalReading(
                    sensor_id=index + 1, key=key, name=key.replace("_", " ").title(),
                    temperature_c=value.get("temp_c"), filtered_temperature_c=value.get("temp_c"),
                    raw_value=value.get("raw"), status=SensorStatus[value.get("status", "STALE")],
                    age_ms=float(value.get("age_ms", 0)), thermal_abs=float(value.get("thermal_abs", 0)),
                    expected_c=value.get("expected_c"), residual_c=value.get("residual_c"),
                    thermal_dev=float(value.get("thermal_dev", 0)), derivative_c_s=float(value.get("dt_dt_c_s", 0)),
                    ambient_delta_c=value.get("ambient_delta_c"),
                )
                for index, (key, value) in enumerate(row.get("readings", {}).items())
            }
            yield ThermalSnapshot(
                online=bool(row.get("node_online", False)), uptime_s=int(row.get("node_uptime_s", 0)),
                config_version=str(row.get("configuration_version", "unknown")), readings=readings,
                derived=row.get("derived", {}), overall_status=str(row.get("overall_status", "DATA FAULT")),
                thermal_state=str(row.get("thermal_state", "THERMAL FAULT")),
            )
