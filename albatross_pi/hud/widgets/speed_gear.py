"""Speed and gear indicator widget."""
from __future__ import annotations

import pygame

from .base import Widget
from .ui_utils import AMBER_BG, AMBER_BRIGHT, AMBER_GLOW, fit_font_size, font
from ...state.snapshot import StateSnapshot


class SpeedGear(Widget):
    def __init__(self, speed_rect: pygame.Rect, gear_rect: pygame.Rect) -> None:
        self.speed_rect = speed_rect
        self.gear_rect = gear_rect

    def draw(self, surface: pygame.Surface, state: StateSnapshot) -> None:
        speed_surface = pygame.Surface(self.speed_rect.size)
        speed_surface.fill(AMBER_BG)
        speed_text = f"{state.engine.speed_mph:3.0f}"
        speed_font_size = fit_font_size(speed_text, self.speed_rect.width - 12, int(self.speed_rect.height * 0.6), start_size=max(32, int(self.speed_rect.height * 0.7)), bold=True)
        speed_render = font(speed_font_size, bold=True).render(speed_text, True, AMBER_BRIGHT)
        speed_surface.blit(
            speed_render,
            (
                self.speed_rect.width // 2 - speed_render.get_width() // 2,
                self.speed_rect.height // 2 - speed_render.get_height() // 2,
            ),
        )

        label_size = fit_font_size("MPH", self.speed_rect.width - 12, int(self.speed_rect.height * 0.2), start_size=max(14, int(self.speed_rect.height * 0.2)))
        label_render = font(label_size).render("MPH", True, AMBER_GLOW)
        speed_surface.blit(
            label_render,
            (
                self.speed_rect.width // 2 - label_render.get_width() // 2,
                self.speed_rect.height - label_render.get_height() - 6,
            ),
        )
        surface.blit(speed_surface, self.speed_rect)

        gear_surface = pygame.Surface(self.gear_rect.size)
        gear_surface.fill(AMBER_BG)
        gear_font_size = fit_font_size(state.engine.gear, self.gear_rect.width - 12, self.gear_rect.height - 12, start_size=max(24, int(min(self.gear_rect.width, self.gear_rect.height) * 0.7)), bold=True)
        gear_render = font(gear_font_size, bold=True).render(state.engine.gear, True, AMBER_BRIGHT)
        gear_surface.blit(
            gear_render,
            (
                self.gear_rect.width // 2 - gear_render.get_width() // 2,
                self.gear_rect.height // 2 - gear_render.get_height() // 2,
            ),
        )
        surface.blit(gear_surface, self.gear_rect)
