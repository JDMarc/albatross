"""Thermal normalization and conservative derived diagnostics."""
from __future__ import annotations

import math
from typing import Mapping

from .config import SensorDefinition
from .model import ThermalReading, SensorStatus


def interpolate_curve(value: float, points: tuple[tuple[float, float], ...]) -> float:
    if value <= points[0][0]:
        return points[0][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if value <= x1:
            ratio = (value - x0) / (x1 - x0)
            return y0 + ratio * (y1 - y0)
    x0, y0 = points[-2]
    x1, y1 = points[-1]
    return y1 + (value - x1) / max(1e-9, x1 - x0) * (y1 - y0)


def valid_temp(readings: Mapping[str, ThermalReading], key: str) -> float | None:
    reading = readings.get(key)
    return reading.temperature_c if reading is not None and reading.valid else None


def difference(readings: Mapping[str, ThermalReading], hot: str, cold: str) -> float | None:
    a, b = valid_temp(readings, hot), valid_temp(readings, cold)
    return None if a is None or b is None else a - b


def intercooler_effectiveness(inlet: float | None, outlet: float | None, ambient: float | None) -> float | None:
    if inlet is None or outlet is None or ambient is None:
        return None
    denominator = inlet - ambient
    if denominator <= 2.0:
        return None
    return max(-50.0, min(150.0, (inlet - outlet) / denominator * 100.0))


def compressor_efficiency(t_in_c: float | None, t_out_c: float | None, pressure_ratio: float | None, gamma: float = 1.4) -> float | None:
    """Return a diagnostic ideal/actual compressor temperature efficiency."""
    if t_in_c is None or t_out_c is None or pressure_ratio is None or pressure_ratio <= 1.01:
        return None
    inlet_k = t_in_c + 273.15
    actual_rise = t_out_c - t_in_c
    if inlet_k <= 0.0 or actual_rise <= 1.0:
        return None
    ideal_out_k = inlet_k * math.pow(pressure_ratio, (gamma - 1.0) / gamma)
    return max(0.0, min(120.0, (ideal_out_k - inlet_k) / actual_rise * 100.0))


def derived_metrics(readings: Mapping[str, ThermalReading], pressure_ratio_left: float | None = None, pressure_ratio_right: float | None = None) -> dict[str, float | None]:
    ambient = valid_temp(readings, "AMBIENT_AIR")
    pairs = {
        "EGT_LR_DELTA": ("EGT_LEFT", "EGT_RIGHT"),
        "TURBINE_OUT_LR_DELTA": ("TURBINE_OUT_LEFT", "TURBINE_OUT_RIGHT"),
        "COMP_IN_LR_DELTA": ("COMP_IN_LEFT", "COMP_IN_RIGHT"),
        "COMP_OUT_LR_DELTA": ("COMP_OUT_LEFT", "COMP_OUT_RIGHT"),
        "IC_IN_LR_DELTA": ("IC_IN_LEFT", "IC_IN_RIGHT"),
        "IC_OUT_LR_DELTA": ("IC_OUT_LEFT", "IC_OUT_RIGHT"),
        "RUNNER_IAT_LR_DELTA": ("RUNNER_IAT_LEFT", "RUNNER_IAT_RIGHT"),
        "HEAD_COOLANT_LR_DELTA": ("HEAD_COOLANT_LEFT", "HEAD_COOLANT_RIGHT"),
        "HEAD_METAL_LR_DELTA": ("HEAD_METAL_LEFT", "HEAD_METAL_RIGHT"),
        "TURBO_DRAIN_LR_DELTA": ("TURBO_OIL_DRAIN_LEFT", "TURBO_OIL_DRAIN_RIGHT"),
        "COMP_RISE_LEFT": ("COMP_OUT_LEFT", "COMP_IN_LEFT"),
        "COMP_RISE_RIGHT": ("COMP_OUT_RIGHT", "COMP_IN_RIGHT"),
        "IC_DROP_LEFT": ("IC_IN_LEFT", "IC_OUT_LEFT"),
        "IC_DROP_RIGHT": ("IC_IN_RIGHT", "IC_OUT_RIGHT"),
        "WMI_DROP": ("PRE_WMI", "POST_WMI"),
        "TURBINE_DROP_LEFT": ("EGT_LEFT", "TURBINE_OUT_LEFT"),
        "TURBINE_DROP_RIGHT": ("EGT_RIGHT", "TURBINE_OUT_RIGHT"),
        "RAD_DELTA_T": ("RAD_IN", "RAD_OUT"),
        "OIL_COOLER_DELTA_T": ("OIL_COOLER_IN", "OIL_COOLER_OUT"),
        "HEAD_COOLANT_TO_METAL_LEFT": ("HEAD_METAL_LEFT", "HEAD_COOLANT_LEFT"),
        "HEAD_COOLANT_TO_METAL_RIGHT": ("HEAD_METAL_RIGHT", "HEAD_COOLANT_RIGHT"),
    }
    result = {name: difference(readings, left, right) for name, (left, right) in pairs.items()}
    for side in ("LEFT", "RIGHT"):
        inlet = valid_temp(readings, f"IC_IN_{side}")
        outlet = valid_temp(readings, f"IC_OUT_{side}")
        result[f"IC_EFFECTIVENESS_{side}"] = intercooler_effectiveness(inlet, outlet, ambient)
        result[f"COMP_EFFICIENCY_{side}"] = compressor_efficiency(
            valid_temp(readings, f"COMP_IN_{side}"),
            valid_temp(readings, f"COMP_OUT_{side}"),
            pressure_ratio_left if side == "LEFT" else pressure_ratio_right,
        )
    return result


def severity(reading: ThermalReading, definition: SensorDefinition) -> float:
    if reading.status != SensorStatus.VALID:
        return 0.0
    absolute = reading.thermal_abs
    deviation = reading.thermal_dev
    rate = min(120.0, abs(reading.derivative_c_s) * (25.0 if "HEAD" in reading.key else 10.0))
    return max(absolute, deviation, rate)
