"""eTRAC and wheelie indicators."""
from __future__ import annotations

import pygame

from .base import Color, Widget
from ...state.snapshot import StateSnapshot

BG_COLOR: Color = (12, 12, 12)
BAR_BG: Color = (40, 40, 40)
BAR_COLOR: Color = (120, 200, 255)
TEXT_COLOR: Color = (200, 200, 200)

FONT_CACHE: dict[int, pygame.font.Font] = {}


def _font(size: int) -> pygame.font.Font:
    font = FONT_CACHE.get(size)
    if font is None:
        font = pygame.font.SysFont("Courier", size)
        FONT_CACHE[size] = font
    return font


class TractionPanel(Widget):
    def __init__(self, rect: pygame.Rect) -> None:
        self.rect = rect

    def draw(self, surface: pygame.Surface, state: StateSnapshot) -> None:
        pygame.draw.rect(surface, BG_COLOR, self.rect)
        slip_pct = state.traction.slip_pct
        bar_rect = pygame.Rect(self.rect.x + 8, self.rect.y + 24, self.rect.width - 16, 14)
        pygame.draw.rect(surface, BAR_BG, bar_rect)
        fill = bar_rect.copy()
        fill.width = int(bar_rect.width * min(1.0, slip_pct / 20.0))
        pygame.draw.rect(surface, BAR_COLOR, fill)

        slip_text = f"Slip {slip_pct:4.1f}%"
        slip_surface = _font(18).render(slip_text, True, TEXT_COLOR)
        surface.blit(slip_surface, (self.rect.x + 8, self.rect.y + 4))

        wheelie_text = f"Pitch {state.traction.wheelie_pitch_deg:+4.1f}°"
        wheelie_surface = _font(18).render(wheelie_text, True, TEXT_COLOR)
        surface.blit(wheelie_surface, (self.rect.x + 8, self.rect.y + 48))

        level_surface = _font(18).render(state.traction.intervention_level, True, BAR_COLOR)
        surface.blit(level_surface, (self.rect.right - level_surface.get_width() - 8, self.rect.y + 4))
