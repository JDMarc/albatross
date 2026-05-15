"""AFR and spark panel."""
from __future__ import annotations

import pygame

from .base import Color, Widget
from ...state.snapshot import StateSnapshot

BG_COLOR: Color = (15, 15, 15)
TEXT_COLOR: Color = (255, 200, 160)
ALERT_COLOR: Color = (255, 80, 80)

_FONT_CACHE: dict[int, pygame.font.Font] = {}


def _font(size: int, *, bold: bool = False) -> pygame.font.Font:
    key = (size, bold)
    font = _FONT_CACHE.get(key)
    if font is None:
        font = pygame.font.SysFont("Courier", size, bold=bold)
        _FONT_CACHE[key] = font
    return font


class AfrPanel(Widget):
    def __init__(self, rect: pygame.Rect) -> None:
        self.rect = rect

    def draw(self, surface: pygame.Surface, state: StateSnapshot) -> None:
        pygame.draw.rect(surface, BG_COLOR, self.rect)
        padding = max(8, int(self.rect.height * 0.18))
        line_height = (self.rect.height - 2 * padding) // 2
        afr_font = max(16, int(line_height * 0.7))
        afr_l = state.engine.afr_left
        afr_r = state.engine.afr_right
        spark = state.engine.spark_advance_deg
        knock = state.engine.knock_events > 0

        afr_text = f"AFR L {afr_l:4.1f} | R {afr_r:4.1f}"
        afr_surface = _font(afr_font).render(afr_text, True, TEXT_COLOR)
        surface.blit(
            afr_surface,
            (
                self.rect.x + padding,
                self.rect.y + padding,
            ),
        )

        spark_surface = _font(afr_font).render(f"Spark {spark:4.1f}°", True, TEXT_COLOR)
        surface.blit(
            spark_surface,
            (
                self.rect.x + padding,
                self.rect.y + padding + line_height,
            ),
        )

        if knock:
            knock_font = max(14, int(self.rect.height * 0.3))
            knock_surface = _font(knock_font, bold=True).render("KNOCK", True, ALERT_COLOR)
            surface.blit(
                knock_surface,
                (
                    self.rect.right - knock_surface.get_width() - padding,
                    self.rect.y + padding,
                ),
            )
