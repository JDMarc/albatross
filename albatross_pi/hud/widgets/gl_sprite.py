"""Guardian Light (GL) sprite widget."""
from __future__ import annotations

import pygame

from .base import Widget
from .ui_utils import AMBER_BG, AMBER_GLOW, FAULT_AMBER, font
from ...state.snapshot import StateSnapshot

class GLSprite(Widget):
    def __init__(self, rect: pygame.Rect) -> None:
        self.rect = rect

    def draw(self, surface: pygame.Surface, state: StateSnapshot) -> None:
        pygame.draw.rect(surface, AMBER_BG, self.rect)
        mood = state.gl_sprite_mood
        color = FAULT_AMBER if mood == "alert" else AMBER_GLOW
        text = ":)" if mood == "happy" else ("!" if mood == "alert" else ":|")
        sprite_surface = font(48, bold=True).render(text, True, color)
        surface.blit(
            sprite_surface,
            (
                self.rect.centerx - sprite_surface.get_width() // 2,
                self.rect.centery - sprite_surface.get_height() // 2,
            ),
        )
