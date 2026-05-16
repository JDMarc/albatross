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
from pathlib import Path
from typing import Iterable, Iterator

import pygame

from albatross_pi.canbus import CANStateAggregator, SocketCANInterface, build_traction_level_frame
from albatross_pi.hud.renderer import HUDRenderer
from albatross_pi.state.simulator import StateSimulator
from albatross_pi.state.snapshot import StateSnapshot
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
    elif args.simulator:
        simulator = StateSimulator()
        if not args.snapshot:
            stream = simulator.stream()

    def _start_demo_udp_listener(addr: str) -> None:
        host, port_s = addr.split(":")
        port = int(port_s)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((host, port))
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
                    speed_mph=float(obj.get("speed_mph", snap.engine.speed_mph)),
                    boost_psi=float(obj.get("boost", snap.engine.boost_psi)),
                    throttle_pct=float(obj.get("tps", snap.engine.throttle_pct)),
                    gear=str(obj.get("gear", snap.engine.gear)),
                )
                temps = replace(
                    snap.temps,
                    coolant_temp_f=float(obj.get("clt_f", snap.temps.coolant_temp_f)),
                    oil_temp_f=float(obj.get("oilt_f", snap.temps.oil_temp_f)),
                    oil_pressure_psi=float(obj.get("oilp", snap.temps.oil_pressure_psi)),
                )
                env = replace(
                    snap.environment,
                    mode=str(obj.get("mode", snap.environment.mode)),
                    fuel_level_pct=float(obj.get("fuel", snap.environment.fuel_level_pct)),
                    message_line=str(obj.get("msg", snap.environment.message_line)),
                )
                trac = replace(snap.traction, intervention_level=str(obj.get("traction", snap.traction.intervention_level)))
                renderer.update_state(replace(snap, engine=eng, temps=temps, environment=env, traction=trac))

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
