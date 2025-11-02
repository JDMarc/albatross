"""Top header widget."""
from __future__ import annotations

import pygame

from .base import Color, Widget
from ...state.snapshot import StateSnapshot

BG_COLOR: Color = (5, 5, 5)
TEXT_COLOR: Color = (255, 180, 120)
ICON_COLOR: Color = (120, 200, 255)
WARN_COLOR: Color = (255, 80, 80)

FONT_CACHE: dict[int, pygame.font.Font] = {}


def _font(size: int) -> pygame.font.Font:
    font = FONT_CACHE.get(size)
    if font is None:
        font = pygame.font.SysFont("Courier", size, bold=True)
        FONT_CACHE[size] = font
    return font


class HeaderBar(Widget):
    def __init__(self, rect: pygame.Rect) -> None:
        self.rect = rect

    def draw(self, surface: pygame.Surface, state: StateSnapshot) -> None:
        pygame.draw.rect(surface, BG_COLOR, self.rect)
        env = state.environment
        mode_surface = _font(24).render(env.mode, True, TEXT_COLOR)
        surface.blit(mode_surface, (self.rect.x + 10, self.rect.y + 6))

        fuel_surface = _font(20).render(f"Fuel {env.fuel_type}", True, TEXT_COLOR)
        surface.blit(fuel_surface, (self.rect.x + 10, self.rect.y + 34))

        time_surface = _font(20).render(env.time.strftime("%H:%M:%S"), True, ICON_COLOR)
        surface.blit(time_surface, (self.rect.centerx - time_surface.get_width() // 2, self.rect.y + 10))

        ambient_text = f"{env.ambient_temp_f:3.0f}F"
        ambient_surface = _font(18).render(ambient_text, True, TEXT_COLOR)
        surface.blit(ambient_surface, (self.rect.right - ambient_surface.get_width() - 10, self.rect.y + 8))

        gps_text = "GPS" if env.gps_lock else "GPS?"
        gps_color = ICON_COLOR if env.gps_lock else WARN_COLOR
        gps_surface = _font(18).render(gps_text, True, gps_color)
        surface.blit(gps_surface, (self.rect.right - gps_surface.get_width() - 10, self.rect.y + 30))

        if env.rain:
            rain_surface = _font(18).render("RAIN", True, WARN_COLOR)
            surface.blit(rain_surface, (self.rect.right - rain_surface.get_width() - 10, self.rect.y + 50))
