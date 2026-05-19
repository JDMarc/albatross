"""Fault event logging and export helpers."""
from __future__ import annotations

import json
import os
import shutil
import string
import threading
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from albatross_pi.canbus.ids import FAULT_CODE_MAP
from albatross_pi.state.snapshot import StateSnapshot


FAULT_NAME_TO_CODE = {name: code for code, name in FAULT_CODE_MAP.items()}
DRIVE_REMOVABLE = 2


def _safe_float(value: float) -> float:
    return round(float(value), 3)


def _snapshot_dict(snapshot: StateSnapshot) -> dict[str, Any]:
    if is_dataclass(snapshot):
        data = asdict(snapshot)
    else:
        data = {}
    env = data.get("environment", {})
    if isinstance(env.get("time"), datetime):
        env["time"] = env["time"].isoformat()
    return data


def fault_reason(fault: str, snapshot: StateSnapshot) -> str:
    engine = snapshot.engine
    temps = snapshot.temps
    env = snapshot.environment
    wmi = snapshot.wmi
    air = snapshot.air_shot
    traction = snapshot.traction
    clutch = snapshot.clutch
    reasons = {
        "WMI FLOW LOW": f"WMI commanded {_safe_float(wmi.commanded_flow_cc_min)} cc/min but measured {_safe_float(wmi.actual_flow_cc_min)} cc/min.",
        "EGT HIGH": f"Exhaust temperature {_safe_float(temps.exhaust_temp_f)} F exceeded thermal warning threshold.",
        "CAN TIMEOUT": "Expected CAN data timed out.",
        "IMU FAULT": "IMU data missing, stale, or outside sanity range.",
        "AIR SHOT LOW": f"Air Shot pressure {_safe_float(air.pressure_psi)} psi was below armed/requested threshold.",
        "LOW OIL PRESS": f"Oil pressure {_safe_float(temps.oil_pressure_psi)} psi was low at {int(engine.rpm)} rpm.",
        "OVERBOOST": f"Boost {_safe_float(engine.boost_psi)} psi exceeded request {_safe_float(engine.target_boost_psi)} psi plus tolerance.",
        "KNOCK ESCALATE": f"Knock event count {engine.knock_events} exceeded warning threshold.",
        "CRITICAL OIL PRESS": f"Oil pressure {_safe_float(temps.oil_pressure_psi)} psi was critically low at {int(engine.rpm)} rpm.",
        "COOLANT HOT": f"Coolant temperature {_safe_float(temps.coolant_temp_f)} F exceeded hard thermal ceiling.",
        "ECU STALE": "ECU telemetry was stale or implausible for current throttle/rpm state.",
        "CAN STALE": "Aggregate CAN telemetry timestamp exceeded freshness window.",
        "SPEED SENSOR": f"Wheel/speed data was implausible: {int(engine.rpm)} rpm, gear {engine.gear}, speed {_safe_float(engine.speed_mph)} mph.",
        "GEAR SENSOR": f"Gear value {engine.gear!r} was invalid or unavailable.",
        "CLUTCH SLIP": f"Clutch slip {_safe_float(clutch.slip_pct)}% severity {clutch.severity}.",
        "LOW FUEL": f"Fuel level {_safe_float(env.fuel_level_pct)}% crossed reserve threshold.",
        "WMI TANK EMPTY": f"WMI tank level {_safe_float(wmi.tank_level_pct)}% was empty/near-empty while WMI or boost was requested.",
        "WMI PUMP FAULT": "Arduino reported an aggregate WMI pump/status fault.",
        "WMI PRESSURE LOW": f"WMI flow/pressure response was low while commanded flow was {_safe_float(wmi.commanded_flow_cc_min)} cc/min.",
        "WASTEGATE STUCK": f"Wastegate duty {_safe_float(engine.wastegate_duty_pct)}% did not produce expected boost response.",
        "BOOST CONTROL ERROR": f"Boost {_safe_float(engine.boost_psi)} psi diverged from request {_safe_float(engine.target_boost_psi)} psi under load.",
        "CYL EGT BOOST MISMATCH": f"High EGT {_safe_float(temps.exhaust_temp_f)} F with low/implausible boost {_safe_float(engine.boost_psi)} psi under load.",
        "INTAKE AIR HOT": f"Intake air temperature {_safe_float(temps.intake_temp_f)} F exceeded derate threshold.",
        "BATTERY LOW": f"Battery voltage {_safe_float(temps.battery_voltage)} V was below under-voltage threshold.",
        "BATTERY HIGH": f"Battery voltage {_safe_float(temps.battery_voltage)} V exceeded over-voltage threshold.",
        "SENSOR RANGE FAULT": "One or more critical sensor values were out of plausible range.",
        "ENGINE RUN SWITCH OFF": "Safety supervisor commanded engine run switch OFF.",
        "ENGINE SHUTDOWN REQUEST": "Safety supervisor requested engine shutdown after escalation criteria persisted.",
        "SLOW TURBO SPOOL": f"Target {_safe_float(engine.target_boost_psi)} psi was requested but boost reached only {_safe_float(engine.boost_psi)} psi under load.",
    }
    if fault == "KNOCK":
        return f"Knock event count {engine.knock_events} exceeded safety supervisor threshold."
    return reasons.get(fault, "Fault was reported by the HUD, CAN decoder, or safety supervisor.")


