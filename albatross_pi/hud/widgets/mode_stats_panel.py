"""Mode-specific operating stats panel."""
from __future__ import annotations

import math

import pygame

from ...economy import fallback_mpg_estimate
from .base import Widget
from .ui_utils import AMBER_BG, AMBER_BRIGHT, AMBER_GLOW, FAULT_AMBER, fit_font_size, font
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
        pygame.draw.rect(surface, AMBER_BG, self.rect)
        padding = max(7, int(min(self.rect.width, self.rect.height) * 0.09))
        mode = state.environment.mode if state.environment.mode in KNOWN_MODES else "NORMAL"
        rows = self._rows_for_mode(mode, state)
        title = f"{mode} DATA"
        title_font = fit_font_size(title, self.rect.width - 2 * padding, max(12, int(self.rect.height * 0.2)), start_size=max(12, int(self.rect.height * 0.18)), bold=True)
        title_surface = font(title_font, bold=True).render(title, True, AMBER_BRIGHT)
        surface.blit(title_surface, (self.rect.x + padding, self.rect.y + max(3, padding // 2)))

        y = self.rect.y + padding + title_surface.get_height()
        available_h = max(18, self.rect.bottom - y - padding)
        row_h = max(13, available_h // max(1, len(rows)))
        value_max_w = max(48, int(self.rect.width * 0.36))
        label_max_w = max(64, self.rect.width - 2 * padding - value_max_w - 8)
        for idx, (label, value, fault) in enumerate(rows):
            row_y = y + idx * row_h
            label_font = fit_font_size(label, label_max_w, row_h, start_size=max(10, int(row_h * 0.68)), bold=True)
            value_font = fit_font_size(value, value_max_w, row_h, start_size=max(11, int(row_h * 0.76)), bold=True)
            color = FAULT_AMBER if fault else AMBER_GLOW
            label_color = AMBER_GLOW if not fault else FAULT_AMBER
            value_color = AMBER_BRIGHT if not fault else color
            label_surface = font(label_font, bold=True).render(label, True, label_color)
            value_surface = font(value_font, bold=True).render(value, True, value_color)
            surface.blit(label_surface, (self.rect.x + padding, row_y))
            surface.blit(value_surface, (self.rect.right - padding - value_surface.get_width(), row_y))

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
                ("MILES LEFT", _fmt(mte, " mi"), fuel_low),
                ("FUEL LEFT", _fmt(state.environment.fuel_level_pct, "%") if state.environment.fuel_level_pct >= 0 else "--", fuel_low),
            ]
        if mode == "NORMAL":
            return [
                (economy_label, _fmt(average_mpg, precision=1), average_mpg is not None and average_mpg < 20),
                ("MILES LEFT", _fmt(mte, " mi"), fuel_low),
                ("FUEL FLOW", _fmt(state.economy.fuel_flow_cc_min, "ccm") if state.economy.source == "INJECTOR" else "--", False),
            ]
        if mode == "SPORT":
            return [
                ("REQ BOOST", f"{state.engine.target_boost_psi:.1f} psi", boost_error),
                ("WG DUTY", f"{state.engine.wastegate_duty_pct:.0f}%", state.engine.wastegate_duty_pct > 85),
                ("TC SLIP", f"{state.traction.slip_pct:.1f}%", state.traction.sensor_fault),
            ]
        if mode == "RACE":
            return [
                ("BOOST", f"{state.engine.boost_psi:.1f}/{state.engine.target_boost_psi:.1f}", boost_error),
                ("EGT", f"{state.temps.exhaust_temp_f:.0f}F", state.temps.exhaust_temp_f > 1600),
                ("WMI FLOW", wmi_flow, state.wmi.fault_active or state.wmi.actual_flow_cc_min < state.wmi.commanded_flow_cc_min * 0.6),
            ]
        return [
            ("AIR SHOT", f"{state.air_shot.pressure_psi:.0f} psi", state.air_shot.pressure_psi < 35 and state.engine.target_boost_psi > 6),
            ("WMI FLOW", wmi_flow, state.wmi.fault_active),
            ("IAT/EGT", f"{state.temps.intake_temp_f:.0f}/{state.temps.exhaust_temp_f:.0f}F", state.temps.intake_temp_f > 155 or state.temps.exhaust_temp_f > 1600),
        ]
