"""RPM bar widget."""
from __future__ import annotations

import pygame

from .base import Color, Widget
from ...state.snapshot import StateSnapshot

RPM_COLOR: Color = (255, 140, 0)
SHIFT_COLOR: Color = (255, 90, 0)
BAR_BG: Color = (40, 40, 40)
TEXT_COLOR: Color = (240, 200, 120)

_FONT_CACHE: dict[int, pygame.font.Font] = {}


def _font(size: int, *, bold: bool = False) -> pygame.font.Font:
    key = (size, bold)
    font = _FONT_CACHE.get(key)
    if font is None:
        font = pygame.font.SysFont("Courier", size, bold=bold)
        _FONT_CACHE[key] = font
    return font


class RpmBar(Widget):
    def __init__(self, rect: pygame.Rect) -> None:
        self.rect = rect

    def draw(self, surface: pygame.Surface, state: StateSnapshot) -> None:
        engine = state.engine
        pygame.draw.rect(surface, BAR_BG, self.rect)
        pct = min(1.0, engine.rpm / max(1, engine.rpm_redline))
        fill_width = int(self.rect.width * pct)
        fill_rect = pygame.Rect(self.rect.x, self.rect.y, fill_width, self.rect.height)
        color = SHIFT_COLOR if state.shift_light else RPM_COLOR
        pygame.draw.rect(surface, color, fill_rect)

        text_size = max(18, int(self.rect.height * 0.6))
        rpm_text = f"RPM {engine.rpm:5d}"
        rpm_surface = _font(text_size, bold=True).render(rpm_text, True, TEXT_COLOR)
        surface.blit(
            rpm_surface,
            (
                self.rect.x + 10,
                self.rect.centery - rpm_surface.get_height() // 2,
            ),
        )

        if state.shift_light:
            shift_size = max(18, int(self.rect.height * 0.7))
            shift_surface = _font(shift_size, bold=True).render("SHIFT!", True, (255, 255, 255))
            surface.blit(
                shift_surface,
                (
                    self.rect.right - shift_surface.get_width() - 10,
                    self.rect.centery - shift_surface.get_height() // 2,
                ),
            )
