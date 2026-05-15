"""Top header widget."""
from __future__ import annotations

import pygame

from .base import Widget
from .ui_utils import AMBER_BG, AMBER_BRIGHT, AMBER_GLOW, FAULT_AMBER, fit_font_size, font
from ...state.snapshot import StateSnapshot



class HeaderBar(Widget):
    def __init__(self, rect: pygame.Rect) -> None:
        self.rect = rect

    def draw(self, surface: pygame.Surface, state: StateSnapshot) -> None:
        pygame.draw.rect(surface, AMBER_BG, self.rect)
        env = state.environment
        padding = max(8, int(self.rect.height * 0.15))
        line_height = max(16, int(self.rect.height * 0.35))

        mode_size = fit_font_size(env.mode, int(self.rect.width * 0.22), line_height, start_size=line_height, bold=True)
        mode_surface = font(mode_size, bold=True).render(env.mode, True, AMBER_BRIGHT)
        surface.blit(mode_surface, (self.rect.x + padding, self.rect.y + padding // 2))

        fuel_text = f"Fuel {env.fuel_type}"
        fuel_size = fit_font_size(fuel_text, int(self.rect.width * 0.22), line_height, start_size=max(14, int(line_height * 0.75)))
        fuel_surface = font(fuel_size).render(fuel_text, True, AMBER_GLOW)
        surface.blit(fuel_surface, (self.rect.x + padding, self.rect.y + padding // 2 + line_height))

        time_surface = font(max(14, int(line_height * 0.8))).render(env.time.strftime("%H:%M:%S"), True, AMBER_GLOW)
        surface.blit(
            time_surface,
            (
                self.rect.centerx - time_surface.get_width() // 2,
                self.rect.y + padding // 2,
            ),
        )

        ambient_surface = font(max(14, int(line_height * 0.7))).render(f"{env.ambient_temp_f:3.0f}F", True, AMBER_BRIGHT)
        surface.blit(
            ambient_surface,
            (
                self.rect.right - ambient_surface.get_width() - padding,
                self.rect.y + padding // 2,
            ),
        )

        gps_text = "GPS" if env.gps_lock else "GPS?"
        gps_color = AMBER_GLOW if env.gps_lock else FAULT_AMBER
        gps_surface = font(max(14, int(line_height * 0.7))).render(gps_text, True, gps_color)
        surface.blit(
            gps_surface,
            (
                self.rect.right - gps_surface.get_width() - padding,
                self.rect.y + padding // 2 + line_height,
            ),
        )

        if env.rain:
            rain_surface = font(max(14, int(line_height * 0.7))).render("RAIN", True, FAULT_AMBER)
            surface.blit(
                rain_surface,
                (
                    self.rect.right - rain_surface.get_width() - padding,
                    self.rect.y + padding // 2 + 2 * line_height,
                ),
            )
