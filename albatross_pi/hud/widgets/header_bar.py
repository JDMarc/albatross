"""Top header widget."""
from __future__ import annotations

import pygame

from .base import Widget
from .ui_utils import AMBER_BG, AMBER_BRIGHT, AMBER_DARK, AMBER_GLOW, FAULT_AMBER, fit_font_size, font
from ...state.snapshot import StateSnapshot



class HeaderBar(Widget):
    def __init__(self, rect: pygame.Rect) -> None:
        self.rect = rect

    def _draw_turn_indicator(self, surface: pygame.Surface, center: tuple[int, int], *, left: bool, active: bool) -> None:
        color = AMBER_BRIGHT if active else AMBER_DARK
        cx, cy = center
        direction = -1 if left else 1
        points = [
            (cx + direction * -8, cy - 7),
            (cx + direction * 9, cy),
            (cx + direction * -8, cy + 7),
            (cx + direction * -4, cy + 3),
            (cx + direction * -15, cy + 3),
            (cx + direction * -15, cy - 3),
            (cx + direction * -4, cy - 3),
        ]
        pygame.draw.polygon(surface, color, points, width=0 if active else 2)

    def _draw_high_beam(self, surface: pygame.Surface, center: tuple[int, int], *, active: bool) -> None:
        color = AMBER_BRIGHT if active else AMBER_DARK
        cx, cy = center
        lamp = pygame.Rect(cx - 11, cy - 7, 11, 14)
        pygame.draw.arc(surface, color, lamp, -1.5708, 1.5708, 2)
        pygame.draw.line(surface, color, (cx - 2, cy - 7), (cx - 2, cy + 7), 2)
        for offset in (-6, -2, 2, 6):
            pygame.draw.line(surface, color, (cx + 2, cy + offset), (cx + 16, cy + offset - 3), 2)

    def _draw_lighting_status(self, surface: pygame.Surface, state: StateSnapshot, y: int) -> None:
        lighting = state.lighting
        spacing = max(28, int(self.rect.height * 0.38))
        cx = self.rect.centerx
        cy = y + max(10, int(self.rect.height * 0.15))
        self._draw_turn_indicator(surface, (cx - spacing, cy), left=True, active=lighting.left_indicator)
        self._draw_high_beam(surface, (cx, cy), active=lighting.high_beam)
        self._draw_turn_indicator(surface, (cx + spacing, cy), left=False, active=lighting.right_indicator)

    def draw(self, surface: pygame.Surface, state: StateSnapshot) -> None:
        pygame.draw.rect(surface, AMBER_BG, self.rect)
        env = state.environment
        padding = max(8, int(self.rect.height * 0.15))
        line_height = max(16, int(self.rect.height * 0.35))

        modes = ["ECO", "NORMAL", "SPORT", "RACE", "ALBATROSS"]
        mx = self.rect.x + padding
        my = self.rect.y + padding // 2
        for mode in modes:
            active = mode == env.mode
            size = fit_font_size(mode, int(self.rect.width * 0.1), line_height, start_size=line_height + (5 if active else 0), bold=active)
            color = AMBER_BRIGHT if active else AMBER_DARK
            mode_surface = font(size, bold=active).render(mode, True, color)
            surface.blit(mode_surface, (mx, my + (0 if active else 3)))
            mx += mode_surface.get_width() + 8

        fuel_text = f"Fuel {env.fuel_type}"
        if env.ethanol_content_pct >= 0:
            fuel_text = f"{fuel_text} E{env.ethanol_content_pct:02.0f}"
        fuel_size = fit_font_size(fuel_text, int(self.rect.width * 0.16), line_height, start_size=max(12, int(line_height * 0.7)))
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
        self._draw_lighting_status(surface, state, self.rect.y + padding // 2 + line_height)

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
