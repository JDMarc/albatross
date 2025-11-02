"""Top header widget."""
from __future__ import annotations

import pygame

from .base import Color, Widget
from ...state.snapshot import StateSnapshot

BG_COLOR: Color = (5, 5, 5)
TEXT_COLOR: Color = (255, 180, 120)
ICON_COLOR: Color = (120, 200, 255)
WARN_COLOR: Color = (255, 80, 80)

_FONT_CACHE: dict[int, pygame.font.Font] = {}


def _font(size: int, *, bold: bool = False) -> pygame.font.Font:
    key = (size, bold)
    font = _FONT_CACHE.get(key)
    if font is None:
        font = pygame.font.SysFont("Courier", size, bold=bold)
        _FONT_CACHE[key] = font
    return font


class HeaderBar(Widget):
    def __init__(self, rect: pygame.Rect) -> None:
        self.rect = rect

    def draw(self, surface: pygame.Surface, state: StateSnapshot) -> None:
        pygame.draw.rect(surface, BG_COLOR, self.rect)
        env = state.environment
        padding = max(8, int(self.rect.height * 0.15))
        line_height = max(16, int(self.rect.height * 0.35))

        mode_surface = _font(line_height, bold=True).render(env.mode, True, TEXT_COLOR)
        surface.blit(mode_surface, (self.rect.x + padding, self.rect.y + padding // 2))

        fuel_surface = _font(max(14, int(line_height * 0.75))).render(
            f"Fuel {env.fuel_type}", True, TEXT_COLOR
        )
        surface.blit(fuel_surface, (self.rect.x + padding, self.rect.y + padding // 2 + line_height))

        time_surface = _font(max(14, int(line_height * 0.8))).render(
            env.time.strftime("%H:%M:%S"), True, ICON_COLOR
        )
        surface.blit(
            time_surface,
            (
                self.rect.centerx - time_surface.get_width() // 2,
                self.rect.y + padding // 2,
            ),
        )

        ambient_surface = _font(max(14, int(line_height * 0.7))).render(
            f"{env.ambient_temp_f:3.0f}F", True, TEXT_COLOR
        )
        surface.blit(
            ambient_surface,
            (
                self.rect.right - ambient_surface.get_width() - padding,
                self.rect.y + padding // 2,
            ),
        )

        gps_text = "GPS" if env.gps_lock else "GPS?"
        gps_color = ICON_COLOR if env.gps_lock else WARN_COLOR
        gps_surface = _font(max(14, int(line_height * 0.7))).render(gps_text, True, gps_color)
        surface.blit(
            gps_surface,
            (
                self.rect.right - gps_surface.get_width() - padding,
                self.rect.y + padding // 2 + line_height,
            ),
        )

        if env.rain:
            rain_surface = _font(max(14, int(line_height * 0.7))).render("RAIN", True, WARN_COLOR)
            surface.blit(
                rain_surface,
                (
                    self.rect.right - rain_surface.get_width() - padding,
                    self.rect.y + padding // 2 + 2 * line_height,
                ),
            )
