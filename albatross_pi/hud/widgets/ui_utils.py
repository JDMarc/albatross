"""Shared HUD theme and text fitting utilities."""
from __future__ import annotations

import pygame

THEME_FONT_PREFERRED = (
    "VT323",
    "Press Start 2P",
    "Orbitron",
    "OCR A Extended",
    "Eurostile",
    "DejaVu Sans Mono",
)
THEME_FONT_QUERY = ",".join(THEME_FONT_PREFERRED)
THEME_FONT_PREFERRED = ("VT323", "Press Start 2P", "Orbitron", "OCR A Extended", "Eurostile", "DejaVu Sans Mono")

Color = tuple[int, int, int]

# 80s amber monochrome-ish palette.
BLACK: Color = (0, 0, 0)
AMBER_BG: Color = (10, 6, 0)
AMBER_DARK: Color = (46, 24, 0)
AMBER_MID: Color = (138, 67, 0)
AMBER_BRIGHT: Color = (255, 141, 20)
AMBER_GLOW: Color = (255, 180, 90)
FAULT_AMBER: Color = (255, 98, 0)

_FONT_CACHE: dict[tuple[int, bool], pygame.font.Font] = {}


def font(size: int, *, bold: bool = False) -> pygame.font.Font:
    key = (max(8, size), bold)
    cached = _FONT_CACHE.get(key)
    if cached is None:
        try:
            cached = pygame.font.SysFont(THEME_FONT_QUERY, max(8, size), bold=bold)
        except Exception:
            font_path = pygame.font.match_font(THEME_FONT_QUERY)
        except TypeError:
            font_path = None

        if font_path is not None:
        font_path = pygame.font.match_font(THEME_FONT_PREFERRED)
        if font_path:
            cached = pygame.font.Font(font_path, max(8, size))
            cached.set_bold(bold)
        else:
            cached = pygame.font.SysFont("Courier New", max(8, size), bold=bold)
        _FONT_CACHE[key] = cached
    return cached


def fit_font_size(text: str, max_w: int, max_h: int, *, start_size: int, bold: bool = False, min_size: int = 8) -> int:
    size = max(min_size, start_size)
    while size > min_size:
        rendered = font(size, bold=bold).render(text, True, (255, 255, 255))
        if rendered.get_width() <= max_w and rendered.get_height() <= max_h:
            return size
        size -= 1
    return min_size
