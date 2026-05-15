# MS3Pro + TunerStudio Setup Guide for The Albatross

## Short answer: can TunerStudio / MS3Pro do this?

Yes. The MS3Pro firmware and TunerStudio workflow support the core ECU-side features this project needs, including:

- table switching and alternate maps
- launch control / 2-step behaviors
- boost control strategies (open-loop and closed-loop with table-based targets)
- CAN messaging to cooperate with external controllers

This means we can keep the architecture: **Pi plans + supervises, Arduino performs fast actuator control, MS3Pro manages core fueling/ignition/engine safeguards**.

## Recommended control split (final)

- **Pi**: mode selection UX, weather/profile logic, requests (`boost target`, `flame request`, `limp request`), HUD.
- **Arduino**: electronic wastegate actuator command, Air Shot compressor + shot latch logic, WMI/flame interlocks, failsafe execution.
- **MS3Pro**: fueling, ignition, safe map selection, launch/2-step, hard engine protections.

## Required MS3Pro configuration steps

## 1) Firmware + project baseline

1. Load a stable MS3Pro firmware build supported by your hardware.
2. Create a fresh TunerStudio project for that exact firmware signature.
3. Confirm all critical sensors are calibrated (TPS, MAP, CLT, IAT, wideband, oil pressure if wired).

## 2) Ignition and fueling safety baseline

1. Configure conservative base spark and VE maps for first-fire.
2. Enable over-temp and AFR protection strategies available in your firmware.
3. Set hard rev limit and soft rev limit with predictable cut behavior.

## 3) Dual map / table switching for safe timing map

1. Enable table/map switching input strategy in TunerStudio.
2. Reserve a low-risk timing/boost-capable “safe” map.
3. Wire or map a software-switchable input path that Arduino/Pi can command indirectly.
4. Validate that map-switch state is logged.

## 4) Boost integration with Arduino electronic wastegate control

1. Keep MS3Pro boost target ceilings conservative to act as ECU-side safety envelope.
2. Allow Arduino to execute real-time electronic actuator positioning and derates.
3. Ensure MAP, TPS, RPM, gear, knock, and thermal channels are available over CAN for Arduino decisions.

## 5) Launch control

1. Configure launch/2-step in MS3Pro (arming input + rpm target by mode as needed).
2. Keep launch spark retard and fuel cut conservative during first tests.
3. Verify transitions in logs (armed, active, released).

## 6) CAN integration

1. Verify IDs match the project CAN contract.
2. Confirm periodic publish rates for ECU sensor frames are stable.
3. Validate that Pi/Arduino commands are visible and correctly decoded.

## 7) Limp mode behavior (critical)

When limp is asserted by Pi (and enforced by Arduino), ensure MS3Pro is configured to cooperate with:

- reduced boost ceiling / no-boost request behavior
- safe ignition table selection
- disabled flame strategy
- continued drivability for return-home conditions

## 8) Validation checklist

1. Engine idles and free-revs with no sync loss.
2. CAN drop test: Arduino enters protective behavior safely.
3. Knock/thermal test: derates occur without oscillation.
4. Limp command test: boost drops, safe timing map selected, flame disabled.
5. Air Shot test: only triggers under valid conditions and respects latching/rearm.

## Notes and constraints

- TunerStudio is primarily calibration/configuration tooling; real-time actuator safety should remain on Arduino + ECU firmware.
- Keep all safety-critical overrides deterministic and testable without the Pi present.

## Traction-control implementation note

MS3 already has native traction-control provisions (wheel-speed and external slip-based strategies).
Recommended approach for this project:

1. Keep Arduino as the aggressiveness/slip pre-processor and profile selector.
2. Feed slip/torque-reduction intent to MS3 and let MS3 perform ignition/fuel/torque cuts using native strategies.
3. Validate cut authority in logs before road use.

If direct external throttle-cut over CAN is not available in your exact firmware build, use MS3 native traction-control inputs/tables as the authoritative cut mechanism and keep Arduino CAN outputs as the supervisory request path.
