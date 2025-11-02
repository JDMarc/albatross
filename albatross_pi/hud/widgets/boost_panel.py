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

FONT_CACHE: dict[int, pygame.font.Font] = {}


def _font(size: int) -> pygame.font.Font:
    font = FONT_CACHE.get(size)
    if font is None:
        font = pygame.font.SysFont("Courier", size)
        FONT_CACHE[size] = font
    return font


class BoostPanel(Widget):
    def __init__(self, rect: pygame.Rect, boost_max: float = 30.0) -> None:
        self.rect = rect
        self.boost_max = boost_max

    def draw(self, surface: pygame.Surface, state: StateSnapshot) -> None:
        pygame.draw.rect(surface, BG_COLOR, self.rect)
        engine = state.engine
        pct = min(1.0, max(0.0, engine.boost_psi / self.boost_max))
        fill_width = int(self.rect.width * pct)
        bar_rect = pygame.Rect(self.rect.x, self.rect.y, fill_width, self.rect.height)
        pygame.draw.rect(surface, BAR_COLOR, bar_rect)

        target_pct = min(1.0, max(0.0, engine.target_boost_psi / self.boost_max))
        target_x = self.rect.x + int(self.rect.width * target_pct)
        pygame.draw.line(surface, TARGET_COLOR, (target_x, self.rect.y), (target_x, self.rect.bottom), 2)

        text = f"Boost {engine.boost_psi:4.1f} psi"
        text_surface = _font(20).render(text, True, TEXT_COLOR)
        surface.blit(text_surface, (self.rect.x + 8, self.rect.y + 4))

        duty_text = f"WG {engine.wastegate_duty_pct:3.0f}%"
        duty_surface = _font(18).render(duty_text, True, TEXT_COLOR)
        surface.blit(duty_surface, (self.rect.x + 8, self.rect.bottom - duty_surface.get_height() - 4))

        if engine.boost_psi > self.boost_max * 0.95:
            warning_surface = _font(18).render("OVERBOOST", True, WARNING_COLOR)
            surface.blit(warning_surface, (self.rect.right - warning_surface.get_width() - 8, self.rect.y + 4))
