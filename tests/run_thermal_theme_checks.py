"""Headless checks for themed thermal chrome and invariant measurement colors."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pygame

from albatross_pi.hud.thermal_style import thermal_chrome
from albatross_pi.hud.thermal_views import ThermalViews
from albatross_pi.hud.widgets.ui_utils import THEME_COLORS
from albatross_pi.state.snapshot import EngineState, StateSnapshot
from albatross_pi.thermal.simulation import ThermalSimulator


THEMES = ("AMBER", "NIGHT", "NIGHT OPS", "HIGH-CON")
PATHS = {
    "charge": ((160, 125), (57, 169, 184)),
    "exhaust": ((42, 305), (195, 108, 60)),
    "coolant": ((295, 150), (72, 125, 175)),
    "oil": ((85, 375), (167, 143, 66)),
}


def map_area(size):
    """Match ThermalViews' shared content/detail layout, in display pixels."""
    sw, sh = size
    panel = pygame.Rect(20, 54, sw - 40, sh - 82)
    content = pygame.Rect(panel.x + 12, panel.y + 42, panel.width - 24, panel.height - 70)
    detail_w = max(255, content.width // 4)
    return pygame.Rect(content.x, content.y, content.width - detail_w - 12, content.height - 18)


def pixel(surface, area, xy):
    x, y = xy
    position = (round(area.x + x * area.width / 1000),
                round(area.y + y * area.height / 400))
    return tuple(surface.get_at(position)[:3])


def phase(animation):
    return (animation.last_ms, dict(animation.rotors), dict(animation.speeds),
            animation.flow, animation.raster)


def check():
    pygame.init()
    state = StateSnapshot(thermal=ThermalSimulator().step(40),
                          engine=EngineState(boost_left_psi=5, boost_right_psi=15))
    output = os.environ.get("ALBATROSS_THERMAL_THEME_PREVIEWS")
    if output:
        Path(output).mkdir(parents=True, exist_ok=True)

    # These fields are purely decorative; HIGH-CON must not pick up a cyan tint.
    required = {"field", "panel", "surface", "component", "shadow", "raster", "grid",
                "sweep", "centerline", "ticks", "edge", "ink", "muted", "bright"}
    for theme in THEMES:
        chrome = thermal_chrome(THEME_COLORS[theme])
        assert required <= chrome.keys(), (theme, "missing chrome entries")
        for key in required:
            color = chrome[key]
            assert len(color) == 3 and all(isinstance(c, int) and 0 <= c <= 255 for c in color), (theme, key, color)
            if theme == "HIGH-CON":
                assert len(set(color)) == 1, (theme, key, "decorative color is not grayscale", color)

    for size in ((1280, 480), (1920, 720)):
        for page in ("thermal_abs", "thermal_dev"):
            views = ThermalViews()
            views.map_selected = "HEAD_METAL_RIGHT"
            views.animation.advance(state.engine, 0)
            views.animation.advance(state.engine, 100)
            # Put the sweep on a clear part of the left margin.
            views.animation.raster = 177.0
            initial_phase = phase(views.animation)
            area = map_area(size)
            reference_geometry = None
            reference_stripes = None
            backgrounds = {}
            grids = {}
            sweeps = {}
            for theme in THEMES:
                colors = THEME_COLORS[theme]
                chrome = thermal_chrome(colors)
                surface = pygame.Surface(size)
                surface.fill(colors[0])
                with patch("pygame.time.get_ticks", return_value=100):
                    views.draw(surface, state, page, colors)
                assert views.map_selected == "HEAD_METAL_RIGHT"
                assert phase(views.animation) == initial_phase, (theme, "theme changed animation")
                geometry = dict(views.map_rects)
                if reference_geometry is None:
                    reference_geometry = geometry
                assert geometry == reference_geometry, (theme, "theme changed hit targets")

                backgrounds[theme] = pixel(surface, area, (25, 35))
                grids[theme] = pixel(surface, area, (40, 35))
                sweeps[theme] = pixel(surface, area, (20, 177))
                assert backgrounds[theme] == chrome["field"], (size, page, theme, "field", backgrounds[theme], chrome["field"])
                assert grids[theme] == chrome["grid"], (size, page, theme, "grid", grids[theme], chrome["grid"])
                assert sweeps[theme] == chrome["sweep"], (size, page, theme, "sweep", sweeps[theme], chrome["sweep"])

                stripes = {}
                for key, rect in geometry.items():
                    if key == views.map_selected:
                        continue
                    reading = state.thermal.get(key)
                    score = reading.thermal_dev if page == "thermal_dev" else reading.thermal_abs
                    expected = views._score_color(score, reading.valid)
                    color = tuple(surface.get_at((rect.x + 3, rect.centery))[:3])
                    assert color == expected, (size, page, theme, key, "heat stripe", color, expected)
                    stripes[key] = color
                if reference_stripes is None:
                    reference_stripes = stripes
                assert stripes == reference_stripes, (theme, "theme changed heat colors")
                for name, (xy, expected) in PATHS.items():
                    actual = pixel(surface, area, xy)
                    assert actual == expected, (size, page, theme, name, "path color", actual, expected)

                if output and size == (1280, 480):
                    filename = f"thermal-theme-{theme.lower().replace(' ', '-')}-{page.removeprefix('thermal_')}.png"
                    pygame.image.save(surface, str(Path(output) / filename))

            for category in (backgrounds, grids, sweeps):
                assert len({category[theme] for theme in THEMES[:3]}) == 3, (page, "chromatic themes did not alter chrome", category)
    pygame.quit()
    print("PASS thermal themes: ABS/DEV at both sizes, themed chrome, invariant heat/path colors, stable selection and animation")


if __name__ == "__main__":
    check()
