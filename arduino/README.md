# Albatross Controller Firmware

Production controller target: **Teensy 4.1**.

Legacy controller target: **Arduino Mega 2560 Rev3 + MCP2515**, retained under
`arduino/legacy/mega2560/albatross_controller/` for reference and bench fallback.

## Production Teensy 4.1 Sketch

- Main sketch:
  `arduino/teensy41/albatross_controller_teensy41/albatross_controller_teensy41.ino`
- CAN library: `FlexCAN_T4`
- CAN bus: Teensy native `CAN1` at 500 kbit/s.
- CAN wiring: Teensy pin `22` = CAN1 RX, Teensy pin `23` = CAN1 TX, through an
  external 3.3 V CAN transceiver.
- Important: Teensy 4.1 GPIO and ADC pins are **not 5 V tolerant**. Every bike
  signal, lamp feed, Hall input, flow input, and 0.5-4.5 V sender must be
  conditioned to 0-3.3 V before it reaches the Teensy.

## What This Controller Owns

- Dual electronic wastegate actuator outputs, PWM/DIR/EN per actuator.
- Air Shot compressor relay + shot latch/rearm logic.
- Air Shot active status reporting for HUD indicator.
- Wheel-speed reporting for HUD speedometer from Hall sensor measurements.
- Traction control slip estimation from front/rear Hall sensors.
- Torque-reduction request messaging to ECU over CAN.
- WMI + flame interlocks and limp-mode enforcement.
- WMI tank, flow, and status sensing for HUD/boost safety.
- Motorcycle lamp status reporting for HUD indicators/high beam/brake/oil warning.

## Teensy 4.1 Pin Map

| Teensy pin | Direction | Function | Hookup notes |
| --- | --- | --- | --- |
| 22 | CAN RX | CAN1 RX | To 3.3 V CAN transceiver RXD |
| 23 | CAN TX | CAN1 TX | To 3.3 V CAN transceiver TXD |
| 2 | Output PWM | Wastegate actuator 1 PWM | To actuator power driver/H-bridge command input |
| 3 | Output | Wastegate actuator 1 direction | To actuator power driver/H-bridge direction input |
| 4 | Output | Wastegate actuator 1 enable | To actuator power driver/H-bridge enable input |
| 5 | Output PWM | Wastegate actuator 2 PWM | To actuator power driver/H-bridge command input |
| 6 | Output | Wastegate actuator 2 direction | To actuator power driver/H-bridge direction input |
| 9 | Output | Wastegate actuator 2 enable | To actuator power driver/H-bridge enable input |
| 10 | Output PWM | WMI pump command | Drive relay/MOSFET module, active high |
| 11 | Output | Flame mode interlock | Drive external interlock circuit, active high |
| 12 | Output | Air Shot solenoid | Drive MOSFET/relay, active high |
| 24 | Output | Air compressor relay | Drive relay/MOSFET module, active high |
| 18 | Input pullup | Front wheel Hall sensor | Open collector/open drain or conditioned 3.3 V pulse |
| 19 | Input pullup | Rear wheel Hall sensor | Open collector/open drain or conditioned 3.3 V pulse |
| 20 | Input pullup | WMI flow sensor | Pulse input, 450 pulses/L default |
| 25 | Input pullup | Neutral switch/lamp | Active low; condition to 3.3 V |
| 26 | Input | Left indicator lamp sense | Condition bike voltage to 3.3 V logic, external pulldown |
| 27 | Input | Right indicator lamp sense | Condition bike voltage to 3.3 V logic, external pulldown |
| 28 | Input | High beam lamp sense | Condition bike voltage to 3.3 V logic, external pulldown |
| 29 | Input | Brake lamp sense | Condition bike voltage to 3.3 V logic, external pulldown |
| 30 | Input | Stock oil warning lamp sense | Status only; not the real oil pressure gauge path |
| 31 | Input pullup | WMI pressure/status OK | Active low by default; switch pulls to ground when OK |
| A0 | Analog input | Fallback oil pressure | 0.5-4.5 V sender scaled to about 0.33-3.0 V at Teensy |
| A1 | Analog input | WMI tank level | 0-5 V sender scaled to 0-3.3 V |
| A2 | Analog input | Air Shot tank pressure | 0.5-4.5 V sender scaled to about 0.33-3.0 V at Teensy |

## Single-Point Boost Configuration

Mode boost caps are centralized in `modeBoostCap()` so each mode only has one
editable value.

