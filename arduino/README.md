# Albatross Arduino Controller

This sketch is pinned and validated for **Arduino Mega 2560 Rev3** pin capabilities.


## What this controller now owns

- Dual (2x) 3-pin electronic wastegate actuator command outputs (PWM + DIR + EN per actuator).
- Air Shot compressor relay + shot latch logic.
- Air Shot active status reporting for HUD indicator.
- Wheel-speed reporting for HUD speedometer from Hall sensor measurements.
- Traction control slip estimation from front/rear Hall sensors.
- Torque-reduction request messaging to ECU over CAN.
- WMI + flame interlocks and limp-mode enforcement.

## Single-point boost configuration

Mode boost caps are centralized in `modeBoostCap()` so each mode only has one editable value.

## Air Shot behavior

- Compressor only runs when:
  - tank pressure is below threshold,
  - engine speed is under 1500 RPM,
  - TPS is below 5%.
- Shots trigger only in RACE or ALBATROSS and only if:
  - TPS > 90%
  - gear >= 2
  - RPM > 5500
- Shot remains latched until intake pressure reaches mode-specific limit.
- Re-fire is blocked until throttle is lifted (rearm logic).
- `shots_remaining` is computed from tank pressure using logarithmic scaling:
  - <=18 psi => 0
  - >=68 psi => 5

## Traction control

Hall sensor wheel speed parameters are centralized constants:

- `FRONT_WHEEL.circumference_m`
- `REAR_WHEEL.circumference_m`
- `FRONT_WHEEL.magnets`
- `REAR_WHEEL.magnets`

Traction level is commanded by Pi CAN frame (`0x124`) with levels:

1. LOW
2. MED
3. HIGH
4. OFF

Arduino computes slip ratio and publishes torque-cut request (`0x125`) for ECU-side power reduction.

## CAN notes

- Pi is source of truth for flame mode (`0x122`) and limp command (`0x123`).
- Arduino reports Air Shot active flag in `0x130` payload byte 1 for HUD “air shot active” indicator.


## Dual wastegate pinout

The sketch exposes separate pins for each 3-pin actuator:

- WG1: `WG1_PWM_PIN`, `WG1_DIR_PIN`, `WG1_EN_PIN`
- WG2: `WG2_PWM_PIN`, `WG2_DIR_PIN`, `WG2_EN_PIN`

Both channels currently mirror the same command request for synchronized twin-actuator control.


## Mega 2560 hardware notes

- Wheel Hall sensors are mapped to external interrupt pins `18` and `19` (valid interrupt pins on Mega 2560).
- MCP2515 CAN interrupt remains on pin `2`.
- Dual e-wastegate channels use independent `PWM/DIR/EN` groups; PWM outputs are on pins `5` and `6` (both PWM-capable on Mega).
