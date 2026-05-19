# MS3Pro + TunerStudio Setup Guide for The Albatross

## Short answer: can TunerStudio / MS3Pro do this?

Yes. The MS3Pro firmware and TunerStudio workflow support the core ECU-side features this project needs, including:

- table switching and alternate maps
- launch control / 2-step behaviors
- boost control strategies (open-loop and closed-loop with table-based targets)
- CAN messaging to cooperate with external controllers

This means we can keep the architecture: **Pi plans + supervises, Arduino performs fast actuator control, MS3Pro manages core fueling/ignition/engine safeguards**.

TunerStudio MS Lite is sufficient for ECU setup, CAN parameters, sensor calibration, table switching, and the MS3 CAN broadcast/receive menus. It is not the runtime bridge for Albatross-specific CAN; it configures the MS3Pro Mini, then the Pi/Arduino handle live traffic.

## Recommended control split (final)

- **Pi**: mode selection UX, weather/profile logic, requests (`boost target`, `flame request`, `limp request`), HUD.
- **Arduino**: electronic wastegate actuator command, Air Shot compressor + shot latch logic, wheel speed, WMI tank/flow/status sensing, WMI/flame interlocks, failsafe execution.
- **MS3Pro Mini**: fueling, ignition, MAP/RPM/TPS/CLT/IAT/wideband, oil pressure, oil temperature, flex fuel, injector pulse width/duty telemetry, safe map selection, launch/2-step, hard engine protections.

Current build wiring assumption:

- Oil pressure: wired to MS3Pro Mini analog input and published to HUD/CAN by MS3-side telemetry.
- Oil temperature: wired to MS3Pro Mini sensor input and published to HUD/CAN by MS3-side telemetry.
- Flex fuel: wired to MS3Pro Mini flex input; HUD consumes ethanol percentage as ECU flex telemetry. Flex content verifies/derates the E85 boost strategy, but it does not upgrade an 87/91/93 manual selection into E85 boost by itself.
- Wheel speed: handled by Arduino hall inputs and published on Arduino HUD wheel-speed frames.
- WMI tank, flow, and status: handled by Arduino and published on Arduino WMI status frames.
- Arduino oil pressure remains a fallback provision only if the MS3 oil pressure path is unavailable during bench testing.

## Required MS3Pro configuration steps

## 1) Firmware + project baseline

1. Load a stable MS3Pro firmware build supported by your hardware.
2. Create a fresh TunerStudio project for that exact firmware signature.
3. Confirm all critical sensors are calibrated (TPS, MAP, CLT, IAT, wideband, oil pressure, oil temperature, flex fuel).

## 2) Ignition and fueling safety baseline

1. Configure conservative base spark and VE maps for first-fire.
2. Configure fuel-specific VE/AFR/stoich behavior for the fuels in the Pi fuel profile frame (`0x150`). Current table indexes are 0=pump gas, 1=100 octane, 2=E85, and 3=C16. With the flex sensor wired to MS3, let MS3 own real fuel composition correction; the Pi uses ethanol percentage only for supervisory boost-cap derating/validation.
3. Configure Spark Table 1/2 as the initial/conservative strategy and Spark Table 3/4 or the configured switched strategy as the SPORT+ performance spark map. The Pi sends `0x151` with 0 for ECO/NORMAL and 1 for SPORT/RACE/ALBATROSS.
4. Enable over-temp and AFR protection strategies available in your firmware.
5. Set hard rev limit and soft rev limit with predictable cut behavior.

## 3) Dual map / table switching for safe timing map

1. Enable table/map switching input strategy in TunerStudio.
2. Reserve a low-risk timing/boost-capable “safe” map.
3. Wire or map a software-switchable input/CAN path that Arduino/Pi can command indirectly.
4. Validate that map-switch state is logged.

## 4) Boost integration with Arduino electronic wastegate control

1. Keep MS3Pro boost target ceilings conservative to act as ECU-side safety envelope.
2. Allow Arduino to execute real-time electronic actuator positioning and derates.
3. Ensure MAP, TPS, RPM, gear, knock, oil pressure, oil temperature, CLT, IAT, EGT, battery voltage, flex content, and injector pulse width/duty are available to the HUD/Pi over CAN. Arduino should not be the source of truth for oil pressure/temp on this build.

## 5) Launch control

1. Configure launch/2-step in MS3Pro (arming input + rpm target by mode as needed).
2. Keep launch spark retard and fuel cut conservative during first tests.
3. Verify transitions in logs (armed, active, released).

## 6) CAN integration

1. Enable CAN master/global CAN in `CAN bus / Testmodes > CAN Parameters`, set the baud rate to match the bus (`500k` unless we deliberately change the Arduino sketch), burn, and power cycle.
2. Enable MS3 CAN broadcast output for the engine data the Pi needs. TunerStudio's built-in broadcasts use standard 11-bit IDs and predefined layouts, so the Pi decoder should either consume MS3's native broadcast format directly or use a small translator. Do not rely on TunerStudio Lite to emit arbitrary Albatross `0x100`-style frames at runtime.
3. For the current Albatross canonical telemetry map, reserve ECU/HUD IDs `0x100`-`0x10E`; `0x10D` is flex fuel ethanol percentage, byte 0 = ethanol content percent. `0x10E` is injector status: bytes 0-1 = injector pulse width in milliseconds x100, bytes 2-3 = injector duty percent x10. Duty may be 0 if the Pi should derive it from pulse width and RPM.
4. Keep Arduino status ownership on `0x130`-`0x13E`, including wheel speed (`0x137`) and WMI status (`0x139`).
5. Confirm periodic publish rates are stable before enabling safety logic: 20-50 Hz is enough for HUD/oil/flex data; wheel speed and WMI can remain Arduino-side at the sketch's 20 Hz status cadence until road testing proves a need for more.
6. Validate with `candump` or TunerStudio's CAN test tools that Pi/Arduino commands are visible and correctly decoded.

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

1. Keep Arduino as the wheel-speed/slip pre-processor and profile selector.
2. Feed slip/torque-reduction intent to MS3 and let MS3 perform ignition/fuel/torque cuts using native strategies. Arduino publishes torque cut on `0x12A` and external slip on `0x12B`.
3. Validate cut authority in logs before road use.

If direct external throttle-cut over CAN is not available in your exact firmware build, use MS3 native traction-control inputs/tables as the authoritative cut mechanism and keep Arduino CAN outputs as the supervisory request path.
