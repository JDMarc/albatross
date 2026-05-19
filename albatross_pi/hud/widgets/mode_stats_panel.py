"""Mode-specific operating stats panel."""
from __future__ import annotations

import math

import pygame

from .base import Widget
from .ui_utils import AMBER_BG, AMBER_BRIGHT, AMBER_GLOW, FAULT_AMBER, fit_font_size, font
from ...state.snapshot import StateSnapshot

TANK_CAPACITY_GAL = 5.3
BASE_MODE_MPG = {
    "ECO": 48.0,
    "NORMAL": 42.0,
    "SPORT": 32.0,
    "RACE": 24.0,
    "ALBATROSS": 18.0,
}
FUEL_MPG_FACTOR = {
    "87": 1.00,
    "91": 1.00,
    "93": 1.00,
    "100": 0.98,
    "E85": 0.72,
    "C16": 0.92,
}


def _calculated_mpg(state: StateSnapshot) -> float | None:
    speed = state.engine.speed_mph
    if speed < 3.0:
        return None
    mode = state.environment.mode if state.environment.mode in BASE_MODE_MPG else "NORMAL"
    base = BASE_MODE_MPG[mode] * FUEL_MPG_FACTOR.get(state.environment.fuel_type.upper(), 1.0)
    throttle = max(0.0, min(100.0, state.engine.throttle_pct))
    load = max(0.0, min(100.0, state.engine.engine_load_pct))
    boost = max(0.0, state.engine.boost_psi)
    rpm = max(0, state.engine.rpm)
    speed_eff = max(0.45, 1.0 - abs(speed - 48.0) / 125.0)
    load_penalty = 1.0 + throttle * 0.010 + load * 0.007 + boost * 0.075 + max(0.0, rpm - 4200) / 12000.0
    mpg = base * speed_eff / load_penalty
    return max(6.0, min(70.0, mpg))


def _miles_to_empty(state: StateSnapshot, mpg: float | None) -> float | None:
    if mpg is None or state.environment.fuel_level_pct < 0:
        return None
    fuel_gal = TANK_CAPACITY_GAL * max(0.0, min(100.0, state.environment.fuel_level_pct)) / 100.0
    return mpg * fuel_gal


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
        mode = state.environment.mode if state.environment.mode in BASE_MODE_MPG else "NORMAL"
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
        mpg = _calculated_mpg(state)
        mte = _miles_to_empty(state, mpg)
        fuel_low = 0 <= state.environment.fuel_level_pct <= 15
        wmi_flow = f"{state.wmi.actual_flow_cc_min:.0f}/{state.wmi.commanded_flow_cc_min:.0f}"
        boost_error = abs(state.engine.boost_psi - state.engine.target_boost_psi) > 3.0 and state.engine.target_boost_psi > 4.0
        if mode == "ECO":
            return [
                ("CALC MPG", _fmt(mpg, precision=1), mpg is not None and mpg < 24),
                ("MILES LEFT", _fmt(mte, " mi"), fuel_low),
                ("FUEL LEFT", _fmt(state.environment.fuel_level_pct, "%") if state.environment.fuel_level_pct >= 0 else "--", fuel_low),
            ]
        if mode == "NORMAL":
            return [
                ("CALC MPG", _fmt(mpg, precision=1), mpg is not None and mpg < 20),
                ("MILES LEFT", _fmt(mte, " mi"), fuel_low),
                ("REQ BOOST", f"{state.engine.target_boost_psi:.1f} psi", state.engine.target_boost_psi > 0.5),
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
