"""State snapshot dataclasses for the HUD renderer."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Tuple


@dataclass(frozen=True)
class AirShotState:
    pressure_psi: float = 0.0
    charges_remaining: int = 0
    is_firing: bool = False


@dataclass(frozen=True)
class WMIState:
    tank_level_pct: float = 0.0
    commanded_flow_cc_min: float = 0.0
    actual_flow_cc_min: float = 0.0
    fault_active: bool = False


@dataclass(frozen=True)
class TractionState:
    slip_pct: float = 0.0
    wheelie_pitch_deg: float = 0.0
    intervention_level: str = ""


@dataclass(frozen=True)
class EngineState:
    rpm: int = 0
    rpm_redline: int = 12000
    speed_mph: float = 0.0
    gear: str = "N"
    boost_psi: float = 0.0
    target_boost_psi: float = 0.0
    wastegate_duty_pct: float = 0.0
    afr_left: float = 0.0
    afr_right: float = 0.0
    spark_advance_deg: float = 0.0
    knock_events: int = 0


@dataclass(frozen=True)
class TemperaturesState:
    coolant_temp_f: float = 0.0
    oil_temp_f: float = 0.0
    oil_pressure_psi: float = 0.0
    battery_voltage: float = 12.5
    intake_temp_f: float = 0.0
    exhaust_temp_f: float = 0.0


@dataclass(frozen=True)
class EnvironmentState:
    mode: str = "ECO"
    fuel_type: str = "93"
    ambient_temp_f: float = 70.0
    gps_lock: bool = False
    rain: bool = False
    time: datetime = field(default_factory=datetime.now)
    brightness_pct: float = 75.0
    message_line: str = ""


@dataclass(frozen=True)
class StateSnapshot:
    engine: EngineState = field(default_factory=EngineState)
    temps: TemperaturesState = field(default_factory=TemperaturesState)
    air_shot: AirShotState = field(default_factory=AirShotState)
    wmi: WMIState = field(default_factory=WMIState)
    traction: TractionState = field(default_factory=TractionState)
    environment: EnvironmentState = field(default_factory=EnvironmentState)
    shift_light: bool = False
    faults: Tuple[str, ...] = field(default_factory=tuple)
