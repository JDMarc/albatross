"""eTRAC and wheelie indicators."""
from __future__ import annotations

import pygame

from .base import Color, Widget
from ...state.snapshot import StateSnapshot

BG_COLOR: Color = (12, 12, 12)
BAR_BG: Color = (40, 40, 40)
BAR_COLOR: Color = (120, 200, 255)
TEXT_COLOR: Color = (200, 200, 200)

_FONT_CACHE: dict[int, pygame.font.Font] = {}


def _font(size: int) -> pygame.font.Font:
    font = _FONT_CACHE.get(size)
    if font is None:
        font = pygame.font.SysFont("Courier", size)
        _FONT_CACHE[size] = font
    return font


class TractionPanel(Widget):
    def __init__(self, rect: pygame.Rect) -> None:
        self.rect = rect

    def draw(self, surface: pygame.Surface, state: StateSnapshot) -> None:
        pygame.draw.rect(surface, BG_COLOR, self.rect)
        padding = max(8, int(self.rect.height * 0.15))
        slip_bar_height = max(8, int(self.rect.height * 0.2))
        slip_rect = pygame.Rect(
            self.rect.x + padding,
            self.rect.y + padding + slip_bar_height,
            self.rect.width - 2 * padding,
            slip_bar_height,
        )
        pygame.draw.rect(surface, BAR_BG, slip_rect)
        fill = slip_rect.copy()
        fill.width = int(slip_rect.width * min(1.0, state.traction.slip_pct / 20.0))
        pygame.draw.rect(surface, BAR_COLOR, fill)

        label_font = max(14, int(self.rect.height * 0.25))
        slip_text = f"Slip {state.traction.slip_pct:4.1f}%"
        slip_surface = _font(label_font).render(slip_text, True, TEXT_COLOR)
        surface.blit(
            slip_surface,
            (
                self.rect.x + padding,
                self.rect.y + padding // 2,
            ),
        )

        wheelie_font = max(14, int(self.rect.height * 0.25))
        wheelie_text = f"Pitch {state.traction.wheelie_pitch_deg:+4.1f}°"
        wheelie_surface = _font(wheelie_font).render(wheelie_text, True, TEXT_COLOR)
        surface.blit(
            wheelie_surface,
            (
                self.rect.x + padding,
                slip_rect.bottom + padding // 2,
            ),
        )

        level_font = max(14, int(self.rect.height * 0.25))
        level_surface = _font(level_font).render(state.traction.intervention_level, True, BAR_COLOR)
        surface.blit(
            level_surface,
            (
                self.rect.right - level_surface.get_width() - padding,
                self.rect.y + padding // 2,
            ),
        )
