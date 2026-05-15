"""Guardian Light (GL) sprite widget."""
from __future__ import annotations

import pygame

from .base import Color, Widget
from ...state.snapshot import StateSnapshot

BG_COLOR: Color = (0, 0, 0)
HAPPY_COLOR: Color = (255, 200, 120)
ALERT_COLOR: Color = (255, 80, 80)

FONT_CACHE: dict[int, pygame.font.Font] = {}


def _font(size: int) -> pygame.font.Font:
    font = FONT_CACHE.get(size)
    if font is None:
        font = pygame.font.SysFont("Courier", size, bold=True)
        FONT_CACHE[size] = font
    return font


class GLSprite(Widget):
    def __init__(self, rect: pygame.Rect) -> None:
        self.rect = rect

    def draw(self, surface: pygame.Surface, state: StateSnapshot) -> None:
        pygame.draw.rect(surface, BG_COLOR, self.rect)
        mood = state.gl_sprite_mood
        color = ALERT_COLOR if mood == "alert" else HAPPY_COLOR
        text = ":)" if mood == "happy" else ("!" if mood == "alert" else ":|")
        sprite_surface = _font(48).render(text, True, color)
        surface.blit(
            sprite_surface,
            (
                self.rect.centerx - sprite_surface.get_width() // 2,
                self.rect.centery - sprite_surface.get_height() // 2,
            ),
        )
