"""Immutable thermal state consumed by analytics, logging, and the HUD."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Mapping


class SensorStatus(IntEnum):
    VALID = 0
    OPEN_CIRCUIT = 1
    SHORT_TO_GROUND = 2
    SHORT_TO_SUPPLY = 3
    OUT_OF_RANGE = 4
    IMPLAUSIBLE_RATE = 5
    STALE = 6
    FRONT_END_FAULT = 7
    NOT_CONFIGURED = 8


@dataclass(frozen=True)
class ThermalReading:
    sensor_id: int
    key: str
    name: str
    temperature_c: float | None = None
    raw_temperature_c: float | None = None
    raw_value: int | None = None
    filtered_temperature_c: float | None = None
    status: SensorStatus = SensorStatus.NOT_CONFIGURED
    age_ms: float = float("inf")
    thermal_abs: float = 0.0
    expected_c: float | None = None
    residual_c: float | None = None
    thermal_dev: float = 0.0
    derivative_c_s: float = 0.0
    ambient_delta_c: float | None = None
    baseline_samples: int = 0
    maximum_c: float | None = None

    @property
    def valid(self) -> bool:
        return self.status == SensorStatus.VALID and self.temperature_c is not None


@dataclass(frozen=True)
class ThermalSnapshot:
    online: bool = False
    protocol_version: int = 0
    node_id: int = 0
    uptime_s: int = 0
    sequence: int = 0
    config_crc32: int = 0
    config_version: str = "unknown"
    can_age_ms: float = float("inf")
    readings: Mapping[str, ThermalReading] = field(default_factory=dict)
    derived: Mapping[str, float | None] = field(default_factory=dict)
    overall_status: str = "DATA FAULT"
    thermal_state: str = "COLD"
    alerts: tuple[str, ...] = ()
    baseline_status: str = "INSUFFICIENT BASELINE"

    def get(self, key: str) -> ThermalReading | None:
        return self.readings.get(key)
