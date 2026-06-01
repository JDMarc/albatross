"""Fault event logging and export helpers."""
from __future__ import annotations

import json
import os
import shutil
import string
import threading
import time
from collections import deque
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from albatross_pi.canbus.ids import FAULT_CODE_MAP
from albatross_pi.state.snapshot import StateSnapshot


FAULT_NAME_TO_CODE = {name: code for code, name in FAULT_CODE_MAP.items()}
DRIVE_REMOVABLE = 2
PRE_FAULT_SECONDS = 30.0
PRE_FAULT_SAMPLE_INTERVAL_S = 0.1


def _safe_float(value: float) -> float:
    return round(float(value), 3)


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, set):
        return sorted(_json_safe(item) for item in value)
    if isinstance(value, Path):
        return str(value)
    return value


def _snapshot_dict(snapshot: StateSnapshot) -> dict[str, Any]:
    if is_dataclass(snapshot):
        data = _json_safe(asdict(snapshot))
    else:
        data = {}
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
        "CYL BOOST MISMATCH": f"Left/right boost disagreed: L {_safe_float(engine.boost_left_psi)} psi, R {_safe_float(engine.boost_right_psi)} psi.",
        "CYL EGT MISMATCH": f"Left/right EGT disagreed: L {_safe_float(temps.exhaust_left_temp_f)} F, R {_safe_float(temps.exhaust_right_temp_f)} F.",
        "CYL AFR MISMATCH": f"Left/right AFR disagreed: L {_safe_float(engine.afr_left)}, R {_safe_float(engine.afr_right)}.",
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


def fault_action(fault: str, snapshot: StateSnapshot) -> str:
    actions = {
        "WMI FLOW LOW": "Boost request is derated; WMI status remains faulted until measured flow recovers.",
        "EGT HIGH": "Boost is reduced and limp can be requested if exhaust temperature keeps rising.",
        "CAN TIMEOUT": "Controller falls back to no-boost safety behavior until CAN traffic returns.",
        "CAN STALE": "HUD flags stale telemetry; Arduino no-boost timeout covers stale control links.",
        "IMU FAULT": "Lean-aware features should be ignored until IMU data is sane again.",
        "AIR SHOT LOW": "Air Shot output is blocked or allowed to expire until tank pressure recovers.",
        "LOW OIL PRESS": "Fault is logged; sustained/critical pressure escalates toward shutdown request.",
        "CRITICAL OIL PRESS": "Safety supervisor requests no boost and can command engine-run off when safe.",
        "OVERBOOST": "Boost controller drives toward no boost; MS3 hard limits should remain authoritative.",
        "KNOCK": "Boost request is reduced and safety supervisor can enter limp if knock persists.",
        "KNOCK ESCALATE": "Boost and timing authority are reduced through the supervisor/ECU safety stack.",
        "COOLANT HOT": "Boost is derated and limp can be requested above the hard thermal ceiling.",
        "ECU STALE": "Safety supervisor requests no boost, limp, flame-off, and high traction intervention.",
        "SPEED SENSOR": "Traction intervention is suppressed when wheel-speed plausibility is bad.",
        "GEAR SENSOR": "Gear-dependent features fall back to conservative behavior.",
        "CLUTCH SLIP": "Fault is logged; supervisor can derate when slip is severe.",
        "LOW FUEL": "Warning is shown and logged; no automatic shutdown is requested.",
        "WMI TANK EMPTY": "WMI-dependent boost authority is removed until tank level recovers.",
        "WMI PUMP FAULT": "WMI-dependent boost authority is removed while aggregate WMI fault is active.",
        "WMI PRESSURE LOW": "Boost request is derated because WMI pressure/flow response is insufficient.",
        "WASTEGATE STUCK": "Boost-control fault is logged; verify actuator, driver, and pressure plumbing.",
        "BOOST CONTROL ERROR": "Supervisor reduces requested boost if deviation persists under load.",
        "CYL EGT BOOST MISMATCH": "Fault is logged as a plausibility warning for tuning/boost validation.",
        "CYL BOOST MISMATCH": "Fault is logged; check split boost plumbing, throttle balance, compressor/wastegate response, and bank pressure sensors.",
        "CYL EGT MISMATCH": "Fault is logged; compare injector/spark behavior, exhaust leaks, sensor placement, and cylinder fueling.",
        "CYL AFR MISMATCH": "Fault is logged; compare bank fueling, injector flow, exhaust leaks, and wideband calibration.",
        "INTAKE AIR HOT": "Boost target is thermally derated until intake temperature drops.",
        "BATTERY LOW": "Fault is logged; update installs can be blocked by low voltage preflight.",
        "BATTERY HIGH": "Fault is logged as charging-system over-voltage risk.",
        "SENSOR RANGE FAULT": "Critical sensor values are treated as untrusted; conservative defaults apply.",
        "ENGINE RUN SWITCH OFF": "Engine-run output was commanded off by the safety supervisor.",
        "ENGINE SHUTDOWN REQUEST": "Shutdown escalation was issued after critical criteria persisted.",
        "SLOW TURBO SPOOL": "Fault is logged; boost system should be checked for leaks, duty, or turbo response.",
    }
    return actions.get(fault, "Fault is logged with the current engine snapshot for diagnosis.")


