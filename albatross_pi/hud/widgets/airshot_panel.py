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

_FONT_CACHE: dict[int, pygame.font.Font] = {}


def _font(size: int, *, bold: bool = False) -> pygame.font.Font:
    key = (size, bold)
    font = _FONT_CACHE.get(key)
    if font is None:
        font = pygame.font.SysFont("Courier", size, bold=bold)
        _FONT_CACHE[key] = font
    return font


class AirShotPanel(Widget):
    def __init__(self, rect: pygame.Rect, max_pressure: float = 2200.0) -> None:
        self.rect = rect
        self.max_pressure = max_pressure

    def draw(self, surface: pygame.Surface, state: StateSnapshot) -> None:
        pygame.draw.rect(surface, BG_COLOR, self.rect)
        padding = max(8, int(self.rect.height * 0.18))
        bar_height = max(8, int(self.rect.height * 0.2))
        bar_rect = pygame.Rect(
            self.rect.x + padding,
            self.rect.bottom - padding - bar_height,
            self.rect.width - 2 * padding,
            bar_height,
        )
        pygame.draw.rect(surface, BAR_BG, bar_rect)
        pressure = state.air_shot.pressure_psi
        pct = min(1.0, pressure / max(1e-6, self.max_pressure))
        fill = bar_rect.copy()
        fill.width = int(bar_rect.width * pct)
        pygame.draw.rect(surface, BAR_COLOR, fill)

        charges_font = max(14, int(self.rect.height * 0.28))
        charges_text = f"Charges {state.air_shot.charges_remaining}"
        if state.air_shot.is_firing:
            charges_text += " FIRE"
        color = FIRE_COLOR if state.air_shot.is_firing else TEXT_COLOR
        charges_surface = _font(charges_font, bold=state.air_shot.is_firing).render(charges_text, True, color)
        surface.blit(
            charges_surface,
            (
                self.rect.x + padding,
                self.rect.y + padding // 2,
            ),
        )

        pressure_font = max(14, int(self.rect.height * 0.28))
        pressure_surface = _font(pressure_font).render(f"{pressure:4.0f} psi", True, TEXT_COLOR)
        surface.blit(
            pressure_surface,
            (
                self.rect.x + padding,
                bar_rect.y - pressure_surface.get_height() - 4,
            ),
        )
