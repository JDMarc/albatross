"""Scrolling message line widget."""
from __future__ import annotations

import pygame

from .base import Color, Widget
from ...state.snapshot import StateSnapshot

BG_COLOR: Color = (0, 0, 0)
TEXT_COLOR: Color = (255, 180, 100)
FAULT_COLOR: Color = (255, 80, 80)

_FONT_CACHE: dict[int, pygame.font.Font] = {}


def _font(size: int) -> pygame.font.Font:
    font = _FONT_CACHE.get(size)
    if font is None:
        font = pygame.font.SysFont("Courier", size)
        _FONT_CACHE[size] = font
    return font


class MessageLine(Widget):
    def __init__(self, rect: pygame.Rect) -> None:
        self.rect = rect

    def draw(self, surface: pygame.Surface, state: StateSnapshot) -> None:
        pygame.draw.rect(surface, BG_COLOR, self.rect)
        text = state.environment.message_line or " | ".join(state.faults) or "ECU OK | ARDUINO OK | CAN OK"
        color = FAULT_COLOR if state.faults else TEXT_COLOR
        font_size = max(14, int(self.rect.height * 0.6))
        text_surface = _font(font_size).render(text, True, color)
        surface.blit(
            text_surface,
            (
                self.rect.x + 8,
                self.rect.centery - text_surface.get_height() // 2,
            ),
        )
