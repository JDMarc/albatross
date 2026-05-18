"""Boost target strategy for Pi-originated ride-mode requests."""
from __future__ import annotations

from .state.snapshot import StateSnapshot, WMIState


MODE_TARGET_RATIO = {
    "ECO": 0.0,
    "NORMAL": 0.0,
    "SPORT": 0.55,
    "RACE": 0.82,
    "ALBATROSS": 1.0,
}

FUEL_CAP_WITH_WMI = {
    "87": 10.0,
    "91": 14.0,
    "93": 18.0,
    "100": 20.0,
    "E85": 22.0,
    "C16": 22.0,
}

FUEL_CAP_DRY = {
    "87": 6.0,
    "91": 8.0,
    "93": 10.0,
    "100": 12.0,
    "E85": 16.0,
    "C16": 16.0,
}


def _flex_blend_caps(snapshot: StateSnapshot) -> tuple[float, float] | None:
    ethanol_pct = snapshot.environment.ethanol_content_pct
    if ethanol_pct < 0:
        return None
    fuel = (snapshot.environment.fuel_type or "93").upper()
    if fuel in {"100", "C16"}:
        return None
    if fuel in {"87", "91", "93"}:
        return FUEL_CAP_DRY[fuel], FUEL_CAP_WITH_WMI[fuel]
    blend = max(0.0, min(1.0, (ethanol_pct - 10.0) / 75.0))
    dry = FUEL_CAP_DRY["93"] + ((FUEL_CAP_DRY["E85"] - FUEL_CAP_DRY["93"]) * blend)
    wmi = FUEL_CAP_WITH_WMI["93"] + ((FUEL_CAP_WITH_WMI["E85"] - FUEL_CAP_WITH_WMI["93"]) * blend)
    return dry, wmi


def wmi_effectiveness(wmi: WMIState) -> float:
    if wmi.fault_active or wmi.tank_level_pct <= 5.0:
        return 0.0
    if wmi.commanded_flow_cc_min <= 0:
        return 1.0
    return max(0.0, min(1.0, wmi.actual_flow_cc_min / wmi.commanded_flow_cc_min))


def _thermal_multiplier(snapshot: StateSnapshot) -> float:
    multiplier = 1.0
    if snapshot.temps.intake_temp_f >= 170.0:
        multiplier *= 0.70
    elif snapshot.temps.intake_temp_f >= 145.0:
        multiplier *= 0.85
    if snapshot.temps.coolant_temp_f >= 235.0:
        multiplier *= 0.65
    elif snapshot.temps.coolant_temp_f >= 225.0:
        multiplier *= 0.85
    if snapshot.temps.oil_temp_f >= 285.0:
        multiplier *= 0.65
    elif snapshot.temps.oil_temp_f >= 260.0:
        multiplier *= 0.85
    if snapshot.temps.exhaust_temp_f >= 1650.0:
        multiplier *= 0.60
    elif snapshot.temps.exhaust_temp_f >= 1550.0:
        multiplier *= 0.80
    return multiplier


def calculate_boost_target(snapshot: StateSnapshot, *, mode: str | None = None) -> float:
    requested_mode = (mode or snapshot.environment.mode or "ECO").upper()
    ratio = MODE_TARGET_RATIO.get(requested_mode, 0.0)
    if ratio <= 0.0:
        return 0.0

    fuel = (snapshot.environment.fuel_type or "93").upper()
    flex_caps = _flex_blend_caps(snapshot)
    if flex_caps is None:
        dry_cap = FUEL_CAP_DRY.get(fuel, FUEL_CAP_DRY["93"])
        wmi_cap = FUEL_CAP_WITH_WMI.get(fuel, FUEL_CAP_WITH_WMI["93"])
    else:
        dry_cap, wmi_cap = flex_caps
    fuel_cap = dry_cap + ((wmi_cap - dry_cap) * wmi_effectiveness(snapshot.wmi))
    boost = fuel_cap * ratio * _thermal_multiplier(snapshot)

    if snapshot.engine.knock_events > 0:
        boost *= 0.75
    return round(max(0.0, boost), 1)