def engine_status(snapshot: StateSnapshot) -> dict[str, Any]:
    return {
        "rpm": int(snapshot.engine.rpm),
        "speed_mph": _safe_float(snapshot.engine.speed_mph),
        "gear": snapshot.engine.gear,
        "mode": snapshot.environment.mode,
        "fuel_type": snapshot.environment.fuel_type,
        "ethanol_content_pct": _safe_float(snapshot.environment.ethanol_content_pct),
        "boost_psi": _safe_float(snapshot.engine.boost_psi),
        "target_boost_psi": _safe_float(snapshot.engine.target_boost_psi),
        "wastegate_duty_pct": _safe_float(snapshot.engine.wastegate_duty_pct),
        "throttle_pct": _safe_float(snapshot.engine.throttle_pct),
        "engine_load_pct": _safe_float(snapshot.engine.engine_load_pct),
        "afr_left": _safe_float(snapshot.engine.afr_left),
        "afr_right": _safe_float(snapshot.engine.afr_right),
        "knock_events": int(snapshot.engine.knock_events),
        "coolant_temp_f": _safe_float(snapshot.temps.coolant_temp_f),
        "oil_temp_f": _safe_float(snapshot.temps.oil_temp_f),
        "oil_pressure_psi": _safe_float(snapshot.temps.oil_pressure_psi),
        "intake_temp_f": _safe_float(snapshot.temps.intake_temp_f),
        "exhaust_temp_f": _safe_float(snapshot.temps.exhaust_temp_f),
        "battery_voltage": _safe_float(snapshot.temps.battery_voltage),
        "fuel_level_pct": _safe_float(snapshot.environment.fuel_level_pct),
        "instant_mpg": _safe_float(snapshot.economy.instant_mpg),
        "average_mpg": _safe_float(snapshot.economy.average_mpg),
        "miles_to_empty": _safe_float(snapshot.economy.miles_to_empty),
        "fuel_flow_cc_min": _safe_float(snapshot.economy.fuel_flow_cc_min),
        "injector_pulse_width_ms": _safe_float(snapshot.economy.injector_pulse_width_ms),
        "economy_source": snapshot.economy.source,
        "wmi_tank_level_pct": _safe_float(snapshot.wmi.tank_level_pct),
        "wmi_commanded_flow_cc_min": _safe_float(snapshot.wmi.commanded_flow_cc_min),
        "wmi_actual_flow_cc_min": _safe_float(snapshot.wmi.actual_flow_cc_min),
        "wmi_fault_active": bool(snapshot.wmi.fault_active),
        "traction_level": snapshot.traction.intervention_level,
        "traction_slip_pct": _safe_float(snapshot.traction.slip_pct),
        "traction_torque_cut_pct": _safe_float(snapshot.traction.torque_cut_pct),
        "traction_active": bool(snapshot.traction.active),
        "traction_sensor_fault": bool(snapshot.traction.sensor_fault),
        "clutch_slip_pct": _safe_float(snapshot.clutch.slip_pct),
        "clutch_severity": snapshot.clutch.severity,
        "air_shot_pressure_psi": _safe_float(snapshot.air_shot.pressure_psi),
        "air_shot_charges_remaining": int(snapshot.air_shot.charges_remaining),
        "air_shot_firing": bool(snapshot.air_shot.is_firing),
    }


