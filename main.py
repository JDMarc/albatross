"""Entry point for running the Albatross HUD demo."""
from __future__ import annotations

import argparse

from albatross_pi.hud.renderer import HUDRenderer
from albatross_pi.state.simulator import StateSimulator


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Albatross HUD demo")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=480)
    args = parser.parse_args()

    renderer = HUDRenderer(screen_size=(args.width, args.height))
    simulator = StateSimulator()
    renderer.run(simulator.stream())


if __name__ == "__main__":
    main()