The Pi calculates a fuel/WMI/temperature-aware boost target and sends it over
CAN. The Teensy is the actual boost controller: it clamps that request by mode
and limp state, compares requested boost to MS3-reported MAP/boost, computes
wastegate actuator duty, and drives the wastegate actuator power stages
directly. There is no separate boost controller between the Teensy and the
wastegate actuator drivers.

If ECU telemetry or Pi command traffic goes stale, Teensy forces a no-boost
limp state, disables flame/WMI/Air Shot outputs, and keeps publishing status
frames so the HUD can report the fault.

## Air Shot Behavior

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
- Compressor turns off at 145 psi, while moving, above low throttle, during
  cranking, below 12.2 V, during limp/undervoltage, or during a shot.
- The Air Shot tank is treated as a buffer: compressor refill is independent
  from shot demand and should not start just because the rider or auto logic
  requested a shot.
- Automatic shots trigger only in RACE or ALBATROSS and only if TPS > 90%,
  gear >= 2, and RPM > 5500.
- Manual Air Shot requests arrive from the Pi on `0x125` and may latch a shot
  in RACE/ALBATROSS when boost is at least 4 psi below request, gear >= 2,
  RPM > 3000, TPS > 70%, tank pressure has available charge, tank pressure is
  at least 12 psi above manifold pressure, and the system is not already latched.
- Shot output drops as soon as intake pressure reaches the Pi-requested boost
  target, capped by the mode safety limit.
- Shot output also drops after 10 seconds max latch time, or immediately if
  intake/manifold pressure is equal to or greater than Air Shot tank pressure.
- Re-fire is blocked until throttle is lifted.
- While a shot is active, and for a brief 350 ms decay window after it closes,
  the wastegate loop uses a clamped boost value so transient Air Shot pressure
  does not open the wastegates and kill turbo spool. The Air Shot solenoid still
  uses real manifold pressure for shutoff, and a >3 psi overshoot exits the
  clamp so the wastegate can protect the engine.
- `shots_remaining` is conservative for a 0-150 psi tank:
  - <35 psi => 0
  - 35-74 psi => 1
  - 75-114 psi => 2
  - >=115 psi => 3

## Traction Control

Hall sensor wheel speed parameters are centralized constants:

- `FRONT_WHEEL.circumference_m`
- `REAR_WHEEL.circumference_m`
- `FRONT_WHEEL.magnets`
- `REAR_WHEEL.magnets`

Traction level is commanded by Pi CAN frame (`0x124`) with levels LOW, MED,
HIGH, and OFF. Teensy computes filtered slip ratio and publishes torque-cut
request (`0x12A`) plus external slip request (`0x12B`) for ECU-side power
reduction.

## CAN Notes

- Teensy reports lamp status in `0x13B` payload byte 0: bit 0 left indicator,
  bit 1 right indicator, bit 2 high beam, bit 3 neutral, bit 4 brake light,
  bit 5 oil warning. The oil warning lamp is status only; pressure decisions use
  the real pressure sensor path.
- Teensy can report fallback oil pressure in `0x13C` as psi x10 from
  `OIL_PRESSURE_SENSOR_PIN` if the ECU cannot publish oil pressure. On the
  current MS3Pro Mini plan, oil pressure and oil temperature are MS3-owned
  inputs, so this should stay a bench/fallback path.
- Teensy consumes ECU fuel level on `0x107`; fuel type selection is not inferred
  from this frame.
- MS3 publishes flex-fuel ethanol content to the HUD on ECU frame `0x10D`
  (byte 0 = ethanol %). Teensy does not infer fuel type from the flex sensor;
  the Pi/HUD uses ethanol percentage for supervisory boost caps.
- Teensy reports fuel type in `0x13D` using the shared fuel code map:
  0=87, 1=91, 2=93, 3=100, 4=E85, 5=C16.
- Teensy accepts Pi fuel type selection on `0x129` using the same map.
- Teensy reports WMI status in `0x139`: byte 0 tank level %, bytes 1-2
  commanded cc/min, bytes 3-4 sensed cc/min, byte 5 aggregate fault.
- Teensy reports service-mode diagnostics for the HUD: `0x13F` sensor voltages
  (oil sender ADC mV, WMI tank ADC mV, Teensy ADC reference mV, Air Shot tank
  pressure sender ADC mV), `0x145` digital input/output/command/fault bitfields,
  and `0x146` firmware version.
- Teensy reports limp status in `0x147`: byte 0 active flag, byte 1 reason code.

## Legacy Mega 2560

The previous Mega/MCP2515 sketch remains in
`arduino/legacy/mega2560/albatross_controller/`. It is no longer the production
target, but it is useful for comparing behavior or running old bench hardware.
