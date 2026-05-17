"""AFR and spark panel."""
from __future__ import annotations

import pygame

from .base import Widget
from .ui_utils import AMBER_BG, AMBER_GLOW, FAULT_AMBER, font
from ...state.snapshot import StateSnapshot

class AfrPanel(Widget):
    def __init__(self, rect: pygame.Rect) -> None:
        self.rect = rect

    def draw(self, surface: pygame.Surface, state: StateSnapshot) -> None:
        pygame.draw.rect(surface, AMBER_BG, self.rect)
        padding = max(8, int(self.rect.height * 0.18))
        line_height = (self.rect.height - 2 * padding) // 2
        afr_font = max(16, int(line_height * 0.7))
        afr_l = state.engine.afr_left
        afr_r = state.engine.afr_right
        spark = state.engine.spark_advance_deg
        knock = state.engine.knock_events > 0

        afr_text = f"AFR L {afr_l:4.1f} | R {afr_r:4.1f}"
        afr_surface = font(afr_font).render(afr_text, True, AMBER_GLOW)
        surface.blit(
            afr_surface,
            (
                self.rect.x + padding,
                self.rect.y + padding,
            ),
        )

        spark_surface = font(afr_font).render(f"Spark {spark:4.1f}°", True, AMBER_GLOW)
        surface.blit(
            spark_surface,
            (
                self.rect.x + padding,
                self.rect.y + padding + line_height,
            ),
        )

        if knock:
            knock_font = max(14, int(self.rect.height * 0.3))
            knock_surface = font(knock_font, bold=True).render("KNOCK", True, FAULT_AMBER)
            surface.blit(
                knock_surface,
                (
                    self.rect.right - knock_surface.get_width() - padding,
                    self.rect.y + padding,
                ),
            )
