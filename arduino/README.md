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
- WMI tank, flow, and status sensing for HUD/boost safety.
- Motorcycle lamp status reporting for HUD indicators/high beam/brake/oil warning.

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
- Shot output drops as soon as intake pressure reaches the Pi-requested boost target, capped by the mode safety limit.
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

- Arduino reports lamp status in `0x13B` payload byte 0: bit 0 left indicator, bit 1 right indicator, bit 2 high beam, bit 3 neutral, bit 4 brake light, bit 5 oil warning. The oil warning lamp is status only; pressure decisions use the real pressure sensor path.
- Arduino can report fallback oil pressure in `0x13C` as psi x10 from `OIL_PRESSURE_SENSOR_PIN` if the ECU cannot publish oil pressure.
- Arduino reports fuel type in `0x13D` using the shared fuel code map: 0=87, 1=91, 2=93, 3=100, 4=E85, 5=C16.
- Arduino accepts Pi fuel type selection on `0x129` using the same shared fuel code map.
- Arduino reports WMI status in `0x139`: byte 0 tank level %, bytes 1-2 commanded cc/min, bytes 3-4 sensed cc/min, byte 5 aggregate fault.
- Pi is source of truth for flame mode (`0x122`) and limp command (`0x123`).
- Arduino reports Air Shot active flag in `0x130` payload byte 1 for HUD “air shot active” indicator.


## Dual wastegate pinout

The sketch exposes separate pins for each 3-pin actuator:

- WG1: `WG1_PWM_PIN`, `WG1_DIR_PIN`, `WG1_EN_PIN`
- WG2: `WG2_PWM_PIN`, `WG2_DIR_PIN`, `WG2_EN_PIN`

Both channels currently mirror the same command request for synchronized twin-actuator control.


## Mega 2560 hardware notes

- Wheel Hall sensors are mapped to external interrupt pins `3` and `18` (valid interrupt pins on Mega 2560).
- MCP2515 CAN interrupt remains on pin `2`.
- Dual e-wastegate channels use independent `PWM/DIR/EN` groups; PWM outputs are on pins `5` and `6` (both PWM-capable on Mega).
- Air compressor relay uses pin `27`; pin `10` is reserved for MCP2515 chip select.
- Lamp feed inputs use pins `28`-`32`; condition bike voltage to 5V logic and provide external pulldowns.
- Fallback oil pressure input uses `A0`, assuming a 0.5V-4.5V sender scaled to 0-100 psi.
- WMI tank level uses `A1`, WMI flow input uses interrupt-capable pin `19`, and WMI pressure/status OK uses pin `33` with internal pullup. `WMI_PRESSURE_OK_ACTIVE_LOW` controls status polarity.
