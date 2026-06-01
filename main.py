"""Entry point for running the Albatross HUD demo."""
from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import signal
import struct
import sys
import threading
import time
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator

import pygame

from albatross_pi.boost_strategy import calculate_boost_target
from albatross_pi.canbus import ArduinoToHudID, CANStateAggregator, ECUToHudID, PiToArduinoID, PiToEcuID, SocketCANInterface, build_mode_selection_frame, build_traction_level_frame
from albatross_pi.canbus.encode import (
    build_air_shot_request_frame,
    build_boost_target_frame,
    build_ecu_fuel_profile_frame,
    build_ecu_rev_limiter_strategy_frame,
    build_ecu_spark_table_frame,
    build_engine_run_switch_frame,
    build_fuel_type_frame,
    build_flame_mode_frame,
    build_limp_mode_frame,
    build_media_control_frame,
    build_nfc_auth_frame,
    build_phone_link_frame,
)
from albatross_pi.canbus.ids import LIMP_REASON_CODES
from albatross_pi.diagnostics import FaultLogger
from albatross_pi.hud.renderer import HUDRenderer
from albatross_pi.phone import PhoneBridge, PhoneStatus
from albatross_pi.runtime import PiPowerSupervisor, SystemdNotifier
from albatross_pi.security import NfcAuthorizer
from albatross_pi.state.simulator import StateSimulator
from albatross_pi.state.snapshot import CANFrameRecord, ClutchState, LightingState, ServiceFlag, ServiceReading, ServiceStatus, StateSnapshot, SystemStatus, WMIState
from albatross_pi.updater import confirm_pending_update_health, install_update_from_github, install_update_from_usb, request_reboot_if_raspberry_pi


def _iter_can_snapshots(
    aggregator: CANStateAggregator, rate_hz: float
) -> Iterator[StateSnapshot]:
    period = 1.0 / max(1.0, rate_hz)
    while True:
        snapshot = aggregator.wait_for_snapshot(timeout=period)
        yield snapshot


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def _clamp_int(value: object, lo: int, hi: int, default: int = 0) -> int:
    try:
        return max(lo, min(hi, int(float(value))))
    except (TypeError, ValueError):
        return default


