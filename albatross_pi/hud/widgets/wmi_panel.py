"""Water-methanol injection widget."""
from __future__ import annotations

import pygame

from .base import Color, Widget
from ...state.snapshot import StateSnapshot

BG_COLOR: Color = (10, 12, 18)
TEXT_COLOR: Color = (180, 220, 255)
FAULT_COLOR: Color = (255, 80, 80)
BAR_BG: Color = (30, 40, 60)
BAR_COLOR: Color = (120, 180, 255)

FONT_CACHE: dict[int, pygame.font.Font] = {}


def _font(size: int) -> pygame.font.Font:
    font = FONT_CACHE.get(size)
    if font is None:
        font = pygame.font.SysFont("Courier", size)
        FONT_CACHE[size] = font
    return font


class WMIPanel(Widget):
    def __init__(self, rect: pygame.Rect) -> None:
        self.rect = rect

    def draw(self, surface: pygame.Surface, state: StateSnapshot) -> None:
        pygame.draw.rect(surface, BG_COLOR, self.rect)
        tank = state.wmi.tank_level_pct
        bar_rect = pygame.Rect(self.rect.x + 8, self.rect.y + 24, self.rect.width - 16, 12)
        pygame.draw.rect(surface, BAR_BG, bar_rect)
        fill = bar_rect.copy()
        fill.width = int(bar_rect.width * min(1.0, tank / 100.0))
        pygame.draw.rect(surface, BAR_COLOR, fill)

        level_surface = _font(18).render(f"Tank {tank:4.0f}%", True, TEXT_COLOR)
        surface.blit(level_surface, (self.rect.x + 8, self.rect.y + 4))

        flow_text = f"Flow {state.wmi.actual_flow_cc_min:4.0f}/{state.wmi.commanded_flow_cc_min:4.0f}"
        flow_surface = _font(18).render(flow_text, True, TEXT_COLOR)
        surface.blit(flow_surface, (self.rect.x + 8, self.rect.y + 44))

        if state.wmi.fault_active:
            fault_surface = _font(18).render("FAULT", True, FAULT_COLOR)
            surface.blit(fault_surface, (self.rect.right - fault_surface.get_width() - 8, self.rect.y + 4))
