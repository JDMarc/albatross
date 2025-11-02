"""Speed and gear indicator widget."""
from __future__ import annotations

import pygame

from .base import Color, Widget
from ...state.snapshot import StateSnapshot

SPEED_COLOR: Color = (255, 200, 120)
GEAR_COLOR: Color = (255, 80, 0)
TEXT_COLOR: Color = (200, 200, 200)

FONT_CACHE: dict[int, pygame.font.Font] = {}


def _font(size: int) -> pygame.font.Font:
    font = FONT_CACHE.get(size)
    if font is None:
        font = pygame.font.SysFont("Courier", size, bold=True)
        FONT_CACHE[size] = font
    return font


class SpeedGear(Widget):
    def __init__(self, speed_rect: pygame.Rect, gear_rect: pygame.Rect) -> None:
        self.speed_rect = speed_rect
        self.gear_rect = gear_rect

    def draw(self, surface: pygame.Surface, state: StateSnapshot) -> None:
        speed_text = f"{state.engine.speed_mph:3.0f}"
        speed_surface = _font(72).render(speed_text, True, SPEED_COLOR)
        speed_bg = pygame.Surface(self.speed_rect.size)
        speed_bg.fill((10, 10, 10))
        surface.blit(speed_bg, self.speed_rect)
        surface.blit(speed_surface, (
            self.speed_rect.centerx - speed_surface.get_width() // 2,
            self.speed_rect.centery - speed_surface.get_height() // 2,
        ))

        gear_surface = _font(60).render(state.engine.gear, True, GEAR_COLOR)
        gear_bg = pygame.Surface(self.gear_rect.size)
        gear_bg.fill((10, 10, 10))
        surface.blit(gear_bg, self.gear_rect)
        surface.blit(gear_surface, (
            self.gear_rect.centerx - gear_surface.get_width() // 2,
            self.gear_rect.centery - gear_surface.get_height() // 2,
        ))

        label_surface = _font(18).render("MPH", True, TEXT_COLOR)
        surface.blit(
            label_surface,
            (
                self.speed_rect.centerx - label_surface.get_width() // 2,
                self.speed_rect.bottom - label_surface.get_height() - 4,
            ),
        )
