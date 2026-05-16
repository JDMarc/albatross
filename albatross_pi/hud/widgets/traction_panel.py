"""eTRAC and wheelie indicators."""
from __future__ import annotations

import pygame

from .base import Widget
from .ui_utils import AMBER_BG, AMBER_BRIGHT, AMBER_DARK, AMBER_GLOW, FAULT_AMBER, fit_font_size, font
from ...state.snapshot import StateSnapshot


class TractionPanel(Widget):
    def __init__(self, rect: pygame.Rect) -> None:
        self.rect = rect

    def draw(self, surface: pygame.Surface, state: StateSnapshot) -> None:
        pygame.draw.rect(surface, AMBER_BG, self.rect)
        padding = max(8, int(self.rect.height * 0.15))
        slip_bar_height = max(8, int(self.rect.height * 0.2))
        slip_rect = pygame.Rect(
            self.rect.x + padding,
            self.rect.y + padding + slip_bar_height,
            self.rect.width - 2 * padding,
            slip_bar_height,
        )
        pygame.draw.rect(surface, AMBER_DARK, slip_rect)
        fill = slip_rect.copy()
        fill.width = int(slip_rect.width * min(1.0, state.traction.slip_pct / 20.0))
        pygame.draw.rect(surface, AMBER_BRIGHT, fill)

        slip_text = f"Slip {state.traction.slip_pct:4.1f}%"
        label_font = fit_font_size(slip_text, self.rect.width - 2 * padding, int(self.rect.height * 0.26), start_size=max(14, int(self.rect.height * 0.25)))
        slip_surface = font(label_font).render(slip_text, True, AMBER_GLOW)
        surface.blit(
            slip_surface,
            (
                self.rect.x + padding,
                self.rect.y + padding // 2,
            ),
        )

        wheelie_text = f"Pitch {state.traction.wheelie_pitch_deg:+4.1f}°"
        wheelie_font = fit_font_size(wheelie_text, self.rect.width - 2 * padding, int(self.rect.height * 0.24), start_size=max(14, int(self.rect.height * 0.24)))
        wheelie_surface = font(wheelie_font).render(wheelie_text, True, AMBER_GLOW)
        surface.blit(
            wheelie_surface,
            (
                self.rect.x + padding,
                slip_rect.bottom + padding // 2,
            ),
        )

        level = state.traction.intervention_level or "MED"
        level_font = fit_font_size(level, self.rect.width // 3, int(self.rect.height * 0.26), start_size=max(14, int(self.rect.height * 0.25)), bold=True)
        level_color = FAULT_AMBER if level == "OFF" else AMBER_BRIGHT
        level_surface = font(level_font, bold=True).render(level, True, level_color)
        surface.blit(
            level_surface,
            (
                self.rect.right - level_surface.get_width() - padding,
                self.rect.y + padding // 2,
            ),
        )
