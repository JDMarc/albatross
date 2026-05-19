"""Fuel economy and range estimation."""
from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import replace

from .state.snapshot import EconomyState, StateSnapshot

CC_PER_US_GALLON = 3785.411784
STOCK_GL500_TANK_GAL = 4.62
INJECTOR_FLOW_CC_MIN = 1100.0
INJECTOR_COUNT = 2
ROLLING_AVG_SECONDS = 120.0

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


def fallback_mpg_estimate(snapshot: StateSnapshot) -> float | None:
    speed = snapshot.engine.speed_mph
    if speed < 3.0:
        return None
    mode = snapshot.environment.mode if snapshot.environment.mode in BASE_MODE_MPG else "NORMAL"
    base = BASE_MODE_MPG[mode] * FUEL_MPG_FACTOR.get(snapshot.environment.fuel_type.upper(), 1.0)
    throttle = max(0.0, min(100.0, snapshot.engine.throttle_pct))
    load = max(0.0, min(100.0, snapshot.engine.engine_load_pct))
    boost = max(0.0, snapshot.engine.boost_psi)
    rpm = max(0, snapshot.engine.rpm)
    speed_eff = max(0.45, 1.0 - abs(speed - 48.0) / 125.0)
    load_penalty = 1.0 + throttle * 0.010 + load * 0.007 + boost * 0.075 + max(0.0, rpm - 4200) / 12000.0
    mpg = base * speed_eff / load_penalty
    return max(6.0, min(70.0, mpg))


def fuel_flow_from_injectors(snapshot: StateSnapshot) -> tuple[float, float]:
    pulse_width_ms = max(0.0, snapshot.economy.injector_pulse_width_ms)
    if pulse_width_ms <= 0.0 or snapshot.engine.rpm <= 0:
        return 0.0, max(0.0, snapshot.economy.injector_duty_pct)
    reported_duty = max(0.0, min(95.0, snapshot.economy.injector_duty_pct))
    if reported_duty > 0.0:
        duty_fraction = reported_duty / 100.0
    else:
        # Four-stroke one injection event per injector per 720 crank degrees.
        duty_fraction = pulse_width_ms * max(0, snapshot.engine.rpm) / 120000.0
    duty_fraction = max(0.0, min(0.95, duty_fraction))
    flow_cc_min = INJECTOR_FLOW_CC_MIN * INJECTOR_COUNT * duty_fraction
    return flow_cc_min, duty_fraction * 100.0


class EconomyTracker:
    """Integrate distance and fuel burn for MPG/range display."""

    def __init__(self, tank_capacity_gal: float = STOCK_GL500_TANK_GAL) -> None:
        self.tank_capacity_gal = tank_capacity_gal
        self._last_ts: float | None = None
        self._distance_miles = 0.0
        self._fuel_used_gal = 0.0
        self._samples: deque[tuple[float, float, float]] = deque()

    def update(self, snapshot: StateSnapshot, now_s: float | None = None) -> StateSnapshot:
        now = time.monotonic() if now_s is None else now_s
        dt = 0.0 if self._last_ts is None else max(0.0, min(1.0, now - self._last_ts))
        self._last_ts = now

        flow_cc_min, duty_pct = fuel_flow_from_injectors(snapshot)
        source = "INJECTOR" if flow_cc_min > 0.0 else "EST"
        instant_mpg = -1.0
        fuel_delta_gal = 0.0
        distance_delta_miles = max(0.0, snapshot.engine.speed_mph) * dt / 3600.0

        if source == "INJECTOR":
            gal_per_hour = flow_cc_min * 60.0 / CC_PER_US_GALLON
            fuel_delta_gal = flow_cc_min * dt / 60.0 / CC_PER_US_GALLON
            if snapshot.engine.speed_mph >= 2.0 and gal_per_hour > 0.001:
                instant_mpg = snapshot.engine.speed_mph / gal_per_hour
        else:
            fallback = fallback_mpg_estimate(snapshot)
            if fallback is not None:
                instant_mpg = fallback
                fuel_delta_gal = distance_delta_miles / fallback if fallback > 0 else 0.0

        if dt > 0.0:
            self._distance_miles += distance_delta_miles
            self._fuel_used_gal += fuel_delta_gal
            self._samples.append((now, distance_delta_miles, fuel_delta_gal))
            while self._samples and now - self._samples[0][0] > ROLLING_AVG_SECONDS:
                self._samples.popleft()

        rolling_distance = sum(sample[1] for sample in self._samples)
        rolling_fuel = sum(sample[2] for sample in self._samples)
        average_mpg = rolling_distance / rolling_fuel if rolling_fuel > 0.00001 else instant_mpg
        if not math.isfinite(average_mpg) or average_mpg <= 0:
            average_mpg = -1.0

        miles_to_empty = -1.0
        if snapshot.environment.fuel_level_pct >= 0 and average_mpg > 0:
            remaining_gal = self.tank_capacity_gal * max(0.0, min(100.0, snapshot.environment.fuel_level_pct)) / 100.0
            miles_to_empty = remaining_gal * average_mpg

        economy = replace(
            snapshot.economy,
            injector_duty_pct=duty_pct,
            fuel_flow_cc_min=flow_cc_min,
            instant_mpg=instant_mpg if math.isfinite(instant_mpg) else -1.0,
            average_mpg=average_mpg,
            miles_to_empty=miles_to_empty,
            distance_miles=self._distance_miles,
            fuel_used_gal=self._fuel_used_gal,
            source=source,
        )
        return replace(snapshot, economy=economy)
