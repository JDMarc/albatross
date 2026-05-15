"""Base widget types for the Albatross HUD."""
from __future__ import annotations

from typing import Protocol, Tuple

import pygame

from ...state.snapshot import StateSnapshot

Color = Tuple[int, int, int]


class Widget(Protocol):
    def draw(self, surface: pygame.Surface, state: StateSnapshot) -> None:
        ...
