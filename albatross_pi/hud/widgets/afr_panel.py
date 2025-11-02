"""AFR and spark panel."""
from __future__ import annotations

import pygame

from .base import Color, Widget
from ...state.snapshot import StateSnapshot

BG_COLOR: Color = (15, 15, 15)
TEXT_COLOR: Color = (255, 200, 160)
ALERT_COLOR: Color = (255, 80, 80)

FONT_CACHE: dict[int, pygame.font.Font] = {}


def _font(size: int) -> pygame.font.Font:
    font = FONT_CACHE.get(size)
    if font is None:
        font = pygame.font.SysFont("Courier", size)
        FONT_CACHE[size] = font
    return font


class AfrPanel(Widget):
    def __init__(self, rect: pygame.Rect) -> None:
        self.rect = rect

    def draw(self, surface: pygame.Surface, state: StateSnapshot) -> None:
        pygame.draw.rect(surface, BG_COLOR, self.rect)
        afr_l = state.engine.afr_left
        afr_r = state.engine.afr_right
        spark = state.engine.spark_advance_deg
        knock = state.engine.knock_events > 0
        afr_text = f"AFR L {afr_l:4.1f} | R {afr_r:4.1f}"
        spark_text = f"Spark {spark:4.1f}°"
        afr_surface = _font(20).render(afr_text, True, TEXT_COLOR)
        spark_surface = _font(20).render(spark_text, True, TEXT_COLOR)
        surface.blit(afr_surface, (self.rect.x + 8, self.rect.y + 6))
        surface.blit(spark_surface, (self.rect.x + 8, self.rect.y + 32))
        if knock:
            knock_surface = _font(18).render("KNOCK", True, ALERT_COLOR)
            surface.blit(knock_surface, (self.rect.right - knock_surface.get_width() - 8, self.rect.y + 8))
