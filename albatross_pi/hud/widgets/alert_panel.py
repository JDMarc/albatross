"""Priority alert panel widget."""
from __future__ import annotations

import pygame

from .base import Color, Widget
from ...state.snapshot import StateSnapshot

BG_COLOR: Color = (15, 15, 15)
FRAME_COLOR: Color = (255, 120, 80)
TEXT_COLOR: Color = (255, 200, 150)
ALERT_COLOR: Color = (255, 90, 90)
ACCENT_COLOR: Color = (120, 200, 255)

_FONT_CACHE: dict[tuple[int, bool], pygame.font.Font] = {}


def _font(size: int, *, bold: bool = False) -> pygame.font.Font:
    key = (size, bold)
    font = _FONT_CACHE.get(key)
    if font is None:
        font = pygame.font.SysFont("Courier", size, bold=bold)
        _FONT_CACHE[key] = font
    return font


class AlertPanel(Widget):
    def __init__(self, rect: pygame.Rect) -> None:
        self.rect = rect

    def draw(self, surface: pygame.Surface, state: StateSnapshot) -> None:
        pygame.draw.rect(surface, BG_COLOR, self.rect)
        pygame.draw.rect(surface, FRAME_COLOR, self.rect, 2)

        lines = list(state.faults)
        highlight = bool(lines)
        if not lines:
            fallback = state.environment.message_line or "GL500 DASH ONLINE"
            lines = [fallback]

        # Reserve space for the GL500 heritage label at the top
        header_height = int(self.rect.height * 0.2)
        header_size = max(14, int(header_height * 0.6))
        header_surface = _font(header_size, bold=True).render("GL500 ALERT", True, ACCENT_COLOR)
        surface.blit(
            header_surface,
            (
                self.rect.centerx - header_surface.get_width() // 2,
                self.rect.y + max(4, (header_height - header_surface.get_height()) // 2),
            ),
        )

        available_height = self.rect.height - header_height - 10
        if lines:
            line_height = available_height // max(1, len(lines))
        else:
            line_height = available_height
        base_size = max(18, int(line_height * 0.7))
        color = ALERT_COLOR if highlight else TEXT_COLOR

        for index, line in enumerate(lines):
            text_surface = _font(base_size, bold=highlight).render(line, True, color)
            x = self.rect.centerx - text_surface.get_width() // 2
            y = self.rect.y + header_height + 5 + index * line_height + max(
                0, (line_height - text_surface.get_height()) // 2
            )
            surface.blit(text_surface, (x, y))
