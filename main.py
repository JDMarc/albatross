"""Entry point for running the Albatross HUD demo."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import pygame

from albatross_pi.hud.renderer import HUDRenderer
from albatross_pi.state.simulator import StateSimulator


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Albatross HUD demo")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument(
        "--snapshot",
        type=Path,
        help="Render a single frame to the specified image file and exit",
    )
    args = parser.parse_args()

    if args.snapshot:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

    renderer = HUDRenderer(
        screen_size=(args.width, args.height),
        use_display=args.snapshot is None,
    )
    simulator = StateSimulator()

    if args.snapshot:
        snapshot = simulator.sample()
        surface = renderer.capture_frame(snapshot)
        output_path = args.snapshot
        output_path.parent.mkdir(parents=True, exist_ok=True)
        pygame.image.save(surface, str(output_path))
    else:
        renderer.run(simulator.stream())


if __name__ == "__main__":
    main()