def engine_status(snapshot: StateSnapshot) -> dict[str, Any]:
    return {
        "rpm": int(snapshot.engine.rpm),
        "speed_mph": _safe_float(snapshot.engine.speed_mph),
        "gear": snapshot.engine.gear,
        "mode": snapshot.environment.mode,
        "fuel_type": snapshot.environment.fuel_type,
        "ethanol_content_pct": _safe_float(snapshot.environment.ethanol_content_pct),
        "boost_psi": _safe_float(snapshot.engine.boost_psi),
        "boost_left_psi": _safe_float(snapshot.engine.boost_left_psi),
        "boost_right_psi": _safe_float(snapshot.engine.boost_right_psi),
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
        "exhaust_left_temp_f": _safe_float(snapshot.temps.exhaust_left_temp_f),
        "exhaust_right_temp_f": _safe_float(snapshot.temps.exhaust_right_temp_f),
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
        "limp_mode_active": bool(snapshot.system.limp_mode_active),
        "limp_mode_reason": snapshot.system.limp_mode_reason,
    }


def pre_fault_sample(snapshot: StateSnapshot) -> dict[str, Any]:
    """Keep the black-box window compact enough to inspect and export easily."""
    status = engine_status(snapshot)
    return {
        "timestamp": datetime.now().isoformat(timespec="milliseconds"),
        "rpm": status["rpm"],
        "speed_mph": status["speed_mph"],
        "gear": status["gear"],
        "mode": status["mode"],
        "fuel_type": status["fuel_type"],
        "boost_psi": status["boost_psi"],
        "target_boost_psi": status["target_boost_psi"],
        "wastegate_duty_pct": status["wastegate_duty_pct"],
        "throttle_pct": status["throttle_pct"],
        "oil_pressure_psi": status["oil_pressure_psi"],
        "oil_temp_f": status["oil_temp_f"],
        "coolant_temp_f": status["coolant_temp_f"],
        "intake_temp_f": status["intake_temp_f"],
        "exhaust_temp_f": status["exhaust_temp_f"],
        "battery_voltage": status["battery_voltage"],
        "wmi_flow_cc_min": status["wmi_actual_flow_cc_min"],
        "wmi_request_cc_min": status["wmi_commanded_flow_cc_min"],
        "traction_slip_pct": status["traction_slip_pct"],
        "traction_cut_pct": status["traction_torque_cut_pct"],
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
        self._pre_fault_samples: deque[tuple[float, dict[str, Any]]] = deque()
        self._last_pre_fault_sample_s = 0.0
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

    def observe(self, snapshot: StateSnapshot) -> None:
        """Sample a rolling readable black-box window for future fault events."""
        now_s = time.monotonic()
        with self._lock:
            if now_s - self._last_pre_fault_sample_s < PRE_FAULT_SAMPLE_INTERVAL_S:
                return
            self._last_pre_fault_sample_s = now_s
            self._pre_fault_samples.append((now_s, pre_fault_sample(snapshot)))
            while self._pre_fault_samples and now_s - self._pre_fault_samples[0][0] > PRE_FAULT_SECONDS:
                self._pre_fault_samples.popleft()

    def _write_fault_event(self, fault: str, snapshot: StateSnapshot) -> None:
        now = datetime.now()
        with self._lock:
            pre_fault_window = [sample for _, sample in self._pre_fault_samples]
        timeline_name = self._timeline_name(now, fault)
        event = {
            "timestamp": now.isoformat(timespec="milliseconds"),
            "code": f"0x{FAULT_NAME_TO_CODE.get(fault, 0):08X}",
            "fault": fault,
            "reason": fault_reason(fault, snapshot),
            "engine_status": engine_status(snapshot),
            "snapshot": _snapshot_dict(snapshot),
            "pre_fault_timeline": timeline_name,
            "pre_fault_window": pre_fault_window,
        }
        line = json.dumps(event, sort_keys=True)
        summary = self._format_summary(event)
        with self._lock:
            with self._event_log.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
            with self._summary_log.open("a", encoding="utf-8") as handle:
                handle.write(summary + "\n")
            self._write_pre_fault_timeline(self.log_dir / timeline_name, fault, event, pre_fault_window)

    @staticmethod
    def _timeline_name(timestamp: datetime, fault: str) -> str:
        safe_fault = "".join(char if char.isalnum() else "_" for char in fault.lower()).strip("_")
        return f"pre_fault_{timestamp.strftime('%Y%m%d_%H%M%S_%f')[:-3]}_{safe_fault}.txt"

    @staticmethod
    def _write_pre_fault_timeline(path: Path, fault: str, event: dict[str, Any], samples: list[dict[str, Any]]) -> None:
        columns = (
            "timestamp", "rpm", "speed_mph", "gear", "mode", "fuel_type", "boost_psi",
            "target_boost_psi", "wastegate_duty_pct", "throttle_pct", "oil_pressure_psi",
            "oil_temp_f", "coolant_temp_f", "intake_temp_f", "exhaust_temp_f",
            "battery_voltage", "wmi_flow_cc_min", "wmi_request_cc_min",
            "traction_slip_pct", "traction_cut_pct",
        )
        with path.open("w", encoding="utf-8") as handle:
            handle.write(f"FAULT: {fault}\n")
            handle.write(f"TRIGGERED: {event['timestamp']}\n")
            handle.write(f"REASON: {event['reason']}\n")
            handle.write("WINDOW: approximately 30 seconds before the fault, sampled at 10 Hz\n\n")
            handle.write("\t".join(columns) + "\n")
            for sample in samples:
                handle.write("\t".join(str(sample.get(column, "")) for column in columns) + "\n")

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
