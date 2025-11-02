"""Temperature and pressure grid widget."""
from __future__ import annotations

import pygame

from .base import Color, Widget
from ...state.snapshot import StateSnapshot

TEXT_COLOR: Color = (200, 200, 200)
LABEL_COLOR: Color = (255, 160, 80)
BG_COLOR: Color = (20, 20, 20)
GRID_COLOR: Color = (80, 80, 80)

_FONT_CACHE: dict[int, pygame.font.Font] = {}


def _font(size: int) -> pygame.font.Font:
    font = _FONT_CACHE.get(size)
    if font is None:
        font = pygame.font.SysFont("Courier", size)
        _FONT_CACHE[size] = font
    return font


class TempsGrid(Widget):
    def __init__(self, rect: pygame.Rect) -> None:
        self.rect = rect
        self.rows = [
            ("Coolant", lambda s: f"{s.temps.coolant_temp_f:5.1f}F"),
            ("Oil", lambda s: f"{s.temps.oil_temp_f:5.1f}F"),
            ("Oil P", lambda s: f"{s.temps.oil_pressure_psi:5.1f}psi"),
            ("Battery", lambda s: f"{s.temps.battery_voltage:4.2f}V"),
            ("IAT", lambda s: f"{s.temps.intake_temp_f:5.1f}F"),
            ("EGT", lambda s: f"{s.temps.exhaust_temp_f:5.0f}F"),
        ]

    def draw(self, surface: pygame.Surface, state: StateSnapshot) -> None:
        pygame.draw.rect(surface, BG_COLOR, self.rect)
        row_height = self.rect.height // len(self.rows)
        font_size = max(14, int(row_height * 0.5))
        for i, (label, value_fn) in enumerate(self.rows):
            y = self.rect.y + i * row_height
            if i > 0:
                pygame.draw.line(surface, GRID_COLOR, (self.rect.x, y), (self.rect.right, y), 1)
            label_surface = _font(font_size).render(label, True, LABEL_COLOR)
            value_surface = _font(font_size).render(value_fn(state), True, TEXT_COLOR)
            surface.blit(label_surface, (self.rect.x + 8, y + max(2, (row_height - label_surface.get_height()) // 2)))
            surface.blit(
                value_surface,
                (
                    self.rect.right - value_surface.get_width() - 8,
                    y + max(2, (row_height - value_surface.get_height()) // 2),
                ),
            )
