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
    torque_cut_pct: float = 0.0
    active: bool = False
    sensor_fault: bool = False


@dataclass(frozen=True)
class ClutchState:
    slip_pct: float = 0.0
    severity: str = "NONE"


@dataclass(frozen=True)
class LightingState:
    left_indicator: bool = False
    right_indicator: bool = False
    high_beam: bool = False
    neutral: bool = False
    brake: bool = False
    oil_warning: bool = False


@dataclass(frozen=True)
class EngineState:
    rpm: int = 0
    rpm_redline: int = 12000
    speed_mph: float = 0.0
    gear: str = "?"
    boost_psi: float = 0.0
    target_boost_psi: float = 0.0
    wastegate_duty_pct: float = 0.0
    afr_left: float = 0.0
    afr_right: float = 0.0
    spark_advance_deg: float = 0.0
    knock_events: int = 0
    throttle_pct: float = 0.0
    engine_load_pct: float = 0.0


@dataclass(frozen=True)
class TemperaturesState:
    coolant_temp_f: float = -1.0
    oil_temp_f: float = -1.0
    oil_pressure_psi: float = 0.0
    battery_voltage: float = -1.0
    intake_temp_f: float = 0.0
    exhaust_temp_f: float = 0.0
    alternator_temp_f: float = 0.0


@dataclass(frozen=True)
class EnvironmentState:
    mode: str = "ECO"
    fuel_type: str = "93"
    flame_mode_enabled: bool = False
    rev_limiter_strategy: str = "FUEL CUT"
    ethanol_content_pct: float = -1.0
    ambient_temp_f: float = 70.0
    gps_lock: bool = False
    rain: bool = False
    time: datetime = field(default_factory=datetime.now)
    brightness_pct: float = 75.0
    message_line: str = ""
    fuel_level_pct: float = -1.0


@dataclass(frozen=True)
class EconomyState:
    injector_pulse_width_ms: float = 0.0
    injector_duty_pct: float = 0.0
    fuel_flow_cc_min: float = 0.0
    instant_mpg: float = -1.0
    average_mpg: float = -1.0
    miles_to_empty: float = -1.0
    distance_miles: float = 0.0
    fuel_used_gal: float = 0.0
    source: str = "EST"


@dataclass(frozen=True)
class CANFrameRecord:
    arbitration_id: int = 0
    name: str = "UNKNOWN"
    data_hex: str = ""
    direction: str = "RX"
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class ServiceReading:
    label: str = ""
    value: str = ""


@dataclass(frozen=True)
class ServiceFlag:
    label: str = ""
    active: bool = False


@dataclass(frozen=True)
class ServiceStatus:
    recent_can_frames: Tuple[CANFrameRecord, ...] = field(default_factory=tuple)
    sensor_voltages: Tuple[ServiceReading, ...] = field(default_factory=tuple)
    pin_states: Tuple[ServiceFlag, ...] = field(default_factory=tuple)
    relay_states: Tuple[ServiceFlag, ...] = field(default_factory=tuple)
    firmware_versions: Tuple[ServiceReading, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class StateSnapshot:
    engine: EngineState = field(default_factory=EngineState)
    temps: TemperaturesState = field(default_factory=TemperaturesState)
    air_shot: AirShotState = field(default_factory=AirShotState)
    wmi: WMIState = field(default_factory=WMIState)
    traction: TractionState = field(default_factory=TractionState)
    clutch: ClutchState = field(default_factory=ClutchState)
    lighting: LightingState = field(default_factory=LightingState)
    environment: EnvironmentState = field(default_factory=EnvironmentState)
    economy: EconomyState = field(default_factory=EconomyState)
    service: ServiceStatus = field(default_factory=ServiceStatus)
    shift_light: bool = False
    faults: Tuple[str, ...] = field(default_factory=tuple)
    advisories: Tuple[str, ...] = field(default_factory=tuple)
