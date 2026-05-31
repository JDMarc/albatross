"""Synthetic state generator for development and HUD demos."""
from __future__ import annotations

import math
import random
import threading
import time
from dataclasses import replace
from datetime import datetime
from typing import Callable, Iterator

from albatross_pi.boost_strategy import calculate_boost_target
from .snapshot import (
    AirShotState,
    ClutchState,
    EngineState,
    EnvironmentState,
    LightingState,
    StateSnapshot,
    TemperaturesState,
    TractionState,
    WMIState,
)

TICK_PERIOD = 1 / 60.0
MODE_NAMES = ("ECO", "NORMAL", "SPORT", "RACE", "ALBATROSS")
FUEL_TYPES = ("87", "91", "93", "100", "E85", "C16")


class StateSimulator:
    """Generate a continuous stream of synthetic `StateSnapshot` objects."""

    def __init__(self, tick_period: float = TICK_PERIOD) -> None:
        self._tick_period = tick_period
        self._running = False
        self._lock = threading.Lock()
        self._subscribers: list[Callable[[StateSnapshot], None]] = []
        self._thread: threading.Thread | None = None
        self._phase = 0.0
        self._mode = "ECO"
        self._fuel_type = "93"

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, name="state-sim", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None

    def subscribe(self, callback: Callable[[StateSnapshot], None]) -> None:
        with self._lock:
            self._subscribers.append(callback)

    def set_mode(self, mode_code: int) -> None:
        if 1 <= mode_code <= len(MODE_NAMES):
            with self._lock:
                self._mode = MODE_NAMES[mode_code - 1]

    def set_fuel_type(self, fuel_code: int) -> None:
        if 0 <= fuel_code < len(FUEL_TYPES):
            with self._lock:
                self._fuel_type = FUEL_TYPES[fuel_code]

    def _broadcast(self, snapshot: StateSnapshot) -> None:
        with self._lock:
            callbacks = list(self._subscribers)
        for callback in callbacks:
            callback(snapshot)

    def _run_loop(self) -> None:
        rng = random.Random(1337)
        snapshot = StateSnapshot()
        while self._running:
            self._phase = (self._phase + self._tick_period * 0.25) % 1.0
            snapshot = self._next_snapshot(snapshot, rng)
            self._broadcast(snapshot)
            time.sleep(self._tick_period)

    def _next_snapshot(self, snapshot: StateSnapshot, rng: random.Random) -> StateSnapshot:
        now = datetime.now()
        engine = snapshot.engine
        rpm = int(1000 + 5000 * (1 + math.sin(self._phase * math.tau)) / 2)
        speed = max(0.0, rpm / 100.0)
        throttle = max(0.0, min(100.0, 40 + math.sin(self._phase * math.tau) * 40))
        if speed < 2.0 and throttle < 3.0:
            gear = "N"
        else:
            gear_index = max(1, min(6, int(speed // 12) + 1))
            gear = str(gear_index)
        boost = max(0.0, 18.0 * math.sin(self._phase * math.tau))
        target_boost = snapshot.engine.target_boost_psi
        afr_left = 12.5 + math.sin(self._phase * math.tau * 2) * 0.2
        afr_right = 12.6 + math.cos(self._phase * math.tau * 2) * 0.2
        spark = 14.0 + math.sin(self._phase * math.tau * 0.5) * 5
        pulse_width_ms = max(1.2, 2.6 + throttle * 0.045 + max(0.0, boost) * 0.22)
        knock = 1 if rng.random() > 0.97 else 0

        engine = replace(
            engine,
            rpm=rpm,
            speed_mph=speed,
            gear=gear,
            boost_psi=boost,
            target_boost_psi=target_boost,
            wastegate_duty_pct=abs(math.sin(self._phase * math.tau)) * 80,
            afr_left=afr_left,
            afr_right=afr_right,
            spark_advance_deg=spark,
            knock_events=knock,
            throttle_pct=throttle,
            engine_load_pct=min(100.0, throttle * 0.9 + 10),
        )

        temps = replace(
            snapshot.temps,
            coolant_temp_f=190 + 5 * math.sin(self._phase * math.tau * 0.7),
            oil_temp_f=205 + 3 * math.sin(self._phase * math.tau * 0.5),
            oil_pressure_psi=60 + 10 * math.sin(self._phase * math.tau * 1.5),
            battery_voltage=13.8 + math.sin(self._phase * math.tau * 0.25) * 0.05,
            intake_temp_f=90 + 15 * abs(math.sin(self._phase * math.tau)),
            exhaust_temp_f=1250 + 50 * math.sin(self._phase * math.tau),
            alternator_temp_f=140 + 10 * math.sin(self._phase * math.tau * 0.6),
        )

        air_shot = replace(
            snapshot.air_shot,
            pressure_psi=1800 + 200 * math.sin(self._phase * math.tau * 0.4),
            charges_remaining=3,
            is_firing=rng.random() > 0.995,
        )

        wmi_fault = rng.random() > 0.99
        wmi = replace(
            snapshot.wmi,
            tank_level_pct=max(0.0, 65 - self._phase * 10),
            commanded_flow_cc_min=250,
            actual_flow_cc_min=240 - (20 if wmi_fault else 0),
            fault_active=wmi_fault,
        )

        traction = replace(
            snapshot.traction,
            slip_pct=max(0.0, 5 + 3 * math.sin(self._phase * math.tau * 1.2)),
            wheelie_pitch_deg=3 * math.sin(self._phase * math.tau * 0.8),
            intervention_level=rng.choice(["LOW", "MED", "HIGH"]),
            torque_cut_pct=12.0 if 0.48 < self._phase < 0.55 else 0.0,
            active=0.48 < self._phase < 0.55,
            sensor_fault=False,
        )
        clutch = ClutchState(
            slip_pct=max(0.0, 2 + math.sin(self._phase * math.tau * 0.9) * 2),
            severity="NONE",
        )

        lighting = LightingState(
            left_indicator=0.15 < self._phase < 0.22,
            right_indicator=0.65 < self._phase < 0.72,
            high_beam=0.35 < self._phase < 0.50,
            neutral=gear == "N",
            brake=throttle < 10.0 and speed > 5.0,
            oil_warning=False,
        )

        message = "ECU OK | ARDUINO OK | CAN OK"
        alerts: tuple[str, ...] = tuple()
        if wmi_fault:
            message = "WMI FLOW LOW"
            alerts = ("WMI FLOW LOW",)
        elif knock:
            message = "KNOCK DETECTED"
            alerts = ("KNOCK DETECTED",)

        with self._lock:
            mode = self._mode
            fuel_type = self._fuel_type

        environment = replace(
            snapshot.environment,
            mode=mode,
            fuel_type=fuel_type,
            flame_mode_enabled=mode in {"RACE", "ALBATROSS"} or snapshot.environment.flame_mode_enabled,
            rev_limiter_strategy="IGNITION CUT" if (mode in {"RACE", "ALBATROSS"} or snapshot.environment.flame_mode_enabled) else "FUEL CUT",
            ambient_temp_f=72 + math.sin(self._phase * math.tau * 0.2) * 5,
            gps_lock=rng.random() > 0.1,
            gps_latitude=42.3314 + math.sin(self._phase * math.tau) * 0.004,
            gps_longitude=-83.0458 + math.cos(self._phase * math.tau) * 0.004,
            rain=rng.random() > 0.9,
            time=now,
            message_line=message,
            brightness_pct=70 + math.sin(self._phase * math.tau * 0.3) * 20,
            fuel_level_pct=max(5.0, 80 - self._phase * 20),
        )

        shift_light = engine.rpm > 10000

        next_snapshot = StateSnapshot(
            engine=engine,
            temps=temps,
            air_shot=air_shot,
            wmi=wmi,
            traction=traction,
            clutch=clutch,
            lighting=lighting,
            environment=environment,
            economy=replace(snapshot.economy, injector_pulse_width_ms=pulse_width_ms),
            shift_light=shift_light,
            faults=alerts,
        )
        return replace(
            next_snapshot,
            engine=replace(engine, target_boost_psi=calculate_boost_target(next_snapshot)),
        )

    def stream(self) -> Iterator[StateSnapshot]:
        self.start()
        latest: list[StateSnapshot] = []
        latest_lock = threading.Lock()

        def capture(snapshot: StateSnapshot) -> None:
            with latest_lock:
                latest[:] = [snapshot]

        self.subscribe(capture)
        try:
            while True:
                with latest_lock:
                    snapshot = latest.pop() if latest else None
                if snapshot is not None:
                    yield snapshot
                else:
                    time.sleep(self._tick_period)
        finally:
            self.stop()

    def sample(self, phase: float = 0.5) -> StateSnapshot:
        """Generate a single snapshot without starting the streaming loop."""
        rng = random.Random(1337)
        previous = StateSnapshot()
        self._phase = phase % 1.0
        return self._next_snapshot(previous, rng)
