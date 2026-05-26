"""Mode-specific operating stats panel."""
from __future__ import annotations

import math

import pygame

from ...economy import fallback_mpg_estimate
from .base import Widget
from .ui_utils import AMBER_BG, AMBER_BRIGHT, AMBER_DARK, AMBER_GLOW, FAULT_AMBER, fit_font_size, font
from ...state.snapshot import StateSnapshot

KNOWN_MODES = {"ECO", "NORMAL", "SPORT", "RACE", "ALBATROSS"}


def _fmt(value: float | None, suffix: str = "", precision: int = 0) -> str:
    if value is None or not math.isfinite(value):
        return "--"
    if precision <= 0:
        return f"{value:.0f}{suffix}"
    return f"{value:.{precision}f}{suffix}"


class ModeStatsPanel(Widget):
    def __init__(self, rect: pygame.Rect) -> None:
        self.rect = rect

    def draw(self, surface: pygame.Surface, state: StateSnapshot) -> None:
        previous_clip = surface.get_clip()
        surface.set_clip(self.rect)
        pygame.draw.rect(surface, AMBER_BG, self.rect)
        padding = max(6, int(min(self.rect.width, self.rect.height) * 0.07))
        mode = state.environment.mode if state.environment.mode in KNOWN_MODES else "NORMAL"
        rows = self._rows_for_mode(mode, state)
        title = mode
        title_font = fit_font_size(title, self.rect.width - 2 * padding, max(12, int(self.rect.height * 0.18)), start_size=max(12, int(self.rect.height * 0.16)), bold=True)
        title_surface = font(title_font, bold=True).render(title, True, AMBER_BRIGHT)
        surface.blit(title_surface, (self.rect.x + padding, self.rect.y + max(3, padding // 2)))

        y = self.rect.y + max(4, padding // 2) + title_surface.get_height() + 2
        available_h = max(18, self.rect.bottom - y - max(4, padding // 2))
        grid_gap = max(4, min(8, padding))
        cell_w = max(32, (self.rect.width - 2 * padding - grid_gap) // 2)
        cell_h = max(12, (available_h - grid_gap) // 2)
        for idx, (label, value, fault) in enumerate(rows):
            col = idx % 2
            row = idx // 2
            row_rect = pygame.Rect(
                self.rect.x + padding + col * (cell_w + grid_gap),
                y + row * (cell_h + grid_gap),
                cell_w,
                cell_h,
            )
            color = FAULT_AMBER if fault else AMBER_GLOW
            label_color = AMBER_GLOW if not fault else FAULT_AMBER
            value_color = AMBER_BRIGHT if not fault else color
            self._draw_cell(surface, row_rect, label, value, label_color, value_color, fault)
        surface.set_clip(previous_clip)

    @staticmethod
    def _draw_cell(
        surface: pygame.Surface,
        rect: pygame.Rect,
        label: str,
        value: str,
        label_color: tuple[int, int, int] | list[int],
        value_color: tuple[int, int, int] | list[int],
        fault: bool,
    ) -> None:
        if fault:
            accent = pygame.Rect(rect.x, rect.y + 3, 2, max(1, rect.height - 6))
            pygame.draw.rect(surface, FAULT_AMBER, accent)
            pygame.draw.line(surface, FAULT_AMBER, (rect.x, rect.bottom - 1), (rect.right, rect.bottom - 1), 1)
        else:
            pygame.draw.line(surface, AMBER_DARK, (rect.x, rect.bottom - 1), (rect.right, rect.bottom - 1), 1)
        inner = rect.inflate(-8 if fault else -4, -4)
        if fault:
            inner.x += 4
            inner.width = max(1, inner.width - 4)
        label_h = max(8, min(13, int(inner.height * 0.42)))
        value_h = max(8, inner.height - label_h)
        label_size = fit_font_size(label, inner.width, label_h, start_size=max(8, min(12, label_h)), bold=True, min_size=8)
        value_size = fit_font_size(value, inner.width, value_h, start_size=max(8, min(16, value_h + 2)), bold=True, min_size=8)
        label_surface = font(label_size, bold=True).render(label, True, label_color)
        value_surface = font(value_size, bold=True).render(value, True, value_color)
        surface.blit(label_surface, (inner.x, inner.y))
        surface.blit(value_surface, (inner.right - value_surface.get_width(), inner.y + label_h - 1))

    def _rows_for_mode(self, mode: str, state: StateSnapshot) -> list[tuple[str, str, bool]]:
        instant_mpg = state.economy.instant_mpg if state.economy.instant_mpg > 0 else fallback_mpg_estimate(state)
        average_mpg = state.economy.average_mpg if state.economy.average_mpg > 0 else instant_mpg
        mte = state.economy.miles_to_empty if state.economy.miles_to_empty > 0 else None
        economy_label = "AVG MPG" if state.economy.source == "INJECTOR" else "EST MPG"
        fuel_low = 0 <= state.environment.fuel_level_pct <= 15
        wmi_flow = f"{state.wmi.actual_flow_cc_min:.0f}/{state.wmi.commanded_flow_cc_min:.0f}"
        boost_error = abs(state.engine.boost_psi - state.engine.target_boost_psi) > 3.0 and state.engine.target_boost_psi > 4.0
        if mode == "ECO":
            return [
                (economy_label, _fmt(average_mpg, precision=1), average_mpg is not None and average_mpg < 24),
                ("RANGE", _fmt(mte, "mi"), fuel_low),
                ("FUEL", _fmt(state.environment.fuel_level_pct, "%") if state.environment.fuel_level_pct >= 0 else "--", fuel_low),
                ("BOOST", "LOCKED", state.engine.target_boost_psi > 0.5),
            ]
        if mode == "NORMAL":
            return [
                (economy_label, _fmt(average_mpg, precision=1), average_mpg is not None and average_mpg < 20),
                ("RANGE", _fmt(mte, "mi"), fuel_low),
                ("FUEL FLOW", _fmt(state.economy.fuel_flow_cc_min, "ccm") if state.economy.source == "INJECTOR" else "--", False),
                ("BOOST", "LOCKED", state.engine.target_boost_psi > 0.5),
            ]
        if mode == "SPORT":
            return [
                ("REQ BOOST", f"{state.engine.target_boost_psi:.1f} psi", boost_error),
                ("WG DUTY", f"{state.engine.wastegate_duty_pct:.0f}%", state.engine.wastegate_duty_pct > 85),
                ("TC SLIP", f"{state.traction.slip_pct:.1f}%", state.traction.sensor_fault),
                ("KNOCK", f"{state.engine.knock_events:.0f}", state.engine.knock_events > 0),
            ]
        if mode == "RACE":
            return [
                ("BOOST", f"{state.engine.boost_psi:.1f}/{state.engine.target_boost_psi:.1f}psi", boost_error),
                ("EGT", f"{state.temps.exhaust_temp_f:.0f}F", state.temps.exhaust_temp_f > 1600),
                ("WMI FLOW", wmi_flow, state.wmi.fault_active or state.wmi.actual_flow_cc_min < state.wmi.commanded_flow_cc_min * 0.6),
                ("TC CUT", f"{state.traction.torque_cut_pct:.0f}%", state.traction.sensor_fault),
            ]
        return [
            ("AIR SHOT", f"{state.air_shot.pressure_psi:.0f} psi", state.air_shot.pressure_psi < 35 and state.engine.target_boost_psi > 6),
            ("WMI FLOW", wmi_flow, state.wmi.fault_active),
            ("IAT/EGT", f"{state.temps.intake_temp_f:.0f}/{state.temps.exhaust_temp_f:.0f}F", state.temps.intake_temp_f > 155 or state.temps.exhaust_temp_f > 1600),
            ("BOOST", f"{state.engine.boost_psi:.1f}/{state.engine.target_boost_psi:.1f}psi", boost_error),
        ]
