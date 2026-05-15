"""Boost gauge widget."""
from __future__ import annotations

import pygame

from .base import Color, Widget
from ...state.snapshot import StateSnapshot

BG_COLOR: Color = (10, 10, 10)
BAR_COLOR: Color = (255, 120, 60)
TARGET_COLOR: Color = (0, 200, 255)
TEXT_COLOR: Color = (220, 220, 220)
WARNING_COLOR: Color = (255, 0, 0)

_FONT_CACHE: dict[int, pygame.font.Font] = {}


def _font(size: int) -> pygame.font.Font:
    font = _FONT_CACHE.get(size)
    if font is None:
        font = pygame.font.SysFont("Courier", size)
        _FONT_CACHE[size] = font
    return font


class BoostPanel(Widget):
    def __init__(self, rect: pygame.Rect, boost_max: float = 30.0) -> None:
        self.rect = rect
        self.boost_max = boost_max

    def draw(self, surface: pygame.Surface, state: StateSnapshot) -> None:
        pygame.draw.rect(surface, BG_COLOR, self.rect)
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
        pygame.draw.rect(surface, (30, 30, 30), bar_rect)
        fill = bar_rect.copy()
        fill.width = int(bar_rect.width * pct)
        pygame.draw.rect(surface, BAR_COLOR, fill)

        target_pct = min(1.0, max(0.0, engine.target_boost_psi / max(1e-6, self.boost_max)))
        target_x = bar_rect.x + int(bar_rect.width * target_pct)
        pygame.draw.line(surface, TARGET_COLOR, (target_x, bar_rect.y), (target_x, bar_rect.bottom), 2)

        top_font = max(16, int(self.rect.height * 0.3))
        text = f"Boost {engine.boost_psi:4.1f} psi"
        text_surface = _font(top_font).render(text, True, TEXT_COLOR)
        surface.blit(text_surface, (self.rect.x + bar_padding, self.rect.y + bar_padding // 2))

        duty_font = max(14, int(self.rect.height * 0.24))
        duty_text = f"WG {engine.wastegate_duty_pct:3.0f}%"
        duty_surface = _font(duty_font).render(duty_text, True, TEXT_COLOR)
        surface.blit(duty_surface, (self.rect.x + bar_padding, bar_rect.y - duty_surface.get_height() - 4))

        if engine.boost_psi > self.boost_max * 0.95:
            warn_font = max(14, int(self.rect.height * 0.24))
            warning_surface = _font(warn_font).render("OVERBOOST", True, WARNING_COLOR)
            surface.blit(
                warning_surface,
                (self.rect.right - warning_surface.get_width() - bar_padding, self.rect.y + bar_padding // 2),
            )
