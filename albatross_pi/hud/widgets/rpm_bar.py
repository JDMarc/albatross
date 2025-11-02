"""RPM bar widget."""
from __future__ import annotations

import pygame

from .base import Color, Widget
from ...state.snapshot import StateSnapshot

RPM_COLOR: Color = (255, 140, 0)
SHIFT_COLOR: Color = (255, 90, 0)
BAR_BG: Color = (40, 40, 40)
TEXT_COLOR: Color = (240, 200, 120)

FONT_CACHE: dict[int, pygame.font.Font] = {}


def _font(size: int) -> pygame.font.Font:
    font = FONT_CACHE.get(size)
    if font is None:
        font = pygame.font.SysFont("Courier", size, bold=True)
        FONT_CACHE[size] = font
    return font


class RpmBar(Widget):
    def __init__(self, rect: pygame.Rect) -> None:
        self.rect = rect

    def draw(self, surface: pygame.Surface, state: StateSnapshot) -> None:
        engine = state.engine
        pygame.draw.rect(surface, BAR_BG, self.rect)
        pct = min(1.0, engine.rpm / engine.rpm_redline)
        fill_width = int(self.rect.width * pct)
        fill_rect = pygame.Rect(self.rect.x, self.rect.y, fill_width, self.rect.height)
        color = SHIFT_COLOR if state.shift_light else RPM_COLOR
        pygame.draw.rect(surface, color, fill_rect)
        rpm_text = f"RPM {engine.rpm:5d}"
        rpm_surface = _font(24).render(rpm_text, True, TEXT_COLOR)
        surface.blit(rpm_surface, (self.rect.x + 10, self.rect.y + self.rect.height // 2 - 12))
        if state.shift_light:
            shift_surface = _font(28).render("SHIFT!", True, (255, 255, 255))
            surface.blit(shift_surface, (self.rect.right - shift_surface.get_width() - 10, self.rect.y + 4))
