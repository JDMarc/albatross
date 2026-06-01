"""Temperature and pressure grid widget."""
from __future__ import annotations

import pygame

from .base import Widget
from .ui_utils import AMBER_BG, AMBER_BRIGHT, AMBER_DARK, AMBER_GLOW, fit_font_size, font
from ...state.snapshot import StateSnapshot


class TempsGrid(Widget):
    def __init__(self, rect: pygame.Rect, *, split: bool = False) -> None:
        self.rect = rect
        self.split = split
        self.rows = [
            ("Coolant", lambda s: f"{s.temps.coolant_temp_f:5.1f}F"),
            ("Oil", lambda s: f"{s.temps.oil_temp_f:5.1f}F"),
            ("Oil P", lambda s: f"{s.temps.oil_pressure_psi:5.1f}psi"),
            ("Battery", lambda s: f"{s.temps.battery_voltage:4.2f}V"),
            ("IAT", lambda s: f"{s.temps.intake_temp_f:5.1f}F"),
            ("EGT", lambda s: f"{s.temps.exhaust_temp_f:5.0f}F"),
            ("WMI Tank", lambda s: f"{s.wmi.tank_level_pct:4.0f}%"),
            ("WMI Flow", lambda s: f"{s.wmi.actual_flow_cc_min:4.0f}/{s.wmi.commanded_flow_cc_min:4.0f}"),
            ("WMI Stat", lambda s: "FAULT" if s.wmi.fault_active else "OK"),
        ]

    def draw(self, surface: pygame.Surface, state: StateSnapshot) -> None:
        pygame.draw.rect(surface, AMBER_BG, self.rect)
        pygame.draw.rect(surface, AMBER_DARK, self.rect, 1)
        if self.split:
            self._draw_split(surface, state)
            return
        row_height = self.rect.height // len(self.rows)
        for i, (label, value_fn) in enumerate(self.rows):
            y = self.rect.y + i * row_height
            if i > 0:
                pygame.draw.line(surface, AMBER_DARK, (self.rect.x, y), (self.rect.right, y), 1)
            value = value_fn(state)
            label_size = fit_font_size(label, int(self.rect.width * 0.38), row_height - 4, start_size=max(13, int(row_height * 0.6)))
            value_size = fit_font_size(value, int(self.rect.width * 0.55), row_height - 4, start_size=max(13, int(row_height * 0.62)), bold=True)
            label_surface = font(label_size).render(label, True, AMBER_GLOW)
            value_surface = font(value_size, bold=True).render(value, True, AMBER_BRIGHT)
            surface.blit(label_surface, (self.rect.x + 8, y + max(2, (row_height - label_surface.get_height()) // 2)))
            surface.blit(
                value_surface,
                (
                    self.rect.right - value_surface.get_width() - 8,
                    y + max(2, (row_height - value_surface.get_height()) // 2),
                ),
            )

    def _draw_split(self, surface: pygame.Surface, state: StateSnapshot) -> None:
        title_h = min(19, max(15, self.rect.height // 7))
        body_y = self.rect.y + title_h
        body_h = self.rect.height - title_h
        column_w = self.rect.width // 2
        row_h = max(1, body_h // 5)
        surface.blit(font(12, bold=True).render("SYSTEM VITALS", True, AMBER_BRIGHT), (self.rect.x + 8, self.rect.y + 2))
        pygame.draw.line(surface, AMBER_DARK, (self.rect.x, body_y), (self.rect.right, body_y), 1)
        pygame.draw.line(surface, AMBER_DARK, (self.rect.x + column_w, body_y), (self.rect.x + column_w, self.rect.bottom), 1)
        for index, (label, value_fn) in enumerate(self.rows):
            column = index // 5
            row = index % 5
            x = self.rect.x + column * column_w
            y = body_y + row * row_h
            if row > 0:
                pygame.draw.line(surface, AMBER_DARK, (x, y), (x + column_w, y), 1)
            value = value_fn(state)
            label_size = fit_font_size(label, int(column_w * 0.48), row_h - 4, start_size=max(11, int(row_h * 0.56)))
            value_size = fit_font_size(value, int(column_w * 0.48), row_h - 4, start_size=max(11, int(row_h * 0.58)), bold=True)
            label_surface = font(label_size).render(label, True, AMBER_GLOW)
            value_surface = font(value_size, bold=True).render(value, True, AMBER_BRIGHT)
            text_y = y + max(1, (row_h - max(label_surface.get_height(), value_surface.get_height())) // 2)
            surface.blit(label_surface, (x + 7, text_y))
            surface.blit(value_surface, (x + column_w - value_surface.get_width() - 7, text_y))
