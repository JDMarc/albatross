# Albatross Arduino Controller

This sketch is pinned and validated for **Arduino Mega 2560 Rev3** pin capabilities.


## What this controller now owns

- Arduino-side boost control for dual (2x) 3-pin electronic wastegate actuators
  (PWM + DIR + EN per actuator).
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

The Pi calculates a fuel/WMI/temperature-aware boost target and sends it over CAN.
The Arduino is the actual boost controller: it clamps that request by mode and
limp state, compares requested boost to MS3-reported MAP/boost, computes
wastegate actuator duty, and drives the wastegate actuator power stages directly.
There is no separate boost controller between the Arduino and the wastegate
actuator drivers.

If ECU telemetry or Pi command traffic goes stale, Arduino forces a no-boost
limp state, disables flame/WMI/Air Shot outputs, and keeps publishing status
frames so the HUD can report the fault.

## Air Shot behavior

- Compressor only runs when:
  - bike speed is effectively zero (<~1 mph),
  - TPS is below 5%,
  - engine is not cranking,
  - bus voltage is at least 12.2 V,
  - neither ECU voltage nor Pi limp reason reports undervoltage,
  - no limp condition is active,
  - no Air Shot is currently latched,
  - tank pressure is at or below 95 psi,
  - the 15 second restart delay after the last shutoff has expired.
- Compressor turns off at 145 psi, while moving, above low throttle, during cranking, below 12.2 V, during limp/undervoltage, or during a shot.
- The Air Shot tank is treated as a buffer: compressor refill is independent from shot demand and should not start just because the rider or auto logic requested a shot.
- Automatic shots trigger only in RACE or ALBATROSS and only if:
  - TPS > 90%
  - gear >= 2
  - RPM > 5500
- Manual Air Shot requests arrive from the Pi on `0x125` and may latch a shot in RACE/ALBATROSS when boost is at least 4 psi below request, gear >= 2, RPM > 3000, TPS > 70%, tank pressure has available charge, tank pressure is at least 12 psi above manifold pressure, and the system is not already latched.
- Shot remains latched until intake pressure reaches mode-specific limit.
- Shot output drops as soon as intake pressure reaches the Pi-requested boost target, capped by the mode safety limit.
- Shot output also drops after 10 seconds max latch time, or immediately if intake/manifold pressure is equal to or greater than Air Shot tank pressure.
- Re-fire is blocked until throttle is lifted (rearm logic).
- While a shot is active, and for a brief 350 ms decay window after it closes, the wastegate loop uses a clamped boost value so transient Air Shot pressure does not open the wastegates and kill turbo spool. The Air Shot solenoid still uses real manifold pressure for shutoff, and a >3 psi overshoot exits the clamp so the wastegate can protect the engine.
- `shots_remaining` is conservative for a 0-150 psi tank:
  - <35 psi => 0
  - 35-74 psi => 1
  - 75-114 psi => 2
  - >=115 psi => 3

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

Arduino computes filtered slip ratio and publishes torque-cut request (`0x12A`) plus external slip request (`0x12B`) for ECU-side power reduction.
Arduino also publishes HUD traction status (`0x13E`) with signed slip %, torque-cut %, active flag, and sensor-fault flag.
The controller includes a low-speed gate, slip filtering, hysteresis, torque-cut ramping, and wheel-speed plausibility suppression so transient Hall pulse noise does not request cuts.

## CAN notes