def _optional_float(value: object, default: float | None = None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _demo_frame_record(frame_id: int, name: str, payload: bytes, timestamp: datetime, direction: str = "RX") -> CANFrameRecord:
    return CANFrameRecord(
        arbitration_id=frame_id,
        name=name,
        data_hex=payload.hex(" ").upper(),
        direction=direction,
        timestamp=timestamp,
    )


def _demo_recent_can_frames(obj: dict[str, object]) -> tuple[CANFrameRecord, ...]:
    """Build representative raw CAN records for the UDP-only Windows demo path."""
    now = datetime.now()
    gear_map = {"N": 0, "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6}
    mode_map = {"ECO": 1, "NORMAL": 2, "SPORT": 3, "RACE": 4, "ALBATROSS": 5}
    fuel_type_map = {"87": 0, "91": 1, "93": 2, "100": 3, "E85": 4, "C16": 5}
    gear = str(obj.get("gear", "N"))
    mode = str(obj.get("mode", "NORMAL"))
    fuel_type = str(obj.get("fuel_type", "93"))
    limp_active = bool(obj.get("limp_mode", False))
    limp_reason = str(obj.get("limp_reason", "PI REQUEST" if limp_active else "NONE")).upper()
    limp_reason_code = LIMP_REASON_CODES.get(limp_reason, LIMP_REASON_CODES["PI REQUEST"] if limp_active else 0)
    speed_mps100 = _clamp_int(float(obj.get("speed", 0.0)) / 2.236936 * 100, 0, 65535)
    light_flags = 0
    light_flags |= 0x01 if bool(obj.get("left_indicator", False)) else 0
    light_flags |= 0x02 if bool(obj.get("right_indicator", False)) else 0
    light_flags |= 0x04 if bool(obj.get("high_beam", False)) else 0
    light_flags |= 0x08 if bool(obj.get("neutral_light", gear == "N")) else 0
    light_flags |= 0x10 if bool(obj.get("brake_light", False)) else 0
    light_flags |= 0x20 if bool(obj.get("oil_warning", False)) else 0

    def f_to_cx10(key: str, default_f: float) -> int:
        temp_f = float(obj.get(key, default_f))
        return _clamp_int((temp_f - 32.0) * 5.0 / 9.0 * 10, 0, 65535)

    output_bits = 0
    output_bits |= 0x01 if _clamp_int(obj.get("wg1", 0), 0, 100) > 0 else 0
    output_bits |= 0x02 if _clamp_int(obj.get("wg2", 0), 0, 100) > 0 else 0
    output_bits |= 0x04 if bool(obj.get("wmi_arm", False)) else 0
    output_bits |= 0x08 if bool(obj.get("flame_mode", False)) else 0
    output_bits |= 0x10 if bool(obj.get("airshot_firing", False)) else 0
    output_bits |= 0x20 if bool(obj.get("air_compressor", False)) else 0
    output_bits |= 0x40 if _clamp_int(obj.get("wg1", 0), 0, 100) > 0 else 0
    output_bits |= 0x80 if _clamp_int(obj.get("wg2", 0), 0, 100) > 0 else 0
    command_bits = 0
    command_bits |= 0x01 if bool(obj.get("nfc_ok", True)) else 0
    command_bits |= 0x02 if bool(obj.get("flame_mode", False)) else 0
    command_bits |= 0x04 if bool(obj.get("limp_mode", False)) else 0
    command_bits |= 0x08 if bool(obj.get("engine_run", True)) else 0
    command_bits |= 0x10 if bool(obj.get("wmi_arm", False)) else 0
    command_bits |= 0x20 if bool(obj.get("airshot_request", False)) else 0
    fault_bits = 0
    fault_bits |= 0x04 if bool(obj.get("wmi_fault", False)) else 0
    fault_bits |= 0x08 if bool(obj.get("traction_fault", False)) else 0

    records = [
        (ECUToHudID.ENGINE_RPM, struct.pack(">H", _clamp_int(obj.get("rpm", 0), 0, 65535)), "RX"),
        (ECUToHudID.THROTTLE_POSITION, bytes((_clamp_int(obj.get("tps", 0), 0, 100),)), "RX"),
        (ECUToHudID.BOOST_PRESSURE, struct.pack(">H", _clamp_int(float(obj.get("boost", 0.0)) * 10, 0, 65535)), "RX"),
        (
            ECUToHudID.BOOST_PRESSURE_BANKS,
            struct.pack(
                ">HH",
                _clamp_int(float(obj.get("boost_l", obj.get("boost", 0.0))) * 10, 0, 65535),
                _clamp_int(float(obj.get("boost_r", obj.get("boost", 0.0))) * 10, 0, 65535),
            ),
            "RX",
        ),
        (
            ECUToHudID.AFR_BANKS,
            struct.pack(
                ">HH",
                _clamp_int(float(obj.get("afr_l", 0.0)) * 100, 0, 65535),
                _clamp_int(float(obj.get("afr_r", 0.0)) * 100, 0, 65535),
            ),
            "RX",
        ),
        (
            ECUToHudID.EXHAUST_GAS_TEMP,
            struct.pack(">HH", f_to_cx10("egt_b1", 1450.0), f_to_cx10("egt_b2", 1470.0)),
            "RX",
        ),
        (ECUToHudID.OIL_PRESSURE_TEMP, struct.pack(">HH", _clamp_int(float(obj.get("oilp", 0.0)) * 10, 0, 65535), f_to_cx10("oilt", 205.0)), "RX"),
        (ECUToHudID.COOLANT_TEMP, struct.pack(">H", f_to_cx10("clt", 190.0)), "RX"),
        (ECUToHudID.BATTERY_VOLTAGE, struct.pack(">H", _clamp_int(float(obj.get("batt_v", 0.0)) * 1000, 0, 65535)), "RX"),
        (ECUToHudID.FLEX_FUEL, bytes((_clamp_int(obj.get("ethanol_pct", 0), 0, 100),)), "RX"),
        (ArduinoToHudID.WHEEL_SPEED, struct.pack(">HH", speed_mps100, speed_mps100), "RX"),
        (ArduinoToHudID.WMI_STATUS, struct.pack(">BHHB", _clamp_int(obj.get("wmi_tank", 0), 0, 100), _clamp_int(obj.get("wmi_commanded", 0), 0, 65535), _clamp_int(obj.get("wmi_actual", 0), 0, 65535), 1 if bool(obj.get("wmi_fault", False)) else 0), "RX"),
        (ArduinoToHudID.LIGHT_STATUS, bytes((light_flags,)), "RX"),
        (ArduinoToHudID.WASTEGATE_STATUS, bytes((_clamp_int(obj.get("wg1", 0), 0, 100), _clamp_int(obj.get("wg2", 0), 0, 100))), "RX"),
        (ArduinoToHudID.SERVICE_SENSOR_VOLTAGES, struct.pack(">HHHH", _clamp_int(float(obj.get("oil_sensor_v", 0.0)) * 1000, 0, 65535), _clamp_int(float(obj.get("wmi_tank_v", 0.0)) * 1000, 0, 65535), _clamp_int(float(obj.get("arduino_5v", 3.3)) * 1000, 0, 65535), _clamp_int(float(obj.get("air_tank_v", 2.95)) * 1000, 0, 65535)), "RX"),
        (ArduinoToHudID.SERVICE_DIGITAL_STATES, bytes((light_flags | (0x40 if bool(obj.get("wmi_pressure_ok", True)) else 0), output_bits, command_bits, fault_bits)), "RX"),
        (ArduinoToHudID.LIMP_STATUS, bytes((1 if limp_active else 0, limp_reason_code & 0xFF)), "RX"),
        (PiToArduinoID.AIR_SHOT_REQUEST, bytes((1,)), "TX") if bool(obj.get("airshot_request", False)) else None,
        (PiToArduinoID.MODE_SELECTION, bytes((mode_map.get(mode, 2),)), "TX"),
        (PiToArduinoID.FUEL_TYPE_SELECT, bytes((fuel_type_map.get(fuel_type, 2),)), "TX"),
        (PiToArduinoID.FLAME_MODE, bytes((1 if bool(obj.get("flame_mode", False)) else 0,)), "TX"),
        (PiToEcuID.REV_LIMITER_STRATEGY, bytes((1 if bool(obj.get("flame_mode", False)) else 0,)), "TX"),
        (ArduinoToHudID.GEAR_POSITION, bytes((gear_map.get(gear, 0),)), "RX"),
    ]
    return tuple(
        _demo_frame_record(int(frame_id), f"{frame_id.__class__.__name__}.{frame_id.name}", payload, now, direction)
        for frame_id, payload, direction in reversed([record for record in records if record is not None])
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Albatross HUD demo")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--can-interface", help="SocketCAN interface name (e.g., can0)")
    parser.add_argument("--simulator", action="store_true", help="Use built-in simulator when CAN is not provided")
    parser.add_argument("--demo-udp-listen", default="127.0.0.1:5005", help="listen host:port for demo control UDP")
    parser.add_argument("--can-bitrate", type=int, help="Bitrate hint for SocketCAN setup")
    parser.add_argument("--can-rate", type=float, default=60.0, help="HUD update rate when using CAN")
    parser.add_argument("--log-level", default="INFO", help="Python logging level")
    parser.add_argument("--fault-log-dir", type=Path, default=Path("logs"), help="directory for fault event logs")
    parser.add_argument("--settings-file", type=Path, default=Path("settings/hud_settings.json"), help="persistent HUD settings file")
    parser.add_argument("--phone-bt-mac", help="Paired phone Bluetooth MAC for media/weather/GPS bridge")
    parser.add_argument("--phone-telemetry-udp", default="127.0.0.1:5010", help="UDP host:port for phone weather/GPS telemetry")
    parser.add_argument("--nfc-config", type=Path, default=Path("settings/nfc_auth.json"), help="USB NFC authorization configuration")
    parser.add_argument("--nfc-bypass", action="store_true", help="bench-only: permit engine run without an NFC scan")
    parser.add_argument("--disable-low-voltage-shutdown", action="store_true", help="disable orderly Pi halt after sustained engine-off undervoltage")
    parser.add_argument("--bind-inputs", action="store_true", help="Prompt keyboard bindings for demo controls")
    parser.add_argument(
        "--snapshot",
        type=Path,
        help="Render a single frame to the specified image file and exit",
    )
    args = parser.parse_args()

    _configure_logging(args.log_level)
    fault_logger = FaultLogger(args.fault_log_dir)
    power_supervisor = PiPowerSupervisor(enabled=not args.disable_low_voltage_shutdown)
    systemd_notifier = SystemdNotifier()

    if args.snapshot:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

    try:
        renderer = HUDRenderer(
            screen_size=(args.width, args.height),
            use_display=args.snapshot is None,
            preferences_path=args.settings_file,
        )
    except Exception:
        logging.exception("HUD renderer failed to initialize")
        raise
    if args.bind_inputs and not args.snapshot:
        ack_name = input("POST acknowledge key (default: return): ").strip().lower() or "return"
        airshot_name = input("Air Shot key (default: f): ").strip().lower() or "f"
        try:
            ack_key = pygame.key.key_code(ack_name)
        except ValueError:
            logging.warning("Unknown key binding '%s'; using RETURN", ack_name)
            ack_key = pygame.K_RETURN
        try:
            airshot_key = pygame.key.key_code(airshot_name)
        except ValueError:
            logging.warning("Unknown key binding '%s'; using F", airshot_name)
            airshot_key = pygame.K_f
        renderer.configure_input_bindings(ack_key, airshot_key)
    def _record_faults(faults: tuple[str, ...], snapshot: StateSnapshot) -> None:
        for fault in faults:
            fault_logger.log_fault(fault, snapshot)

    def _observe_snapshot(snapshot: StateSnapshot) -> None:
        fault_logger.observe(snapshot)
        power_supervisor.observe(snapshot)

    renderer.configure_fault_log_callback(_record_faults)
    renderer.configure_snapshot_log_callback(_observe_snapshot)
    renderer.configure_runtime_heartbeat_callback(systemd_notifier.watchdog)
    renderer.configure_runtime_health_callback(confirm_pending_update_health)
    renderer.configure_log_export_callback(fault_logger.export_to_usb)
    renderer.configure_update_install_callback(lambda snapshot: install_update_from_usb(snapshot).display())

    def _online_update(snapshot: StateSnapshot, progress_callback) -> str:
        result = install_update_from_github(snapshot, progress_callback)
        display = result.display()
        if "RESTART" in display:
            display = f"{display} REBOOTING" if request_reboot_if_raspberry_pi() else f"{display} REBOOT MANUAL"
        return display

    renderer.configure_online_update_callback(_online_update)
    phone_bridge: PhoneBridge | None = None

    def _apply_phone_status(status: PhoneStatus) -> None:
        snap = renderer.state
        env = replace(
            snap.environment,
            ambient_temp_f=status.ambient_temp_f if status.ambient_temp_f is not None else snap.environment.ambient_temp_f,
            gps_lock=status.gps_lock if status.gps_lock is not None else snap.environment.gps_lock,
            gps_latitude=status.gps_lat if status.gps_lat is not None else snap.environment.gps_latitude,
            gps_longitude=status.gps_lon if status.gps_lon is not None else snap.environment.gps_longitude,
            rain=status.rain if status.rain is not None else snap.environment.rain,
            time=status.phone_time if status.phone_time is not None else snap.environment.time,
            message_line=(f"♫ {status.artist} - {status.track}"[:96] if status.track else snap.environment.message_line),
        )
        renderer.update_phone_status(
            artist=status.artist,
            track=status.track,
            position_s=status.position_s,
            length_s=status.length_s,
            devices=status.devices,
        )
        renderer.update_state(replace(snap, environment=env))

    if args.phone_bt_mac:
        phone_bridge = PhoneBridge(args.phone_bt_mac, _apply_phone_status, telemetry_udp=args.phone_telemetry_udp)
        phone_bridge.start()

    can_interface: SocketCANInterface | None = None
    aggregator: CANStateAggregator | None = None
    simulator: StateSimulator | None = None
    stream: Iterable[StateSnapshot] | None = None
    nfc_authorizer: NfcAuthorizer | None = None
    authority_stop_event = threading.Event()
    engine_run_inhibit = threading.Event()

    if args.can_interface:
        aggregator = CANStateAggregator()
        can_interface = SocketCANInterface(
            channel=args.can_interface,
            bitrate=args.can_bitrate,
            rx_callback=aggregator.apply_frame,
        )
        try:
            can_interface.start()
        except RuntimeError as exc:
            logging.error("Unable to start CAN interface: %s", exc)
            sys.exit(1)
        if not args.snapshot:
            stream = _iter_can_snapshots(aggregator, args.can_rate)

        def _send_traction_level(level_code: int) -> None:
            frame_id, payload = build_traction_level_frame(level_code)
            assert can_interface is not None
            can_interface.send(frame_id, payload)
            aggregator.mark_sent_frame(frame_id, payload)

        renderer.configure_traction_callback(_send_traction_level)

        def _send_boost_request() -> None:
            assert can_interface is not None and aggregator is not None
            snapshot = aggregator.current_snapshot()
            boost_frame = build_boost_target_frame(calculate_boost_target(snapshot))
            can_interface.send(*boost_frame)
            aggregator.mark_sent_frame(*boost_frame)

        def _send_mode_selection(mode_code: int) -> None:
            assert can_interface is not None
            for frame in (
                build_mode_selection_frame(mode_code),
                build_ecu_spark_table_frame(mode_code),
            ):
                can_interface.send(*frame)
                aggregator.mark_sent_frame(*frame)
            _send_boost_request()

        def _send_flame_mode(enabled: bool) -> None:
            assert can_interface is not None
            for frame in (
                build_flame_mode_frame(enabled),
                build_ecu_rev_limiter_strategy_frame(enabled),
            ):
                can_interface.send(*frame)
                aggregator.mark_sent_frame(*frame)

        def _send_fuel_type(fuel_code: int) -> None:
            assert can_interface is not None
            for frame in (
                build_fuel_type_frame(fuel_code),
                build_ecu_fuel_profile_frame(fuel_code),
            ):
                can_interface.send(*frame)
                aggregator.mark_sent_frame(*frame)
            _send_boost_request()

        def _send_air_shot_request() -> None:
            assert can_interface is not None and aggregator is not None
            frame = build_air_shot_request_frame()
            can_interface.send(*frame)
            aggregator.mark_sent_frame(*frame)

        def _send_media_control(command: str, value: int) -> None:
            assert can_interface is not None
            if command == "phone_link":
                enabled = bool(value)
                if phone_bridge is not None:
                    phone_bridge.set_link(enabled)
                frame = build_phone_link_frame(enabled)
            else:
                if phone_bridge is not None:
                    if command.startswith("connect:"):
                        phone_bridge.connect_device(command.split(":", 1)[1])
                    else:
                        phone_bridge.media_command(command)
                command_map = {"prev": 0x10, "play_pause": 0x11, "next": 0x12}
                frame = build_media_control_frame(command_map.get(command, 0x00), value)
            can_interface.send(*frame)
            aggregator.mark_sent_frame(*frame)

        renderer.configure_mode_callback(_send_mode_selection)
        renderer.configure_media_callback(_send_media_control)
        renderer.configure_fuel_type_callback(_send_fuel_type)
        renderer.configure_flame_callback(_send_flame_mode)
        renderer.configure_air_shot_callback(_send_air_shot_request)
        renderer.configure_can_freshness_callback(
            aggregator.rx_age_s,
            ecu_callback=aggregator.ecu_rx_age_s,
            controller_callback=aggregator.controller_rx_age_s,
        )
        renderer.sync_persisted_controls()

        nfc_authorizer = NfcAuthorizer.from_config(args.nfc_config, bypass=args.nfc_bypass)
        nfc_authorizer.start()

        def _send_start_authority() -> None:
            assert can_interface is not None and aggregator is not None and nfc_authorizer is not None
            while not authority_stop_event.is_set():
                authorized = nfc_authorizer.authorized
                engine_run_enabled = authorized and not engine_run_inhibit.is_set()
                try:
                    for frame in (
                        build_nfc_auth_frame(authorized),
                        build_engine_run_switch_frame(engine_run_enabled),
                    ):
                        can_interface.send(*frame)
                        aggregator.mark_sent_frame(*frame)
                except Exception:
                    logging.exception("Unable to publish NFC/start authority heartbeat")
                authority_stop_event.wait(0.25)

        threading.Thread(target=_send_start_authority, name="start-authority", daemon=True).start()

        def _safety_supervisor() -> None:
            assert aggregator is not None and can_interface is not None
            last_fault_state = False
            critical_oil_start: float | None = None
            last_engine_run_switch_enabled = True
            last_escalation_ts = 0.0
            boost_ctrl_error_start: float | None = None
            wmi_flow_low_start: float | None = None
            boost_mismatch_start: float | None = None
            egt_mismatch_start: float | None = None
            afr_mismatch_start: float | None = None
            prev_boost_psi = 0.0
            prev_wg_duty = 0.0
            wg_stuck_start: float | None = None
            last_requested_boost: float | None = None
            last_requested_boost_ts = 0.0

            def limp_reason_for(faults_now: list[str], shutdown_requested: bool = False, run_switch_cut: bool = False) -> str:
                if shutdown_requested:
                    return "LOW OIL PRESS"
                if run_switch_cut:
                    return "ENGINE RUN OFF"
                if "ECU STALE" in faults_now:
                    return "ECU CAN STALE"
                if "CAN STALE" in faults_now:
                    return "CONTROL LINK STALE"
                if "LOW OIL PRESS" in faults_now or "CRITICAL OIL PRESS" in faults_now:
                    return "LOW OIL PRESS"
                if "COOLANT HOT" in faults_now or "EGT HIGH" in faults_now or "INTAKE AIR HOT" in faults_now:
                    return "THERMAL"
                if "BATTERY LOW" in faults_now or "BATTERY HIGH" in faults_now:
                    return "BATTERY VOLTAGE"
                if "KNOCK" in faults_now or "KNOCK ESCALATE" in faults_now:
                    return "KNOCK"
                if "OVERBOOST" in faults_now or "BOOST CONTROL ERROR" in faults_now:
                    return "OVERBOOST"
                if "WMI FLOW LOW" in faults_now or "WMI PRESSURE LOW" in faults_now or "WMI PUMP FAULT" in faults_now:
                    return "WMI FAULT"
                if "CLUTCH SLIP" in faults_now:
                    return "CLUTCH SLIP"
                return "SAFETY SUPERVISOR"

            while True:
                snap = aggregator.current_snapshot()
                faults: list[str] = []
                now_ts = time.time()

                # Source-specific ages cannot be hidden by unrelated traffic or local TX echoes.
                if aggregator.ecu_rx_age_s() > 0.5:
                    faults.append("ECU STALE")
                if aggregator.controller_rx_age_s() > 0.5:
                    faults.append("CAN STALE")
                if snap.engine.throttle_pct > 15 and snap.engine.rpm < 300:
                    faults.append("ECU STALE")
                if snap.engine.rpm > 0 and snap.engine.speed_mph == 0 and snap.engine.gear not in ("N", "?"):
                    faults.append("SPEED SENSOR")
                if snap.engine.gear not in ("N", "1", "2", "3", "4", "5", "6", "?"):
                    faults.append("GEAR SENSOR")
                # Clutch slip is computed controller-side from predicted vs observed RPM:MPH ratio.
                # Ratios are currently placeholders until measured drivetrain ratios are provided.
                if (
                    snap.clutch.slip_pct >= 8.0
                    and snap.engine.gear not in ("N", "?")
                    and snap.engine.speed_mph > 5.0
                ) or (
                    snap.clutch.severity in ("MODERATE", "SEVERE")
                    and snap.engine.gear not in ("N", "?")
                ):
                    faults.append("CLUTCH SLIP")
                if snap.temps.oil_pressure_psi < 12 and snap.engine.rpm > 2000:
                    faults.append("LOW OIL PRESS")
                if snap.temps.oil_pressure_psi < 8 and snap.engine.rpm > 2200:
                    faults.append("CRITICAL OIL PRESS")
                if snap.temps.coolant_temp_f > 240:
                    faults.append("COOLANT HOT")
                if snap.temps.exhaust_temp_f > 1650:
                    faults.append("EGT HIGH")
                if snap.temps.intake_temp_f > 150:
                    faults.append("INTAKE AIR HOT")
                if snap.temps.battery_voltage > 0 and snap.temps.battery_voltage < 11.2:
                    faults.append("BATTERY LOW")
                if snap.temps.battery_voltage > 15.4:
                    faults.append("BATTERY HIGH")
                if (
                    snap.engine.boost_psi > 10.0
                    and snap.engine.rpm > 3000
                    and snap.temps.exhaust_temp_f > 1400
                    and abs(snap.engine.boost_psi - (snap.temps.exhaust_temp_f / 100.0)) > 9.0
                ):
                    faults.append("CYL EGT BOOST MISMATCH")
                boost_mismatch = (
                    snap.engine.boost_left_psi >= 0.0
                    and snap.engine.boost_right_psi >= 0.0
                    and snap.engine.rpm > 3000
                    and snap.engine.throttle_pct > 35
                    and (snap.engine.target_boost_psi > 4.0 or snap.engine.boost_psi > 4.0)
                    and abs(snap.engine.boost_left_psi - snap.engine.boost_right_psi) >= 3.0
                )
                if boost_mismatch:
                    if boost_mismatch_start is None:
                        boost_mismatch_start = now_ts
                    elif (now_ts - boost_mismatch_start) >= 0.6:
                        faults.append("CYL BOOST MISMATCH")
                else:
                    boost_mismatch_start = None
                egt_mismatch = (
                    snap.temps.exhaust_left_temp_f >= 0.0
                    and snap.temps.exhaust_right_temp_f >= 0.0
                    and snap.engine.rpm > 3000
                    and snap.engine.throttle_pct > 35
                    and abs(snap.temps.exhaust_left_temp_f - snap.temps.exhaust_right_temp_f) >= 150.0
                )
                if egt_mismatch:
                    if egt_mismatch_start is None:
                        egt_mismatch_start = now_ts
                    elif (now_ts - egt_mismatch_start) >= 0.8:
                        faults.append("CYL EGT MISMATCH")
                else:
                    egt_mismatch_start = None
                afr_mismatch = (
                    snap.engine.afr_left > 0.0
                    and snap.engine.afr_right > 0.0
                    and snap.engine.rpm > 2500
                    and snap.engine.throttle_pct > 30
                    and abs(snap.engine.afr_left - snap.engine.afr_right) >= 0.8
                )
                if afr_mismatch:
                    if afr_mismatch_start is None:
                        afr_mismatch_start = now_ts
                    elif (now_ts - afr_mismatch_start) >= 0.8:
                        faults.append("CYL AFR MISMATCH")
                else:
                    afr_mismatch_start = None
                if snap.engine.boost_psi > (snap.engine.target_boost_psi + 3.0):
                    faults.append("OVERBOOST")
                if snap.engine.knock_events >= 3:
                    faults.append("KNOCK")
                if snap.environment.fuel_level_pct <= 5:
                    faults.append("LOW FUEL")
                if snap.air_shot.pressure_psi > 0 and snap.air_shot.pressure_psi < 35:
                    faults.append("AIR SHOT LOW")
                if snap.wmi.fault_active:
                    faults.append("WMI PUMP FAULT")
                if snap.wmi.tank_level_pct >= 0 and snap.wmi.tank_level_pct < 3:
                    faults.append("WMI TANK EMPTY")
                if snap.wmi.commanded_flow_cc_min > 0:
                    if snap.wmi.actual_flow_cc_min < (0.6 * snap.wmi.commanded_flow_cc_min):
                        if wmi_flow_low_start is None:
                            wmi_flow_low_start = now_ts
                        elif (now_ts - wmi_flow_low_start) >= 0.25:
                            faults.append("WMI FLOW LOW")
                            faults.append("WMI PRESSURE LOW")
                    else:
                        wmi_flow_low_start = None
                else:
                    wmi_flow_low_start = None

                boost_error = abs(snap.engine.boost_psi - snap.engine.target_boost_psi)
                if snap.engine.target_boost_psi >= 8.0 and snap.engine.throttle_pct > 35 and boost_error > 4.0:
                    if boost_ctrl_error_start is None:
                        boost_ctrl_error_start = now_ts
                    elif (now_ts - boost_ctrl_error_start) >= 0.75:
                        faults.append("BOOST CONTROL ERROR")
                else:
                    boost_ctrl_error_start = None

                if snap.engine.throttle_pct > 35 and snap.engine.target_boost_psi >= 8.0:
                    wg_delta = abs(snap.engine.wastegate_duty_pct - prev_wg_duty)
                    boost_delta = abs(snap.engine.boost_psi - prev_boost_psi)
                    if wg_delta >= 8.0 and boost_delta < 0.4:
                        if wg_stuck_start is None:
                            wg_stuck_start = now_ts
                        elif (now_ts - wg_stuck_start) >= 1.0:
                            faults.append("WASTEGATE STUCK")
                    else:
                        wg_stuck_start = None
                else:
                    wg_stuck_start = None
                prev_boost_psi = snap.engine.boost_psi
                prev_wg_duty = snap.engine.wastegate_duty_pct

                severe = any(f in faults for f in ("CAN STALE", "ECU STALE", "LOW OIL PRESS", "COOLANT HOT", "EGT HIGH", "CLUTCH SLIP"))
                desired_boost = 0.0 if severe else calculate_boost_target(snap)
                if (
                    last_requested_boost is None
                    or abs(desired_boost - last_requested_boost) >= 0.1
                    or (now_ts - last_requested_boost_ts) >= 1.0
                ):
                    frame = build_boost_target_frame(desired_boost)
                    can_interface.send(*frame)
                    aggregator.mark_sent_frame(*frame)
                    last_requested_boost = desired_boost
                    last_requested_boost_ts = now_ts

                # Critical oil-pressure handling with anti-false-positive protections:
                # - ignore cranking/idle zones
                # - require persistence
                # - only request shutdown when neutral + near-stationary
                critical_oil = "CRITICAL OIL PRESS" in faults
                running_not_cranking = snap.engine.rpm > 1200
                if critical_oil and running_not_cranking:
                    if critical_oil_start is None:
                        critical_oil_start = now_ts
                else:
                    critical_oil_start = None

                should_shutdown_engine = (
                    critical_oil_start is not None
                    and (now_ts - critical_oil_start) > 2.5
                    and snap.engine.gear == "N"
                    and snap.engine.speed_mph < 3.0
                    and snap.engine.throttle_pct < 8.0
                )
                should_cut_run_switch = (
                    should_shutdown_engine
                    or ("ECU STALE" in faults and snap.engine.rpm > 1800 and snap.engine.throttle_pct > 20)
                    or ("COOLANT HOT" in faults and snap.temps.coolant_temp_f > 250 and snap.engine.rpm > 2000)
                    or ("EGT HIGH" in faults and snap.temps.exhaust_temp_f > 1725 and snap.engine.rpm > 2200)
                )
                if severe and not last_fault_state:
                    # Fail-safe action set: cut boost command, enable limp, disable flame, max traction.
                    limp_reason = limp_reason_for(faults)
                    for frame in (
                        build_boost_target_frame(0.0),
                        build_limp_mode_frame(True, limp_reason),
                        build_flame_mode_frame(False),
                        build_ecu_rev_limiter_strategy_frame(False),
                        build_traction_level_frame(3),
                    ):
                        can_interface.send(*frame)
                        aggregator.mark_sent_frame(*frame)
                    logging.error("Safety supervisor engaged: %s", ", ".join(faults))
                elif not severe and last_fault_state:
                    # Clear limp when recovered.
                    frame = build_limp_mode_frame(False)
                    can_interface.send(*frame)
                    aggregator.mark_sent_frame(*frame)
                    logging.info("Safety supervisor recovered.")

                if should_shutdown_engine:
                    # Engine shutdown request includes torque-reduction stack + run-switch OFF.
                    limp_reason = limp_reason_for(faults, shutdown_requested=True)
                    for frame in (
                        build_boost_target_frame(0.0),
                        build_limp_mode_frame(True, limp_reason),
                        build_flame_mode_frame(False),
                        build_ecu_rev_limiter_strategy_frame(False),
                        build_traction_level_frame(3),
                    ):
                        can_interface.send(*frame)
                        aggregator.mark_sent_frame(*frame)
                    faults.append("ENGINE SHUTDOWN REQUEST")
                    logging.critical("Critical oil pressure persisted; shutdown request issued in neutral at low speed.")

                # Engine run switch "OFF" acts as ECU-level kill (ignition/fuel cut).
                # Re-send every 1s while active for robustness against frame loss.
                if should_cut_run_switch:
                    engine_run_inhibit.set()
                    if last_engine_run_switch_enabled or (now_ts - last_escalation_ts) >= 1.0:
                        frame = build_engine_run_switch_frame(False)
                        can_interface.send(*frame)
                        aggregator.mark_sent_frame(*frame)
                        last_escalation_ts = now_ts
                    last_engine_run_switch_enabled = False
                    faults.append("ENGINE RUN SWITCH OFF")
                elif not last_engine_run_switch_enabled:
                    engine_run_inhibit.clear()
                    if nfc_authorizer is not None and nfc_authorizer.authorized:
                        frame = build_engine_run_switch_frame(True)
                        can_interface.send(*frame)
                        aggregator.mark_sent_frame(*frame)
                        last_engine_run_switch_enabled = True
                        logging.info("Safety supervisor restored authorized engine run switch to ON.")
                else:
                    engine_run_inhibit.clear()

                if faults:
                    active_limp = severe or should_shutdown_engine or should_cut_run_switch
                    renderer.update_state(
                        replace(
                            snap,
                            faults=tuple(sorted(set(faults))),
                            system=replace(
                                snap.system,
                                limp_mode_active=active_limp,
                                limp_mode_reason=limp_reason_for(faults, should_shutdown_engine, should_cut_run_switch) if active_limp else "",
                            ),
                        )
                    )
                last_fault_state = severe
                time.sleep(0.2)

        threading.Thread(target=_safety_supervisor, name="safety-supervisor", daemon=True).start()
    elif args.simulator:
        simulator = StateSimulator()
        renderer.configure_mode_callback(simulator.set_mode)
        renderer.configure_fuel_type_callback(simulator.set_fuel_type)
        renderer.sync_persisted_controls()
        if not args.snapshot:
            stream = simulator.stream()

    def _start_demo_udp_listener(addr: str) -> None:
        host, port_s = addr.split(":")
        port = int(port_s)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind((host, port))
        except PermissionError:
            logging.warning(
                "Unable to bind demo UDP listener on %s:%s (permission denied). "
                "Trying localhost fallback port 5505.",
                host,
                port,
            )
            sock.bind(("127.0.0.1", 5505))
            logging.info("Demo UDP listener bound on 127.0.0.1:5505")
        except OSError as exc:
            logging.warning(
                "Unable to bind demo UDP listener on %s:%s (%s). "
                "Demo UDP listener disabled.",
                host,
                port,
                exc,
            )
            return
        else:
            logging.info("Demo UDP listener bound on %s:%s", host, port)
        sock.settimeout(0.2)

        def loop() -> None:
            while True:
                try:
                    data, _ = sock.recvfrom(65535)
                except socket.timeout:
                    continue
                try:
                    obj = json.loads(data.decode("utf-8"))
                except Exception:
                    continue
                snap = renderer.state
                eng = replace(
                    snap.engine,
                    rpm=int(obj.get("rpm", snap.engine.rpm)),
                    speed_mph=float(obj.get("speed_mph", obj.get("speed", snap.engine.speed_mph))),
                    boost_psi=(
                        float(obj.get("boost_l", obj.get("boost", snap.engine.boost_psi)))
                        + float(obj.get("boost_r", obj.get("boost", snap.engine.boost_psi)))
                    ) / 2.0,
                    boost_left_psi=float(obj.get("boost_l", obj.get("boost", snap.engine.boost_left_psi))),
                    boost_right_psi=float(obj.get("boost_r", obj.get("boost", snap.engine.boost_right_psi))),
                    throttle_pct=float(obj.get("tps", snap.engine.throttle_pct)),
                    gear=str(obj.get("gear", snap.engine.gear)),
                    afr_left=float(obj.get("afr_l", snap.engine.afr_left)),
                    afr_right=float(obj.get("afr_r", snap.engine.afr_right)),
                    knock_events=int(bin(int(obj.get("knock_mask", 0))).count("1")) if "knock_mask" in obj else snap.engine.knock_events,
                    engine_load_pct=float(obj.get("load", snap.engine.engine_load_pct)),
                    wastegate_duty_pct=(float(obj.get("wg1", snap.engine.wastegate_duty_pct)) + float(obj.get("wg2", snap.engine.wastegate_duty_pct))) / 2.0,
                )
                economy = replace(
                    snap.economy,
                    injector_pulse_width_ms=float(obj.get("inj_pw_ms", snap.economy.injector_pulse_width_ms)),
                    injector_duty_pct=float(obj.get("inj_duty_pct", snap.economy.injector_duty_pct)),
                )
                temps = replace(
                    snap.temps,
                    coolant_temp_f=float(obj.get("clt_f", obj.get("clt", snap.temps.coolant_temp_f))),
                    oil_temp_f=float(obj.get("oilt_f", obj.get("oilt", snap.temps.oil_temp_f))),
                    oil_pressure_psi=float(obj.get("oilp", snap.temps.oil_pressure_psi)),
                    intake_temp_f=float(obj.get("iat", snap.temps.intake_temp_f)),
                    exhaust_temp_f=(float(obj.get("egt_b1", snap.temps.exhaust_temp_f)) + float(obj.get("egt_b2", snap.temps.exhaust_temp_f))) / 2.0,
                    exhaust_left_temp_f=float(obj.get("egt_b1", snap.temps.exhaust_left_temp_f)),
                    exhaust_right_temp_f=float(obj.get("egt_b2", snap.temps.exhaust_right_temp_f)),
                    battery_voltage=float(obj.get("batt_v", snap.temps.battery_voltage)),
                )
                env = replace(
                    snap.environment,
                    mode=str(obj.get("mode", snap.environment.mode)),
                    fuel_type=str(obj.get("fuel_type", snap.environment.fuel_type)),
                    ethanol_content_pct=float(obj.get("ethanol_pct", snap.environment.ethanol_content_pct)),
                    fuel_level_pct=float(obj.get("fuel", snap.environment.fuel_level_pct)),
                    gps_lock=bool(obj.get("gps_lock", snap.environment.gps_lock)),
                    gps_latitude=_optional_float(obj.get("gps_lat", obj.get("gps_latitude")), snap.environment.gps_latitude),
                    gps_longitude=_optional_float(obj.get("gps_lon", obj.get("gps_longitude")), snap.environment.gps_longitude),
                    message_line=str(obj.get("msg", snap.environment.message_line)),
                    flame_mode_enabled=bool(obj.get("flame_mode", snap.environment.flame_mode_enabled)),
                    rev_limiter_strategy="IGNITION CUT" if bool(obj.get("flame_mode", snap.environment.flame_mode_enabled)) else "FUEL CUT",
                )
                air = replace(
                    snap.air_shot,
                    pressure_psi=float(obj.get("tank_psi", snap.air_shot.pressure_psi)),
                    charges_remaining=max(0, min(3, int(obj.get("airshot_charges", snap.air_shot.charges_remaining)))),
                    is_firing=bool(obj.get("airshot_firing", snap.air_shot.is_firing)),
                )
                wmi = WMIState(
                    tank_level_pct=float(obj.get("wmi_tank", snap.wmi.tank_level_pct)),
                    commanded_flow_cc_min=float(obj.get("wmi_commanded", snap.wmi.commanded_flow_cc_min)),
                    actual_flow_cc_min=float(obj.get("wmi_actual", snap.wmi.actual_flow_cc_min)),
                    fault_active=bool(obj.get("wmi_fault", snap.wmi.fault_active)),
                )
                trac = replace(
                    snap.traction,
                    intervention_level=str(obj.get("traction", snap.traction.intervention_level)),
                    slip_pct=float(obj.get("traction_slip", snap.traction.slip_pct)),
                    torque_cut_pct=float(obj.get("torque_cut", snap.traction.torque_cut_pct)),
                    active=bool(obj.get("traction_active", snap.traction.active)),
                    sensor_fault=bool(obj.get("traction_fault", snap.traction.sensor_fault)),
                    wheelie_pitch_deg=float(obj.get("lean_deg", snap.traction.wheelie_pitch_deg)),
                )
                clutch = ClutchState(
                    slip_pct=float(obj.get("clutch_slip_pct", snap.clutch.slip_pct)),
                    severity=str(obj.get("clutch_slip_severity", snap.clutch.severity)),
                )
                lighting = LightingState(
                    left_indicator=bool(obj.get("left_indicator", obj.get("turn_left", snap.lighting.left_indicator))),
                    right_indicator=bool(obj.get("right_indicator", obj.get("turn_right", snap.lighting.right_indicator))),
                    high_beam=bool(obj.get("high_beam", snap.lighting.high_beam)),
                    neutral=bool(obj.get("neutral_light", obj.get("neutral", eng.gear == "N"))),
                    brake=bool(obj.get("brake_light", obj.get("brake", snap.lighting.brake))),
                    oil_warning=bool(obj.get("oil_warning", snap.lighting.oil_warning)),
                )
                service = ServiceStatus(
                    recent_can_frames=_demo_recent_can_frames(obj),
                    sensor_voltages=(
                        ServiceReading("Oil pressure sensor", f"{float(obj.get('oil_sensor_v', 2.75)):.2f} V"),
                        ServiceReading("WMI tank sender", f"{float(obj.get('wmi_tank_v', 3.25)):.2f} V"),
                        ServiceReading("Controller 3.3V rail", f"{float(obj.get('arduino_5v', 3.30)):.2f} V"),
                        ServiceReading("Air tank pressure sender", f"{float(obj.get('air_tank_v', 2.95)):.2f} V"),
                    ),
                    pin_states=(
                        ServiceFlag("Left indicator", lighting.left_indicator),
                        ServiceFlag("Right indicator", lighting.right_indicator),
                        ServiceFlag("High beam", lighting.high_beam),
                        ServiceFlag("Neutral switch", lighting.neutral),
                        ServiceFlag("Brake light", lighting.brake),
                        ServiceFlag("Oil warning lamp", lighting.oil_warning),
                        ServiceFlag("WMI pressure OK", bool(obj.get("wmi_pressure_ok", True))),
                    ),
                    relay_states=(
                        ServiceFlag("WMI pump", bool(obj.get("wmi_pump_relay", obj.get("wmi_arm", False)))),
                        ServiceFlag("Flame enable", bool(obj.get("flame_mode", False))),
                        ServiceFlag("Air shot solenoid", air.is_firing),
                        ServiceFlag("Air compressor", bool(obj.get("air_compressor", air.pressure_psi < 68.0))),
                        ServiceFlag("WG1 enable", int(obj.get("wg1", 0)) > 0),
                        ServiceFlag("WG2 enable", int(obj.get("wg2", 0)) > 0),
                    ),
                    firmware_versions=(
                        ServiceReading("Pi HUD", "local/dev"),
                        ServiceReading("Teensy controller", str(obj.get("arduino_fw", "demo"))),
                    ),
                )
                limp_active = bool(obj.get("limp_mode", snap.system.limp_mode_active))
                limp_reason = str(obj.get("limp_reason", snap.system.limp_mode_reason or ("PI REQUEST" if limp_active else ""))).upper()
                updated = replace(
                    snap,
                    engine=eng,
                    temps=temps,
                    environment=env,
                    economy=economy,
                    traction=trac,
                    clutch=clutch,
                    lighting=lighting,
                    air_shot=air,
                    wmi=wmi,
                    service=service,
                    system=SystemStatus(limp_mode_active=limp_active, limp_mode_reason=limp_reason if limp_active else ""),
                )
                renderer.update_state(
                    replace(
                        updated,
                        engine=replace(updated.engine, target_boost_psi=calculate_boost_target(updated)),
                    )
                )

        threading.Thread(target=loop, name="demo-udp", daemon=True).start()

    if not args.can_interface and not args.simulator and not args.snapshot:
        _start_demo_udp_listener(args.demo_udp_listen)

    def _shutdown_handler(*_: object) -> None:
        authority_stop_event.set()
        if nfc_authorizer:
            nfc_authorizer.stop()
        systemd_notifier.stopping()
        if can_interface:
            can_interface.stop()
        pygame.quit()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown_handler)

    try:
        if args.snapshot:
            if aggregator is not None:
                snapshot = aggregator.wait_for_snapshot(timeout=2.0)
            else:
                snapshot = (simulator or StateSimulator()).sample()
            surface = renderer.capture_frame(snapshot)
            output_path = args.snapshot
            output_path.parent.mkdir(parents=True, exist_ok=True)
            pygame.image.save(surface, str(output_path))
        else:
            if stream is None:
                stream = []
            systemd_notifier.ready()
            renderer.run(stream)
    except Exception:
        logging.exception("HUD runtime error")
        raise
    finally:
        authority_stop_event.set()
        if nfc_authorizer:
            nfc_authorizer.stop()
        systemd_notifier.stopping()
        if can_interface:
            can_interface.stop()


if __name__ == "__main__":
    main()
