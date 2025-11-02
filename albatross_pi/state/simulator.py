"""Synthetic state generator for development and HUD demos."""
from __future__ import annotations

import math
import random
import threading
import time
from dataclasses import replace
from datetime import datetime
from typing import Callable, Iterator

from .snapshot import (
    AirShotState,
    EngineState,
    EnvironmentState,
    StateSnapshot,
    TemperaturesState,
    TractionState,
    WMIState,
)

TICK_PERIOD = 1 / 60.0


class StateSimulator:
    """Generate a continuous stream of synthetic `StateSnapshot` objects."""

    def __init__(self, tick_period: float = TICK_PERIOD) -> None:
        self._tick_period = tick_period
        self._running = False
        self._lock = threading.Lock()
        self._subscribers: list[Callable[[StateSnapshot], None]] = []
        self._thread: threading.Thread | None = None
        self._phase = 0.0

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
        gear_index = max(1, min(6, int(speed // 12) + 1))
        gear = str(gear_index)
        boost = max(0.0, 18.0 * math.sin(self._phase * math.tau))
        target_boost = 20.0
        afr_left = 12.5 + math.sin(self._phase * math.tau * 2) * 0.2
        afr_right = 12.6 + math.cos(self._phase * math.tau * 2) * 0.2
        spark = 14.0 + math.sin(self._phase * math.tau * 0.5) * 5
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
        )

        temps = replace(
            snapshot.temps,
            coolant_temp_f=190 + 5 * math.sin(self._phase * math.tau * 0.7),
            oil_temp_f=205 + 3 * math.sin(self._phase * math.tau * 0.5),
            oil_pressure_psi=60 + 10 * math.sin(self._phase * math.tau * 1.5),
            battery_voltage=13.8 + math.sin(self._phase * math.tau * 0.25) * 0.05,
            intake_temp_f=90 + 15 * abs(math.sin(self._phase * math.tau)),
            exhaust_temp_f=1250 + 50 * math.sin(self._phase * math.tau),
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
        )

        message = "ECU OK | ARDUINO OK | CAN OK"
        if wmi_fault:
            message = "WMI FLOW LOW"
        elif knock:
            message = "KNOCK DETECTED"

        environment = replace(
            snapshot.environment,
            mode=rng.choice(["ECO", "NORMAL", "SPORT", "RACE", "ALBATROSS"]),
            fuel_type=rng.choice(["93", "100", "E85"]),
            ambient_temp_f=72 + math.sin(self._phase * math.tau * 0.2) * 5,
            gps_lock=rng.random() > 0.1,
            rain=rng.random() > 0.9,
            time=now,
            message_line=message,
            brightness_pct=70 + math.sin(self._phase * math.tau * 0.3) * 20,
        )

        shift_light = engine.rpm > 10000
        gl_mood = "alert" if knock or wmi_fault else "happy"

        return StateSnapshot(
            engine=engine,
            temps=temps,
            air_shot=air_shot,
            wmi=wmi,
            traction=traction,
            environment=environment,
            shift_light=shift_light,
            gl_sprite_mood=gl_mood,
            faults=(message,) if message != "ECU OK | ARDUINO OK | CAN OK" else tuple(),
        )

    def stream(self) -> Iterator[StateSnapshot]:
        self.start()
        queue: list[StateSnapshot] = []

        def capture(snapshot: StateSnapshot) -> None:
            queue.append(snapshot)

        self.subscribe(capture)
        try:
            while True:
                if queue:
                    yield queue.pop(0)
                else:
                    time.sleep(self._tick_period)
        finally:
            self.stop()
