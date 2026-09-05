"""Legacy HUD fields projected from primary thermal-node readings only."""
from dataclasses import replace
import math


def primary_temperatures(base, thermal):
    def value(*keys):
        readings = [thermal.get(key) for key in keys]
        if not thermal.online or any(r is None or not r.valid or not math.isfinite(r.temperature_c) for r in readings):
            return -1.0  # Existing unavailable sentinel; never a replacement sensor.
        return max(r.temperature_c for r in readings) * 1.8 + 32
    return replace(base,
        coolant_temp_f=value("HEAD_COOLANT_LEFT", "HEAD_COOLANT_RIGHT"),
        oil_temp_f=value("OIL_GALLERY"), intake_temp_f=value("PLENUM_IAT"),
        exhaust_temp_f=value("EGT_LEFT", "EGT_RIGHT"),
        exhaust_left_temp_f=value("EGT_LEFT"), exhaust_right_temp_f=value("EGT_RIGHT"),
        alternator_temp_f=-1.0)
