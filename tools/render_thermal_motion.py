"""Render a synthetic boost sweep as a GIF; no CAN/network or vehicle control.

Optional development dependencies: Pygame and Pillow.
"""
import argparse
import math
import os
import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image
import pygame
from albatross_pi.hud.thermal_views import ThermalViews
from albatross_pi.state.snapshot import StateSnapshot, EngineState
from albatross_pi.thermal.simulation import ThermalSimulator


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="Destination GIF path")
    target = parser.parse_args().output
    pygame.init()
    try:
        surface = pygame.Surface((1280, 480))
        views = ThermalViews()
        title_font = pygame.font.Font(None, 23)
        colors = ((4, 12, 17), (255, 198, 64), (148, 166, 167), (255, 80, 40))
        thermal = ThermalSimulator().step(40)
        frames = []
        for n in range(90):
            boost = 20 * (1 - math.cos(2 * math.pi * n / 90)) / 2
            state = replace(StateSnapshot(), thermal=thermal, engine=EngineState(boost_psi=boost))
            surface.fill((3, 9, 14))
            # Explicit deterministic presentation clock, no realtime waiting.
            with patch("pygame.time.get_ticks", return_value=n * 50):
                views.draw(surface, state, "thermal_abs", colors)
            title = title_font.render(
                f"SYNTHETIC BOOST SWEEP: {boost:04.1f} PSI  /  VISUAL MOTION, NOT SHAFT RPM",
                True, (194, 217, 219),
            )
            surface.blit(title, (24, 20))
            frames.append(Image.frombytes("RGB", surface.get_size(), pygame.image.tostring(surface, "RGB")))
        target.parent.mkdir(parents=True, exist_ok=True)
        frames[0].save(target, save_all=True, append_images=frames[1:], duration=50, loop=0, optimize=False)
        print(target)
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
