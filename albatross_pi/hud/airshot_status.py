"""Presentation of rider intent versus controller observations; no control logic."""
from dataclasses import dataclass
import time


@dataclass(frozen=True)
class AirShotRequest:
    requested_mode: str | None = None
    requested_at: float = 0.0
    fire_held: bool = False
    mode_send_error: bool = False
    fire_send_error: bool = False


REASON_TEXT = {
    "NONE": "No controller inhibit reported", "OFF": "Controller mode is OFF",
    "UNCALIBRATED": "Controller configuration is not valid", "CAN STALE": "Required CAN inputs are stale",
    "PRESSURE SENSOR": "Tank pressure sensor is invalid", "LOW PRESSURE": "Tank pressure is too low",
    "REGULATOR": "Regulated pressure is outside limits", "ENGINE COLD": "Coolant or oil is below the warm-up limit",
    "RPM RANGE": "Engine RPM is outside the allowed range", "TORQUE LOW": "Rider torque request is too low",
    "DBW": "Throttle control permission is unavailable", "TRACTION": "Traction control is intervening",
    "WHEELIE": "Wheelie control is intervening", "THERMAL": "Thermal protection is active or data unavailable",
    "WMI": "Water/meth permission is unavailable", "ECU PROTECTION": "ECU protection is active",
    "DRIVER": "Valve driver fault", "ALREADY BOOSTED": "Boost is already at the completion threshold",
    "RECOVERY": "Waiting for recovery time", "MAX DURATION": "Maximum shot duration reached",
    "RELEASED": "Rider released FIRE", "SPOOL COMPLETE": "Turbo spool assistance is complete",
    "OVERBOOST": "Boost exceeds the protection limit", "BUDGET": "Air Shot time budget exhausted",
    "WASTEGATE": "Wastegate permission is unavailable", "SHADOW": "Shadow test: valves are not driven",
    "SERVICE": "Controller is in service mode", "FUEL": "Fuel, gear or ride-mode eligibility is not met",
}


def airshot_status(air, request=None, now=None):
    request = request or AirShotRequest()
    now = time.monotonic() if now is None else now
    wanted = request.requested_mode or air.mode
    intent = f"REQ {wanted}" + (" + FIRE" if request.fire_held else "")
    confirmed = air.mode if air.online else "UNKNOWN"
    reason = REASON_TEXT.get(air.reason, "Controller reason: " + air.reason)
    if not air.online:
        return intent, "UNCONFIRMED / DATA STALE", "Controller telemetry is offline; request cannot be confirmed"
    if request.mode_send_error:
        return intent, "MODE SEND FAILED", "Mode request could not be sent; controller mode is " + confirmed
    if request.requested_mode and request.requested_mode != air.mode:
        status = "WAITING FOR MODE" if now-request.requested_at < 1 else "MODE NOT CONFIRMED"
        return intent, status + " / " + confirmed, "Requested " + wanted + "; controller still reports " + confirmed
    if request.fire_send_error and request.fire_held:
        return intent, "FIRE SEND FAILED", "FIRE request could not be sent"
    if air.flags & 8 and air.mode != "OFF":
        return intent, "SHADOW / NO OUTPUT", REASON_TEXT["SHADOW"]
    if air.state in ("FIRING", "TAPERING"):
        return intent, air.state, "Controller reports active valve commands" if air.reason == "NONE" else reason
    if air.reason != "NONE":
        return intent, air.state + " / " + air.reason, reason
    if request.fire_held:
        return intent, "FIRE NOT CONFIRMED", "No firing state or inhibit reason received yet"
    if air.mode == "AUTO":
        return intent, air.state + " / AUTO WAIT", "Waiting for the controller's automatic trigger conditions"
    if air.mode == "MANUAL":
        return intent, air.state + " / PRESS FIRE", "Manual mode selected; waiting for FIRE"
    return intent, air.state, reason
