"""Water-methanol injection status widget."""
from __future__ import annotations

import pygame

from .base import Widget
from .ui_utils import AMBER_BG, AMBER_BRIGHT, AMBER_DARK, AMBER_GLOW, FAULT_AMBER, fit_font_size, font
from ...state.snapshot import StateSnapshot

BAR_BG = AMBER_DARK
BAR_COLOR = AMBER_BRIGHT


class WMIPanel(Widget):
    def __init__(self, rect: pygame.Rect) -> None:
        self.rect = rect

    def draw(self, surface: pygame.Surface, state: StateSnapshot) -> None:
        pygame.draw.rect(surface, AMBER_BG, self.rect)
        padding = max(8, int(self.rect.height * 0.18))
        bar_height = max(8, int(self.rect.height * 0.2))
        bar_rect = pygame.Rect(
            self.rect.x + padding,
            self.rect.bottom - padding - bar_height,
            self.rect.width - 2 * padding,
            bar_height,
        )
        pygame.draw.rect(surface, BAR_BG, bar_rect)
        fill = bar_rect.copy()
        fill.width = int(bar_rect.width * min(1.0, state.wmi.tank_level_pct / 100.0))
        pygame.draw.rect(surface, BAR_COLOR, fill)

        level_text = f"Tank {state.wmi.tank_level_pct:4.0f}%"
        level_font = fit_font_size(level_text, self.rect.width - (2 * padding), max(12, int(self.rect.height * 0.3)), start_size=max(14, int(self.rect.height * 0.28)))
        level_surface = font(level_font).render(level_text, True, AMBER_GLOW)
        surface.blit(
            level_surface,
            (
                self.rect.x + padding,
                self.rect.y + padding // 2,
            ),
        )

        flow_text = f"Flow {state.wmi.actual_flow_cc_min:4.0f}/{state.wmi.commanded_flow_cc_min:4.0f}"
        flow_font = fit_font_size(flow_text, self.rect.width - (2 * padding), max(12, int(self.rect.height * 0.3)), start_size=max(14, int(self.rect.height * 0.26)))
        flow_surface = font(flow_font).render(flow_text, True, AMBER_BRIGHT)
        surface.blit(
            flow_surface,
            (
                self.rect.x + padding,
                bar_rect.y - flow_surface.get_height() - 4,
            ),
        )

        if state.wmi.fault_active:
            fault_font = fit_font_size("FAULT", self.rect.width // 3, max(12, int(self.rect.height * 0.3)), start_size=max(14, int(self.rect.height * 0.28)), bold=True)
            fault_surface = font(fault_font, bold=True).render("FAULT", True, FAULT_AMBER)
            surface.blit(
                fault_surface,
                (
                    self.rect.right - fault_surface.get_width() - padding,
                    self.rect.y + padding // 2,
                ),
            )
