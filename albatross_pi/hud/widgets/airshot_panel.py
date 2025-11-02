"""Air Shot status widget."""
from __future__ import annotations

import pygame

from .base import Color, Widget
from ...state.snapshot import StateSnapshot

BG_COLOR: Color = (15, 10, 10)
TEXT_COLOR: Color = (255, 180, 140)
FIRE_COLOR: Color = (255, 90, 0)
BAR_BG: Color = (50, 30, 30)
BAR_COLOR: Color = (255, 150, 80)

FONT_CACHE: dict[int, pygame.font.Font] = {}


def _font(size: int) -> pygame.font.Font:
    font = FONT_CACHE.get(size)
    if font is None:
        font = pygame.font.SysFont("Courier", size)
        FONT_CACHE[size] = font
    return font


class AirShotPanel(Widget):
    def __init__(self, rect: pygame.Rect, max_pressure: float = 2200.0) -> None:
        self.rect = rect
        self.max_pressure = max_pressure

    def draw(self, surface: pygame.Surface, state: StateSnapshot) -> None:
        pygame.draw.rect(surface, BG_COLOR, self.rect)
        pressure = state.air_shot.pressure_psi
        pct = min(1.0, pressure / self.max_pressure)
        bar_rect = pygame.Rect(self.rect.x + 8, self.rect.y + 24, self.rect.width - 16, 12)
        pygame.draw.rect(surface, BAR_BG, bar_rect)
        fill = bar_rect.copy()
        fill.width = int(bar_rect.width * pct)
        pygame.draw.rect(surface, BAR_COLOR, fill)

        charges_text = f"Charges {state.air_shot.charges_remaining}" \
            + (" *FIRE*" if state.air_shot.is_firing else "")
        color = FIRE_COLOR if state.air_shot.is_firing else TEXT_COLOR
        charges_surface = _font(18).render(charges_text, True, color)
        surface.blit(charges_surface, (self.rect.x + 8, self.rect.y + 4))

        pressure_surface = _font(18).render(f"{pressure:4.0f} psi", True, TEXT_COLOR)
        surface.blit(pressure_surface, (self.rect.x + 8, self.rect.y + 44))
