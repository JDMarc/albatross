"""Priority alert panel widget."""
from __future__ import annotations

import pygame
import time

from .base import Widget
from .ui_utils import AMBER_BG, AMBER_BRIGHT, AMBER_DARK, AMBER_GLOW, FAULT_AMBER, fit_font_size, font
from ...state.snapshot import StateSnapshot


class AlertPanel(Widget):
    def __init__(self, rect: pygame.Rect) -> None:
        self.rect = rect
        self._latched_faults: list[str] = []
        self._latch_until = 0.0

    def draw(self, surface: pygame.Surface, state: StateSnapshot) -> None:
        pygame.draw.rect(surface, AMBER_BG, self.rect)
        pygame.draw.rect(surface, AMBER_DARK, self.rect, 2)

        now = time.monotonic()
        if state.faults:
            self._latched_faults = list(state.faults)
            self._latch_until = now + 3.5

        active_faults = list(state.faults)
        latched_faults = self._latched_faults if now < self._latch_until else []
        lines = active_faults if active_faults else latched_faults
        highlight = bool(lines)
        is_active_fault_display = bool(active_faults)
        if not lines:
            fallback = state.environment.message_line or "NO ACTIVE ALERT"
            lines = [fallback]

        # Reserve space for the GL500 heritage label at the top
        header_height = int(self.rect.height * 0.2)
        header_size = fit_font_size("GL500 ALERT", self.rect.width - 10, header_height - 4, start_size=max(12, int(header_height * 0.6)), bold=True)
        header_surface = font(header_size, bold=True).render("GL500 ALERT", True, AMBER_BRIGHT)
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
        # Flash only while faults are actively present; latched post-clear faults remain steady.
        flash_on = (int(now * 4) % 2) == 0
        color = FAULT_AMBER if highlight else AMBER_GLOW

        for index, line in enumerate(lines):
            size = fit_font_size(line, self.rect.width - 10, line_height - 2, start_size=max(12, int(line_height * 0.65)), bold=highlight)
            if is_active_fault_display and not flash_on:
                text_surface = font(size, bold=highlight).render(line, True, AMBER_BG)
            else:
                text_surface = font(size, bold=highlight).render(line, True, color)
            x = self.rect.centerx - text_surface.get_width() // 2
            y = self.rect.y + header_height + 5 + index * line_height + max(
                0, (line_height - text_surface.get_height()) // 2
            )
            surface.blit(text_surface, (x, y))
