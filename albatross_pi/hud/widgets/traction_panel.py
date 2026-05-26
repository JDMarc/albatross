"""eTRAC and wheelie indicators."""
from __future__ import annotations

import pygame

from .base import Widget
from .ui_utils import AMBER_BG, AMBER_BRIGHT, AMBER_DARK, AMBER_GLOW, FAULT_AMBER, fit_font_size, font
from ...state.snapshot import StateSnapshot


class TractionPanel(Widget):
    def __init__(self, rect: pygame.Rect) -> None:
        self.rect = rect

    def draw(self, surface: pygame.Surface, state: StateSnapshot) -> None:
        previous_clip = surface.get_clip()
        surface.set_clip(self.rect)
        pygame.draw.rect(surface, AMBER_BG, self.rect)
        border = FAULT_AMBER if state.traction.sensor_fault else (AMBER_BRIGHT if state.traction.active else AMBER_DARK)
        pygame.draw.rect(surface, border, self.rect, width=1)

        padding = max(6, min(12, int(self.rect.height * 0.12)))
        inner = self.rect.inflate(-2 * padding, -2 * padding)
        if inner.height < 62:
            self._draw_compact(surface, inner, state)
            surface.set_clip(previous_clip)
            return

        title_h = max(14, min(22, int(inner.height * 0.25)))
        bar_h = max(10, min(20, int(inner.height * 0.24)))
        bottom_h = max(14, inner.height - title_h - bar_h - 6)

        title = "eTRAC"
        status = "FAULT" if state.traction.sensor_fault else ("CUT" if state.traction.active else (state.traction.intervention_level or "MED"))
        status_color = FAULT_AMBER if state.traction.sensor_fault or status == "OFF" else AMBER_BRIGHT
        title_surface = self._fit(title, inner.width // 2, title_h, 20, AMBER_GLOW)
        status_surface = self._fit(status, inner.width // 2, title_h, 20, status_color)
        surface.blit(title_surface, (inner.x, inner.y))
        surface.blit(status_surface, (inner.right - status_surface.get_width(), inner.y))

        slip_rect = pygame.Rect(inner.x, inner.y + title_h + 3, inner.width, bar_h)
        pygame.draw.rect(surface, AMBER_DARK, slip_rect, width=2)
        fill = slip_rect.inflate(-4, -4)
        fill.width = int(fill.width * min(1.0, max(0.0, state.traction.slip_pct) / 20.0))
        pygame.draw.rect(surface, FAULT_AMBER if state.traction.sensor_fault else AMBER_BRIGHT, fill)

        bottom_y = slip_rect.bottom + 3
        col_w = max(48, (inner.width - 10) // 3)
        metrics = (
            (pygame.Rect(inner.x, bottom_y, col_w, bottom_h), f"SLIP {state.traction.slip_pct:.1f}%", state.traction.sensor_fault),
            (pygame.Rect(inner.x + col_w + 5, bottom_y, col_w, bottom_h), f"CUT {state.traction.torque_cut_pct:.0f}%", state.traction.active),
            (pygame.Rect(inner.right - col_w, bottom_y, col_w, bottom_h), f"PITCH {state.traction.wheelie_pitch_deg:+.1f}deg", False),
        )
        for rect, text, hot in metrics:
            self._draw_metric(surface, rect, text, hot)
        surface.set_clip(previous_clip)

    @staticmethod
    def _fit(text: str, max_w: int, max_h: int, start_size: int, color: tuple[int, int, int] | list[int]) -> pygame.Surface:
        size = fit_font_size(text, max_w, max_h, start_size=start_size, bold=True)
        return font(size, bold=True).render(text, True, color)

    @staticmethod
    def _draw_metric(surface: pygame.Surface, rect: pygame.Rect, text: str, hot: bool) -> None:
        size = fit_font_size(text, rect.width, rect.height, start_size=max(8, min(15, rect.height)), bold=True)
        rendered = font(size, bold=True).render(text, True, FAULT_AMBER if hot else AMBER_GLOW)
        surface.blit(
            rendered,
            (
                rect.x + (rect.width - rendered.get_width()) // 2,
                rect.y + max(0, (rect.height - rendered.get_height()) // 2),
            ),
        )

    def _draw_compact(self, surface: pygame.Surface, rect: pygame.Rect, state: StateSnapshot) -> None:
        status = "FAULT" if state.traction.sensor_fault else ("CUT" if state.traction.active else (state.traction.intervention_level or "MED"))
        left = f"eTRAC {status}"
        right = f"{state.traction.slip_pct:.1f}% | {state.traction.torque_cut_pct:.0f}%"
        left_color = FAULT_AMBER if state.traction.sensor_fault or status == "OFF" else AMBER_GLOW
        right_color = FAULT_AMBER if state.traction.sensor_fault else AMBER_BRIGHT
        left_surface = self._fit(left, rect.width // 2, rect.height, 16, left_color)
        right_surface = self._fit(right, rect.width // 2, rect.height, 15, right_color)
        surface.blit(left_surface, (rect.x, rect.centery - left_surface.get_height() // 2))
        surface.blit(right_surface, (rect.right - right_surface.get_width(), rect.centery - right_surface.get_height() // 2))
