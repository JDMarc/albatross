"""Entry point for running the Albatross HUD demo."""
from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Iterable, Iterator

import pygame

from albatross_pi.canbus import CANStateAggregator, SocketCANInterface, build_mode_selection_frame, build_traction_level_frame
from albatross_pi.canbus.encode import (
    build_boost_target_frame,
    build_engine_run_switch_frame,
    build_flame_mode_frame,
    build_limp_mode_frame,
    build_media_control_frame,
    build_phone_link_frame,
)
from albatross_pi.hud.renderer import HUDRenderer
from albatross_pi.state.simulator import StateSimulator
from albatross_pi.state.snapshot import StateSnapshot
from albatross_pi.phone import PhoneBridge, PhoneStatus
from dataclasses import replace


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
    parser.add_argument("--phone-bt-mac", help="Paired phone Bluetooth MAC for media/weather/GPS bridge")
    parser.add_argument("--phone-telemetry-udp", default="127.0.0.1:5010", help="UDP host:port for phone weather/GPS telemetry")
    parser.add_argument("--bind-inputs", action="store_true", help="Prompt keyboard bindings for demo controls")
    parser.add_argument(
        "--snapshot",
        type=Path,
        help="Render a single frame to the specified image file and exit",
    )
    args = parser.parse_args()

    _configure_logging(args.log_level)

    if args.snapshot:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

    try:
        renderer = HUDRenderer(
            screen_size=(args.width, args.height),
            use_display=args.snapshot is None,
        )
    except Exception:
        logging.exception("HUD renderer failed to initialize")
        raise
    if args.bind_inputs and not args.snapshot:
        ack_name = input("POST acknowledge key (default: return): ").strip().lower() or "return"
        try:
            ack_key = pygame.key.key_code(ack_name)
        except ValueError:
            logging.warning("Unknown key binding '%s'; using RETURN", ack_name)
            ack_key = pygame.K_RETURN
        renderer.configure_input_bindings(ack_key)
    phone_bridge: PhoneBridge | None = None

    def _apply_phone_status(status: PhoneStatus) -> None:
        snap = renderer.state
        env = replace(
            snap.environment,
            ambient_temp_f=status.ambient_temp_f if status.ambient_temp_f is not None else snap.environment.ambient_temp_f,
            gps_lock=status.gps_lock if status.gps_lock is not None else snap.environment.gps_lock,
            rain=status.rain if status.rain is not None else snap.environment.rain,
            time=status.phone_time if status.phone_time is not None else snap.environment.time,
            message_line=(f"♫ {status.artist} - {status.track}"[:96] if status.track else snap.environment.message_line),
        )
        if status.gps_lat is not None and status.gps_lon is not None:
            env = replace(env, message_line=f"GPS {status.gps_lat:.5f}, {status.gps_lon:.5f}")
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

        def _send_mode_selection(mode_code: int) -> None:
            frame = build_mode_selection_frame(mode_code)
            assert can_interface is not None
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

        def _safety_supervisor() -> None:
            assert aggregator is not None and can_interface is not None
            last_fault_state = False
            critical_oil_start: float | None = None
            last_engine_run_switch_enabled = True
            last_escalation_ts = 0.0
            while True:
                snap = aggregator.current_snapshot()
                faults: list[str] = []
                now_ts = time.time()

                # Comms/freshness (simple): if key telemetry never appears or drops to all-zero under throttle.
                if snap.engine.throttle_pct > 15 and snap.engine.rpm < 300:
                    faults.append("ECU STALE")
                if snap.engine.rpm > 0 and snap.engine.speed_mph == 0 and snap.engine.gear not in ("N", "?"):
                    faults.append("SPEED SENSOR")
                # RPM/speed mismatch can indicate clutch slip under load, not only sensor error.
                if (
                    snap.engine.rpm > 7000
                    and snap.engine.throttle_pct > 55
                    and snap.engine.speed_mph < 20
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
                    faults.append("EGT HOT")
                if (
                    snap.engine.boost_psi > 10.0
                    and snap.engine.rpm > 3000
                    and snap.temps.exhaust_temp_f > 1400
                    and abs(snap.engine.boost_psi - (snap.temps.exhaust_temp_f / 100.0)) > 9.0
                ):
                    faults.append("CYL EGT BOOST MISMATCH")
                if snap.engine.knock_events >= 3:
                    faults.append("KNOCK")
                if snap.environment.fuel_level_pct <= 5:
                    faults.append("LOW FUEL")

                severe = any(f in faults for f in ("ECU STALE", "LOW OIL PRESS", "COOLANT HOT", "EGT HOT", "CLUTCH SLIP"))

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
                    or ("EGT HOT" in faults and snap.temps.exhaust_temp_f > 1725 and snap.engine.rpm > 2200)
                )
                if severe and not last_fault_state:
                    # Fail-safe action set: cut boost command, enable limp, disable flame, max traction.
                    for frame in (
                        build_boost_target_frame(0.0),
                        build_limp_mode_frame(True),
                        build_flame_mode_frame(False),
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
                    for frame in (
                        build_boost_target_frame(0.0),
                        build_limp_mode_frame(True),
                        build_flame_mode_frame(False),
                        build_traction_level_frame(3),
                    ):
                        can_interface.send(*frame)
                        aggregator.mark_sent_frame(*frame)
                    faults.append("ENGINE SHUTDOWN REQUEST")
                    logging.critical("Critical oil pressure persisted; shutdown request issued in neutral at low speed.")

                # Engine run switch "OFF" acts as ECU-level kill (ignition/fuel cut).
                # Re-send every 1s while active for robustness against frame loss.
                if should_cut_run_switch:
                    if last_engine_run_switch_enabled or (now_ts - last_escalation_ts) >= 1.0:
                        frame = build_engine_run_switch_frame(False)
                        can_interface.send(*frame)
                        aggregator.mark_sent_frame(*frame)
                        last_escalation_ts = now_ts
                    last_engine_run_switch_enabled = False
                    faults.append("ENGINE RUN SWITCH OFF")
                elif not last_engine_run_switch_enabled:
                    frame = build_engine_run_switch_frame(True)
                    can_interface.send(*frame)
                    aggregator.mark_sent_frame(*frame)
                    last_engine_run_switch_enabled = True
                    logging.info("Safety supervisor restored engine run switch to ON.")

                if faults:
                    renderer.update_state(replace(snap, faults=tuple(sorted(set(faults)))))
                last_fault_state = severe
                time.sleep(0.2)

        threading.Thread(target=_safety_supervisor, name="safety-supervisor", daemon=True).start()
    elif args.simulator:
        simulator = StateSimulator()
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
                    boost_psi=float(obj.get("boost", snap.engine.boost_psi)),
                    throttle_pct=float(obj.get("tps", snap.engine.throttle_pct)),
                    gear=str(obj.get("gear", snap.engine.gear)),
                    afr_left=float(obj.get("afr_l", snap.engine.afr_left)),
                    afr_right=float(obj.get("afr_r", snap.engine.afr_right)),
                    knock_events=int(bin(int(obj.get("knock_mask", 0))).count("1")) if "knock_mask" in obj else snap.engine.knock_events,
                    engine_load_pct=float(obj.get("load", snap.engine.engine_load_pct)),
                    target_boost_psi=(float(obj.get("turbo1", snap.engine.target_boost_psi)) + float(obj.get("turbo2", snap.engine.target_boost_psi))) / 2.0,
                    wastegate_duty_pct=(float(obj.get("wg1", snap.engine.wastegate_duty_pct)) + float(obj.get("wg2", snap.engine.wastegate_duty_pct))) / 2.0,
                )
                temps = replace(
                    snap.temps,
                    coolant_temp_f=float(obj.get("clt_f", obj.get("clt", snap.temps.coolant_temp_f))),
                    oil_temp_f=float(obj.get("oilt_f", obj.get("oilt", snap.temps.oil_temp_f))),
                    oil_pressure_psi=float(obj.get("oilp", snap.temps.oil_pressure_psi)),
                    intake_temp_f=float(obj.get("iat", snap.temps.intake_temp_f)),
                    exhaust_temp_f=(float(obj.get("egt_b1", snap.temps.exhaust_temp_f)) + float(obj.get("egt_b2", snap.temps.exhaust_temp_f))) / 2.0,
                    battery_voltage=float(obj.get("batt_v", snap.temps.battery_voltage)),
                )
                env = replace(
                    snap.environment,
                    mode=str(obj.get("mode", snap.environment.mode)),
                    fuel_level_pct=float(obj.get("fuel", snap.environment.fuel_level_pct)),
                    message_line=str(obj.get("msg", snap.environment.message_line)),
                )
                air = replace(
                    snap.air_shot,
                    pressure_psi=float(obj.get("tank_psi", snap.air_shot.pressure_psi)),
                    charges_remaining=int(obj.get("airshot_charges", snap.air_shot.charges_remaining)),
                    is_firing=bool(obj.get("airshot_firing", snap.air_shot.is_firing)),
                )
                trac = replace(
                    snap.traction,
                    intervention_level=str(obj.get("traction", snap.traction.intervention_level)),
                    wheelie_pitch_deg=float(obj.get("lean_deg", snap.traction.wheelie_pitch_deg)),
                )
                renderer.update_state(replace(snap, engine=eng, temps=temps, environment=env, traction=trac, air_shot=air))

        threading.Thread(target=loop, name="demo-udp", daemon=True).start()

    if not args.can_interface and not args.simulator and not args.snapshot:
        _start_demo_udp_listener(args.demo_udp_listen)

    def _shutdown_handler(*_: object) -> None:
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
                assert simulator is not None
                snapshot = simulator.sample()
            surface = renderer.capture_frame(snapshot)
            output_path = args.snapshot
            output_path.parent.mkdir(parents=True, exist_ok=True)
            pygame.image.save(surface, str(output_path))
        else:
            if stream is None:
                stream = []
            renderer.run(stream)
    except Exception:
        logging.exception("HUD runtime error")
        raise
    finally:
        if can_interface:
            can_interface.stop()


if __name__ == "__main__":
    main()