def _is_accessible_dir(path: Path) -> bool:
    try:
        return path.exists() and path.is_dir()
    except OSError:
        return False


def _windows_drive_type(root: Path) -> int | None:
    try:
        import ctypes

        return int(ctypes.windll.kernel32.GetDriveTypeW(str(root)))
    except (AttributeError, OSError, ValueError):
        return None


def _iter_windows_drive_roots() -> Iterable[Path]:
    for letter in string.ascii_uppercase[3:]:
        root = Path(f"{letter}:\\")
        if _windows_drive_type(root) != DRIVE_REMOVABLE:
            continue
        if _is_accessible_dir(root):
            yield root


def find_usb_log_destination() -> Path | None:
    env_target = os.environ.get("ALBATROSS_LOG_EXPORT_DIR")
    if env_target:
        target = Path(env_target).expanduser()
        if _is_accessible_dir(target):
            return target
    user = os.environ.get("USER") or os.environ.get("USERNAME") or ""
    candidates = [
        Path("/media") / user,
        Path("/run/media") / user,
        Path("/mnt"),
        Path("/media"),
    ]
    for parent in candidates:
        if _is_accessible_dir(parent):
            try:
                children = sorted(parent.iterdir())
            except OSError:
                continue
            for child in children:
                if _is_accessible_dir(child):
                    return child
    for root in _iter_windows_drive_roots():
        return root
    return None


class FaultLogger:
    """Append one JSONL event when a fault first becomes active."""

    def __init__(self, log_dir: Path | str = "logs") -> None:
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._active_faults: set[str] = set()
        self._lock = threading.Lock()
        date = datetime.now().strftime("%Y-%m-%d")
        self._event_log = self.log_dir / f"fault_events_{date}.jsonl"
        self._summary_log = self.log_dir / f"fault_events_{date}.txt"

    def update(self, faults: Iterable[str], snapshot: StateSnapshot) -> None:
        current = set(faults)
        new_faults = sorted(current - self._active_faults)
        with self._lock:
            self._active_faults = current
        for fault in new_faults:
            self._write_fault_event(fault, snapshot)

    def log_fault(self, fault: str, snapshot: StateSnapshot) -> None:
        self._write_fault_event(fault, snapshot)

    def _write_fault_event(self, fault: str, snapshot: StateSnapshot) -> None:
        now = datetime.now()
        event = {
            "timestamp": now.isoformat(timespec="milliseconds"),
            "code": f"0x{FAULT_NAME_TO_CODE.get(fault, 0):08X}",
            "fault": fault,
            "reason": fault_reason(fault, snapshot),
            "engine_status": engine_status(snapshot),
            "snapshot": _snapshot_dict(snapshot),
        }
        line = json.dumps(event, sort_keys=True)
        summary = self._format_summary(event)
        with self._lock:
            with self._event_log.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
            with self._summary_log.open("a", encoding="utf-8") as handle:
                handle.write(summary + "\n")

    @staticmethod
    def _format_summary(event: dict[str, Any]) -> str:
        status = event["engine_status"]
        return (
            f"{event['timestamp']} {event['code']} {event['fault']}: {event['reason']} | "
            f"rpm={status['rpm']} speed={status['speed_mph']}mph gear={status['gear']} "
            f"mode={status['mode']} fuel={status['fuel_type']} e={status['ethanol_content_pct']}% "
            f"boost={status['boost_psi']}psi req={status['target_boost_psi']}psi "
            f"wg={status['wastegate_duty_pct']}% tps={status['throttle_pct']}% "
            f"oil={status['oil_pressure_psi']}psi/{status['oil_temp_f']}F "
            f"coolant={status['coolant_temp_f']}F iat={status['intake_temp_f']}F "
            f"egt={status['exhaust_temp_f']}F batt={status['battery_voltage']}V "
            f"mpg={status['average_mpg']} range={status['miles_to_empty']}mi "
            f"wmi={status['wmi_actual_flow_cc_min']}/{status['wmi_commanded_flow_cc_min']}ccm"
        )

    def export_to_usb(self) -> str:
        destination_root = find_usb_log_destination()
        if destination_root is None:
            return "NO USB"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        destination = destination_root / f"albatross_logs_{timestamp}"
        shutil.copytree(self.log_dir, destination, dirs_exist_ok=True)
        return f"EXPORTED {destination.name}"