- Arduino reports lamp status in `0x13B` payload byte 0: bit 0 left indicator, bit 1 right indicator, bit 2 high beam, bit 3 neutral, bit 4 brake light, bit 5 oil warning. The oil warning lamp is status only; pressure decisions use the real pressure sensor path.
- Arduino can report fallback oil pressure in `0x13C` as psi x10 from `OIL_PRESSURE_SENSOR_PIN` if the ECU cannot publish oil pressure. On the current MS3Pro Mini plan, oil pressure and oil temperature are MS3-owned inputs, so this should stay a bench/fallback path rather than the normal bike path.
- Arduino consumes ECU fuel level on `0x107`; fuel type selection is not inferred from this frame.
- MS3 publishes flex-fuel ethanol content to the HUD on ECU frame `0x10D` (byte 0 = ethanol %). Arduino does not infer fuel type from the flex sensor; the Pi/HUD uses ethanol percentage for supervisory boost caps.
- Arduino reports fuel type in `0x13D` using the shared fuel code map: 0=87, 1=91, 2=93, 3=100, 4=E85, 5=C16.
- Arduino accepts Pi fuel type selection on `0x129` using the same shared fuel code map.
- Arduino reports WMI status in `0x139`: byte 0 tank level %, bytes 1-2 commanded cc/min, bytes 3-4 sensed cc/min, byte 5 aggregate fault.
- Arduino reports service-mode diagnostics for the HUD: `0x13F` sensor voltages (oil sender mV, WMI tank mV, 5V rail mV, Air Shot tank pressure sender mV), `0x145` digital input/output/command/fault bitfields, and `0x146` firmware version (device, major, minor, patch, build).
- Arduino reports limp status in `0x147`: byte 0 active flag, byte 1 reason code. Reason codes are shared with the Pi ID table (`0x00` none, `0x01` Pi request, `0x02` engine run off, `0x03` ECU CAN stale, `0x04` Pi command stale, `0x05` thermal, `0x06` low oil pressure, `0x07` battery voltage, `0x08` knock, `0x09` ECU sensor, `0x0A` NFC auth, `0x0B` safety supervisor, `0x0C` overboost, `0x0D` WMI fault, `0x0E` clutch slip).
- Pi sends ECU fuel profile selection on `0x150`: fuel code, fuel table index, and stoich AFR x100. Current table indexes are 0=pump gas, 1=100 octane, 2=E85, 3=C16. Pi sends ECU spark table selection on `0x151`: 0 initial map, 1 SPORT+ performance map.
- Pi sends MS3 rev-limiter strategy selection on `0x152`: 0 fuel cut, 1 ignition/spark cut. HUD flame mode requests ignition cut, and RACE/ALBATROSS auto-enable flame mode.
- Pi is source of truth for flame mode (`0x122`) and limp command (`0x123`).
- Pi sends dedicated rider Air Shot requests on `0x125`; Arduino treats the frame as a short-lived request and still applies all Air Shot safety gates before latching the solenoid.
- Pi engine run switch (`0x127`) is enforced by Arduino as limp/no-boost plus 100% torque-cut request while OFF.
- Arduino enters no-boost limp if ECU telemetry is stale for `ECU_CAN_TIMEOUT_MS`
  or Pi command traffic is stale for `PI_CAN_TIMEOUT_MS`.
- Arduino reports Air Shot active flag in `0x130` payload byte 1 for HUD “air shot active” indicator.


## Dual wastegate pinout

The sketch exposes separate pins for each 3-pin actuator. These pins are logic
signals for external actuator power stages/H-bridges, not direct motor power:

- WG1: `WG1_PWM_PIN`, `WG1_DIR_PIN`, `WG1_EN_PIN`
- WG2: `WG2_PWM_PIN`, `WG2_DIR_PIN`, `WG2_EN_PIN`

Both channels currently mirror the same command request for synchronized twin-actuator control.


## Mega 2560 hardware notes

- Wheel Hall sensors are mapped to external interrupt pins `3` and `18` (valid interrupt pins on Mega 2560).
- MCP2515 CAN interrupt remains on pin `2` with internal pullup enabled.
- MCP2515 chip select uses pin `10`; Mega hardware SS pin `53` is held as `OUTPUT/HIGH` to keep SPI in master mode.
- Dual e-wastegate channels use independent `PWM/DIR/EN` groups; PWM outputs are on pins `5` and `6` (both PWM-capable on Mega).
- Air compressor relay uses pin `27`; pin `10` is reserved for MCP2515 chip select.
- Lamp feed inputs use pins `28`-`32`; condition bike voltage to 5V logic and provide external pulldowns.
- Fallback oil pressure input uses `A0`, assuming a 0.5V-4.5V sender scaled to 0-100 psi.
- WMI tank level uses `A1`, Air Shot tank pressure uses `A2`, WMI flow input uses interrupt-capable pin `19`, and WMI pressure/status OK uses pin `33` with internal pullup. `WMI_PRESSURE_OK_ACTIVE_LOW` controls status polarity.
