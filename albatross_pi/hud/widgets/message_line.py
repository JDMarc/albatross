"""Scrolling message line widget."""
from __future__ import annotations

import pygame

from .base import Widget
from .ui_utils import AMBER_BG, AMBER_BRIGHT, FAULT_AMBER, fit_font_size, font
from ...state.snapshot import StateSnapshot



class MessageLine(Widget):
    def __init__(self, rect: pygame.Rect) -> None:
        self.rect = rect

    def draw(self, surface: pygame.Surface, state: StateSnapshot) -> None:
        pygame.draw.rect(surface, AMBER_BG, self.rect)
        text = state.environment.message_line or " | ".join(state.faults) or "ECU OK | ARDUINO OK | CAN OK"
        color = FAULT_AMBER if state.faults else AMBER_BRIGHT
        font_size = fit_font_size(text, self.rect.width - 16, self.rect.height - 4, start_size=max(14, int(self.rect.height * 0.6)))
        text_surface = font(font_size).render(text, True, color)
        surface.blit(
            text_surface,
            (
                self.rect.x + 8,
                self.rect.centery - text_surface.get_height() // 2,
            ),
        )
