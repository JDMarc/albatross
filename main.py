"""Entry point for running the Albatross HUD demo."""
from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
from pathlib import Path
from typing import Iterable, Iterator

import pygame

from albatross_pi.canbus import CANStateAggregator, SocketCANInterface
from albatross_pi.hud.renderer import HUDRenderer
from albatross_pi.state.simulator import StateSimulator
from albatross_pi.state.snapshot import StateSnapshot


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
    parser.add_argument("--can-bitrate", type=int, help="Bitrate hint for SocketCAN setup")
    parser.add_argument("--can-rate", type=float, default=60.0, help="HUD update rate when using CAN")
    parser.add_argument("--log-level", default="INFO", help="Python logging level")
    parser.add_argument(
        "--snapshot",
        type=Path,
        help="Render a single frame to the specified image file and exit",
    )
    args = parser.parse_args()

    _configure_logging(args.log_level)

    if args.snapshot:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

    renderer = HUDRenderer(
        screen_size=(args.width, args.height),
        use_display=args.snapshot is None,
    )
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
    else:
        simulator = StateSimulator()
        if not args.snapshot:
            stream = simulator.stream()

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
            assert stream is not None
            renderer.run(stream)
    finally:
        if can_interface:
            can_interface.stop()


if __name__ == "__main__":
    main()
