"""Fuel level block gauge."""
from __future__ import annotations

import pygame

from .base import Widget
from .ui_utils import AMBER_BG, AMBER_BRIGHT, AMBER_DARK, AMBER_GLOW, FAULT_AMBER, fit_font_size, font
from ...state.snapshot import StateSnapshot


class FuelPanel(Widget):
    def __init__(self, rect: pygame.Rect) -> None:
        self.rect = rect

    def draw(self, surface: pygame.Surface, state: StateSnapshot) -> None:
        pygame.draw.rect(surface, AMBER_BG, self.rect)
        padding = max(8, int(self.rect.height * 0.12))
        level = max(0.0, min(100.0, state.environment.fuel_level_pct))
        blocks_on = int(level // 10)

        title = font(fit_font_size("FUEL", self.rect.width // 2, int(self.rect.height * 0.22), start_size=22, bold=True), bold=True).render("FUEL", True, AMBER_GLOW)
        surface.blit(title, (self.rect.x + padding, self.rect.y + 4))

        pct_text = f"{level:3.0f}%"
        pct = font(fit_font_size(pct_text, self.rect.width // 3, int(self.rect.height * 0.2), start_size=18, bold=True), bold=True).render(pct_text, True, FAULT_AMBER if level <= 20 else AMBER_GLOW)
        surface.blit(pct, (self.rect.right - pct.get_width() - padding, self.rect.y + 4))

        bar_y = self.rect.y + title.get_height() + 12
        available_w = self.rect.width - 2 * padding
        gap = 4
        block_w = max(8, (available_w - 9 * gap) // 10)
        block_h = max(14, self.rect.height - (bar_y - self.rect.y) - padding)
        for i in range(10):
            r = pygame.Rect(self.rect.x + padding + i * (block_w + gap), bar_y, block_w, block_h)
            pygame.draw.rect(surface, AMBER_DARK, r, 1)
            if i < blocks_on:
                c = FAULT_AMBER if level <= 20 else AMBER_BRIGHT
                pygame.draw.rect(surface, c, r.inflate(-3, -3))

        if level <= 15:
            low = font(14, bold=True).render("LOW FUEL", True, FAULT_AMBER)
            surface.blit(low, (self.rect.centerx - low.get_width() // 2, self.rect.bottom - low.get_height() - 2))
