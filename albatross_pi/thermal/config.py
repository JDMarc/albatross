"""Versioned thermal configuration loader and validation."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "thermal_system.json"


@dataclass(frozen=True)
class ProtocolConfig:
    version: int
    node_id: int
    can_bitrate: int
    heartbeat_id: int
    value_base_id: int
    status_base_id: int
    config_id: int
    fault_base_id: int
    raw_base_id: int
    temperature_scale_c: float
    invalid_raw: int
    heartbeat_timeout_ms: int


@dataclass(frozen=True)
class SensorDefinition:
    sensor_id: int
    key: str
    name: str
    side: str
    location: str
    technology: str
    source_bus: str
    source_channel: int
    sample_hz: float
    report_hz: float
    filter_tau_s: float
    derivative_tau_s: float
    valid_raw: tuple[int, int]
    valid_c: tuple[float, float]
    curve: tuple[tuple[float, float], ...]
    warning_c: float
    critical_c: float
    component: str
    enabled: bool
    pair: str | None = None
    ambient_reference: str | None = None


@dataclass(frozen=True)
class ThermalConfig:
    schema_version: int
    configuration_version: str
    protocol: ProtocolConfig
    sensors: tuple[SensorDefinition, ...]

    @property
    def by_key(self) -> dict[str, SensorDefinition]:
        return {sensor.key: sensor for sensor in self.sensors}

    @property
    def by_id(self) -> dict[int, SensorDefinition]:
        return {sensor.sensor_id: sensor for sensor in self.sensors}


def _sensor(row: dict[str, Any]) -> SensorDefinition:
    return SensorDefinition(
        sensor_id=int(row["id"]), key=str(row["key"]), name=str(row["name"]),
        side=str(row["side"]), location=str(row["location"]), technology=str(row["technology"]),
        source_bus=str(row["source"]["bus"]), source_channel=int(row["source"]["channel"]),
        sample_hz=float(row["sample_hz"]), report_hz=float(row["report_hz"]),
        filter_tau_s=float(row["filter_tau_s"]), derivative_tau_s=float(row["derivative_tau_s"]),
        valid_raw=(int(row["valid_raw"][0]), int(row["valid_raw"][1])),
        valid_c=(float(row["valid_c"][0]), float(row["valid_c"][1])),
        curve=tuple((float(point[0]), float(point[1])) for point in row["curve"]),
        warning_c=float(row["warning_c"]), critical_c=float(row["critical_c"]),
        pair=row.get("pair"), ambient_reference=row.get("ambient_reference"),
        component=str(row["component"]), enabled=bool(row["enabled"]),
    )


def load_thermal_config(path: Path | str | None = None) -> ThermalConfig:
    source = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    raw = json.loads(source.read_text(encoding="utf-8"))
    protocol = ProtocolConfig(**raw["protocol"])
    sensors = tuple(_sensor(row) for row in raw["sensors"])
    ids = [sensor.sensor_id for sensor in sensors]
    keys = [sensor.key for sensor in sensors]
    if ids != list(range(1, 33)):
        raise ValueError("thermal sensor IDs must be contiguous 1..32")
    if len(set(keys)) != len(keys):
        raise ValueError("thermal sensor keys must be unique")
    if protocol.value_base_id + 7 >= protocol.status_base_id:
        raise ValueError("thermal value and status CAN ranges overlap")
    for sensor in sensors:
        if not sensor.curve or any(a[0] >= b[0] for a, b in zip(sensor.curve, sensor.curve[1:])):
            raise ValueError(f"{sensor.key}: normalization curve temperatures must increase")
        if sensor.warning_c >= sensor.critical_c:
            raise ValueError(f"{sensor.key}: warning must be below critical")
    return ThermalConfig(
        schema_version=int(raw["schema_version"]),
        configuration_version=str(raw["configuration_version"]),
        protocol=protocol,
        sensors=sensors,
    )
