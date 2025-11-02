"""Water-methanol injection status widget."""
from __future__ import annotations

import pygame

from .base import Color, Widget
from ...state.snapshot import StateSnapshot

BG_COLOR: Color = (10, 12, 18)
TEXT_COLOR: Color = (180, 220, 255)
FAULT_COLOR: Color = (255, 80, 80)
BAR_BG: Color = (30, 40, 60)
BAR_COLOR: Color = (120, 180, 255)

_FONT_CACHE: dict[int, pygame.font.Font] = {}


def _font(size: int, *, bold: bool = False) -> pygame.font.Font:
    key = (size, bold)
    font = _FONT_CACHE.get(key)
    if font is None:
        font = pygame.font.SysFont("Courier", size, bold=bold)
        _FONT_CACHE[key] = font
    return font


class WMIPanel(Widget):
    def __init__(self, rect: pygame.Rect) -> None:
        self.rect = rect

    def draw(self, surface: pygame.Surface, state: StateSnapshot) -> None:
        pygame.draw.rect(surface, BG_COLOR, self.rect)
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

        level_font = max(14, int(self.rect.height * 0.28))
        level_surface = _font(level_font).render(f"Tank {state.wmi.tank_level_pct:4.0f}%", True, TEXT_COLOR)
        surface.blit(
            level_surface,
            (
                self.rect.x + padding,
                self.rect.y + padding // 2,
            ),
        )

        flow_font = max(14, int(self.rect.height * 0.26))
        flow_text = f"Flow {state.wmi.actual_flow_cc_min:4.0f}/{state.wmi.commanded_flow_cc_min:4.0f}"
        flow_surface = _font(flow_font).render(flow_text, True, TEXT_COLOR)
        surface.blit(
            flow_surface,
            (
                self.rect.x + padding,
                bar_rect.y - flow_surface.get_height() - 4,
            ),
        )

        if state.wmi.fault_active:
            fault_font = max(14, int(self.rect.height * 0.28))
            fault_surface = _font(fault_font, bold=True).render("FAULT", True, FAULT_COLOR)
            surface.blit(
                fault_surface,
                (
                    self.rect.right - fault_surface.get_width() - padding,
                    self.rect.y + padding // 2,
                ),
            )
