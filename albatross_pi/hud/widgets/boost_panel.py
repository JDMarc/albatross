"""Boost gauge widget."""
from __future__ import annotations

import pygame

from .base import Widget
from .ui_utils import AMBER_BG, AMBER_BRIGHT, AMBER_DARK, AMBER_GLOW, FAULT_AMBER, fit_font_size, font
from ...state.snapshot import StateSnapshot


class BoostPanel(Widget):
    def __init__(self, rect: pygame.Rect, boost_max: float = 30.0) -> None:
        self.rect = rect
        self.boost_max = boost_max

    def draw(self, surface: pygame.Surface, state: StateSnapshot) -> None:
        pygame.draw.rect(surface, AMBER_BG, self.rect)
        engine = state.engine
        pct = min(1.0, max(0.0, engine.boost_psi / max(1e-6, self.boost_max)))
        bar_padding = max(8, int(self.rect.height * 0.15))
        bar_height = max(8, int(self.rect.height * 0.35))
        bar_rect = pygame.Rect(
            self.rect.x + bar_padding,
            self.rect.y + self.rect.height - bar_padding - bar_height,
            self.rect.width - 2 * bar_padding,
            bar_height,
        )
        pygame.draw.rect(surface, AMBER_DARK, bar_rect)
        fill = bar_rect.copy()
        fill.width = int(bar_rect.width * pct)
        pygame.draw.rect(surface, AMBER_BRIGHT, fill)

        target_pct = min(1.0, max(0.0, engine.target_boost_psi / max(1e-6, self.boost_max)))
        target_x = bar_rect.x + int(bar_rect.width * target_pct)
        pygame.draw.line(surface, AMBER_GLOW, (target_x, bar_rect.y), (target_x, bar_rect.bottom), 2)

        text = f"Boost {engine.boost_psi:4.1f} psi"
        top_font = fit_font_size(text, self.rect.width - 2 * bar_padding, int(self.rect.height * 0.28), start_size=max(16, int(self.rect.height * 0.3)), bold=True)
        text_surface = font(top_font, bold=True).render(text, True, AMBER_BRIGHT)
        surface.blit(text_surface, (self.rect.x + bar_padding, self.rect.y + bar_padding // 2))

        target_text = f"REQ {engine.target_boost_psi:4.1f}"
        target_font = fit_font_size(target_text, int(self.rect.width * 0.36), int(self.rect.height * 0.2), start_size=max(13, int(self.rect.height * 0.2)), bold=True)
        target_surface = font(target_font, bold=True).render(target_text, True, AMBER_BRIGHT)
        surface.blit(target_surface, (self.rect.x + bar_padding, self.rect.y + bar_padding // 2 + text_surface.get_height() + 2))

        duty_text = f"WG {engine.wastegate_duty_pct:3.0f}%"
        duty_font = fit_font_size(duty_text, int(self.rect.width * 0.36), int(self.rect.height * 0.2), start_size=max(14, int(self.rect.height * 0.22)))
        duty_surface = font(duty_font).render(duty_text, True, AMBER_GLOW)
        surface.blit(duty_surface, (self.rect.right - bar_padding - duty_surface.get_width(), self.rect.y + bar_padding // 2 + text_surface.get_height() + 2))

        if engine.boost_psi > self.boost_max * 0.95:
            warn_font = fit_font_size("OVERBOOST", self.rect.width // 2, int(self.rect.height * 0.2), start_size=max(14, int(self.rect.height * 0.2)), bold=True)
            warning_surface = font(warn_font, bold=True).render("OVERBOOST", True, FAULT_AMBER)
            surface.blit(
                warning_surface,
                (self.rect.right - warning_surface.get_width() - bar_padding, self.rect.y + bar_padding // 2),
            )
