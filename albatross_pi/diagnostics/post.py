"""Read-only, evidence-based HUD startup checks; never actuator commissioning."""
from dataclasses import dataclass
import math

from ..thermal.config import DEFAULT_CONFIG_PATH, load_thermal_config
from ..thermal.service import ThermalService
from ..thermal.model import SensorStatus

# Presentation timing only; does not change controller safety timeouts.
INTRO_S, STEP_S, HOLD_S = 0.4, 0.45, 0.4
RX_LENGTHS = {0x100: 2, 0x105: 4, 0x107: 1, 0x10C: 2, 0x139: 6,
              0x147: 2, 0x16D: 8}


@dataclass(frozen=True)
class PostResult:
    name: str
    status: str
    detail: str


class PowerOnSelfTest:
    def __init__(self, config_path=None):
        self.config = load_thermal_config(config_path)
        self.expected_crc = ThermalService.config_crc32(config_path or DEFAULT_CONFIG_PATH)
        self.started_at = None
        self.complete = False
        self.results = ()

    @property
    def duration_s(self):
        return INTRO_S + len(self.results) * STEP_S + HOLD_S

    @property
    def needs_ack(self):
        return any(r.status in ("FAULT", "UNVERIFIED") for r in self.results)

    def update(self, state, now, *, display_ok=True, usb_present=False):
        if self.complete:
            return self.results
        if self.started_at is None:
            self.started_at = now
        snapshot_age = (max(0, now - state.telemetry_observed_at)
                        if state.telemetry_observed_at is not None else math.inf)
        # Config broadcasts every 2 s; status streams use the existing 1.5 s HUD window.
        fresh = lambda fid: state.telemetry_age_s.get(fid, math.inf) + snapshot_age <= (2.5 if fid == 0x16D else 1.5)
        dyn, air, thermal, fm = state.dynamics, state.air_shot.v2, state.thermal, state.fault_management
        dynamics_ok = dyn.online and snapshot_age <= .3
        air_ok = air.online and snapshot_age <= .3
        fm_ok = fm is not None and fm.online and snapshot_age <= .3
        thermal_ok = thermal.online and snapshot_age <= .75
        rows = []

        def check(name, present, healthy=True, detail="Fresh telemetry; not a physical load test."):
            rows.append(PostResult(name, ("OK" if healthy else "FAULT") if present else "WAIT", detail))

        def defer(name, detail):
            rows.append(PostResult(name, "DEFER", detail))

        check("DISPLAY", True, display_ok, "Framebuffer available; inspect the physical screen.")
        check("ECU TELEMETRY", fresh(0x100), 0 <= state.engine.rpm <= 65535,
              "Received RPM frame. Zero RPM is valid with engine stopped.")
        check("MAIN TEENSY", dynamics_ok or fm_ok or fresh(0x147))
        check("THERMAL NODE", thermal_ok)
        check("THERMAL CONFIG", thermal_ok and fresh(0x16D),
              thermal.config_crc32 == self.expected_crc, "Node CRC must match the HUD thermal configuration.")
        for name, bus in (("NTC BANKS", "ADS1115"), ("PT1000 BANKS", "MAX31865"),
                          ("THERMOCOUPLES", "MAX31856")):
            readings = [thermal.get(s.key) for s in self.config.sensors if s.enabled and s.source_bus.upper() == bus]
            reported = thermal_ok and bool(readings) and all(
                r is not None and r.status not in (SensorStatus.STALE, SensorStatus.NOT_CONFIGURED)
                for r in readings)
            healthy = all(r is not None and r.valid and math.isfinite(r.temperature_c)
                          and r.age_ms + snapshot_age * 1000 <= 750 for r in readings)
            check(name, reported, healthy, "All configured probes must report valid, fresh measurements.")
        check("VDC TELEMETRY", dynamics_ok)
        check("VDC CONFIG", dynamics_ok, dyn.calibrated and dyn.calibration_matches,
              "Engineering calibration accepted and configuration fingerprint matched.")
        evaluated = dynamics_ok and dyn.calibrated and dyn.state not in ("INIT", "SELF TEST")
        check("DBWX2 / APS / TPS", evaluated, not dyn.faults & sum(1 << b for b in (5, 6, 7, 8, 9, 11)),
              "VDC-reported DBW health only. No startup throttle sweep.")
        check("IMU", evaluated, not dyn.faults & sum(1 << b for b in (3, 4, 12)),
              "VDC-reported inertial health; mounting and calibration require a fixture test.")
        if evaluated and dyn.faults & 6:
            check("WHEEL SPEED", True, False, "VDC reports a wheel-speed fault.")
        else:
            defer("WHEEL SPEED", "Zero speed cannot prove pulse sensing. Rotate wheels on an appropriate fixture.")
        check("FAULT MANAGER", fm_ok, fm_ok and not fm.missing_calibration and not fm.alerts,
              "Fresh supervisor bundle, no reported faults or missing limit calibration.")
        check("AIR SHOT V2", air_ok, not air.driver_faults and air.state != "FAULT",
              "Controller telemetry only; valves remain under main-controller authority.")
        check("AIR PRESSURE", air_ok, air.pressure_valid,
              "Controller pressure validity. No valve firing or pressure-build test.")
        defer("MASTER NC VALVE", "Command telemetry is not proof of physical closure. Verify isolation on the bench.")
        check("WMI", fresh(0x139), not state.wmi.fault_active,
              "Reported status only; pump and flow response require a controlled test.")
        if fresh(0x100) and state.engine.rpm == 0 and fresh(0x105):
            defer("OIL PRESSURE", "Engine stopped: zero pressure is expected; running protection remains ECU-owned.")
        else:
            check("OIL PRESSURE", fresh(0x100) and fresh(0x105),
                  math.isfinite(state.temps.oil_pressure_psi) and state.temps.oil_pressure_psi > 0,
                  "Telemetry plausibility only; not validation of the RPM/temperature pressure envelope.")
        check("BATTERY VOLTAGE", fresh(0x10C),
              math.isfinite(state.temps.battery_voltage) and state.temps.battery_voltage > 0)
        check("FUEL LEVEL", fresh(0x107), 0 <= state.environment.fuel_level_pct <= 100)
        defer("EWG RESPONSE", "Actuator position/current response requires separate bench commissioning.")
        defer("PDM / FAN", "No commissioned feedback proof; no startup load activation.")
        if usb_present:
            check("USB GRIP", True, True, "Controller enumerated; manually verify individual buttons.")
        else:
            defer("USB GRIP", "No controller enumerated; keyboard operation remains available.")
        self.results = tuple(rows)
        if now - self.started_at >= self.duration_s:
            self.results = tuple(PostResult(r.name, "UNVERIFIED" if r.status == "WAIT" else r.status, r.detail)
                                 for r in self.results)
            self.complete = True
        return self.results
