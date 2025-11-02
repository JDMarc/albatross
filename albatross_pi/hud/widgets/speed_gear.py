"""Speed and gear indicator widget."""
from __future__ import annotations

import pygame

from .base import Color, Widget
from ...state.snapshot import StateSnapshot

SPEED_COLOR: Color = (255, 200, 120)
GEAR_COLOR: Color = (255, 80, 0)
TEXT_COLOR: Color = (200, 200, 200)
BG_COLOR: Color = (10, 10, 10)

_FONT_CACHE: dict[tuple[int, bool], pygame.font.Font] = {}


def _font(size: int, *, bold: bool = False) -> pygame.font.Font:
    key = (size, bold)
    font = _FONT_CACHE.get(key)
    if font is None:
        font = pygame.font.SysFont("Courier", size, bold=bold)
        _FONT_CACHE[key] = font
    return font


class SpeedGear(Widget):
    def __init__(self, speed_rect: pygame.Rect, gear_rect: pygame.Rect) -> None:
        self.speed_rect = speed_rect
        self.gear_rect = gear_rect

    def draw(self, surface: pygame.Surface, state: StateSnapshot) -> None:
        speed_surface = pygame.Surface(self.speed_rect.size)
        speed_surface.fill(BG_COLOR)
        speed_font_size = max(32, int(self.speed_rect.height * 0.7))
        speed_text = f"{state.engine.speed_mph:3.0f}"
        speed_render = _font(speed_font_size, bold=True).render(speed_text, True, SPEED_COLOR)
        speed_surface.blit(
            speed_render,
            (
                self.speed_rect.width // 2 - speed_render.get_width() // 2,
                self.speed_rect.height // 2 - speed_render.get_height() // 2,
            ),
        )

        label_size = max(16, int(self.speed_rect.height * 0.2))
        label_render = _font(label_size).render("MPH", True, TEXT_COLOR)
        speed_surface.blit(
            label_render,
            (
                self.speed_rect.width // 2 - label_render.get_width() // 2,
                self.speed_rect.height - label_render.get_height() - 6,
            ),
        )
        surface.blit(speed_surface, self.speed_rect)

        gear_surface = pygame.Surface(self.gear_rect.size)
        gear_surface.fill(BG_COLOR)
        gear_font_size = max(28, int(min(self.gear_rect.width, self.gear_rect.height) * 0.7))
        gear_render = _font(gear_font_size, bold=True).render(state.engine.gear, True, GEAR_COLOR)
        gear_surface.blit(
            gear_render,
            (
                self.gear_rect.width // 2 - gear_render.get_width() // 2,
                self.gear_rect.height // 2 - gear_render.get_height() // 2,
            ),
        )
        surface.blit(gear_surface, self.gear_rect)
