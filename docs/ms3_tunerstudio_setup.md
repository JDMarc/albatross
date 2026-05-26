# MS3Pro + TunerStudio Setup Guide for The Albatross

## Short answer: can TunerStudio / MS3Pro do this?

Yes. The MS3Pro firmware and TunerStudio workflow support the core ECU-side features this project needs, including:

- table switching and alternate maps
- launch control / 2-step behaviors
- boost control strategies (open-loop and closed-loop with table-based targets)
- CAN messaging to cooperate with external controllers

This means we can keep the architecture: **Pi plans + supervises, Teensy performs fast actuator control, MS3Pro manages core fueling/ignition/engine safeguards**.

TunerStudio MS Lite is sufficient for ECU setup, CAN parameters, sensor calibration, table switching, and the MS3 CAN broadcast/receive menus. It is not the runtime bridge for Albatross-specific CAN; it configures the MS3Pro Mini, then the Pi/Teensy handle live traffic.

## Recommended control split (final)

- **Pi**: mode selection UX, weather/profile logic, requests (`boost target`, `flame request`, `limp request`), HUD.
- **Teensy 4.1**: electronic wastegate actuator command, Air Shot compressor + shot latch logic, wheel speed, WMI tank/flow/status sensing, WMI/flame interlocks, failsafe execution.
- **MS3Pro Mini**: fueling, ignition, MAP/RPM/TPS/CLT/IAT/wideband, oil pressure, oil temperature, flex fuel, injector pulse width/duty telemetry, safe map selection, launch/2-step, hard engine protections.

Current build wiring assumption:

- Oil pressure: wired to MS3Pro Mini analog input and published to HUD/CAN by MS3-side telemetry.
- Oil temperature: wired to MS3Pro Mini sensor input and published to HUD/CAN by MS3-side telemetry.
- Flex fuel: wired to MS3Pro Mini flex input; HUD consumes ethanol percentage as ECU flex telemetry. Flex content verifies/derates the E85 boost strategy, but it does not upgrade an 87/91/93 manual selection into E85 boost by itself.
- Wheel speed: handled by Teensy hall inputs and published on controller HUD wheel-speed frames.
- WMI tank, flow, and status: handled by Teensy and published on controller WMI status frames.
- Teensy oil pressure remains a fallback provision only if the MS3 oil pressure path is unavailable during bench testing.

## Required MS3Pro configuration steps

## 1) Firmware + project baseline

1. Load a stable MS3Pro firmware build supported by your hardware.
2. Create a fresh TunerStudio project for that exact firmware signature.
3. Confirm all critical sensors are calibrated (TPS, MAP, CLT, IAT, wideband, oil pressure, oil temperature, flex fuel).

## 2) Ignition and fueling safety baseline

1. Configure conservative base spark and VE maps for first-fire.
2. Configure fuel-specific VE/AFR/stoich behavior for the fuels in the Pi fuel profile frame (`0x150`). Current table indexes are 0=pump gas, 1=100 octane, 2=E85, and 3=C16. With the flex sensor wired to MS3, let MS3 own real fuel composition correction; the Pi uses ethanol percentage only for supervisory boost-cap derating/validation.
3. Configure Spark Table 1/2 as the initial/conservative strategy and Spark Table 3/4 or the configured switched strategy as the SPORT+ performance spark map. The Pi sends `0x151` with 0 for ECO/NORMAL and 1 for SPORT/RACE/ALBATROSS.
4. Configure rev limiter cut strategy switching for flame mode if your MS3 firmware/settings allow it. The Pi sends `0x152` with 0=fuel cut and 1=ignition/spark cut; RACE/ALBATROSS force the ignition-cut request, and the HUD flame setting can request it in other modes.
5. Do not treat wasted-spark/COP/coil-count ignition mode as a live CAN toggle. MS3/TunerStudio exposes it as a core ignition setup item under Number Of Coils/Spark Output; configure and validate it before runtime rather than switching it while running.
6. Enable over-temp and AFR protection strategies available in your firmware.
7. Set hard rev limit and soft rev limit with predictable cut behavior.

## 3) Dual map / table switching for safe timing map

1. Enable table/map switching input strategy in TunerStudio.
2. Reserve a low-risk timing/boost-capable “safe” map.
3. Wire or map a software-switchable input/CAN path that Teensy/Pi can command indirectly.
4. Validate that map-switch state is logged.

## 4) Boost integration with Teensy electronic wastegate control

1. Keep MS3Pro boost target ceilings conservative to act as ECU-side safety envelope.
2. Allow Teensy to execute real-time electronic actuator positioning and derates.
3. Ensure MAP, TPS, RPM, gear, knock, oil pressure, oil temperature, CLT, IAT, EGT, battery voltage, flex content, and injector pulse width/duty are available to the HUD/Pi over CAN. Teensy should not be the source of truth for oil pressure/temp on this build.

## 5) Launch control

1. Configure launch/2-step in MS3Pro (arming input + rpm target by mode as needed).
2. Keep launch spark retard and fuel cut conservative during first tests.
3. Verify transitions in logs (armed, active, released).

## 6) CAN integration

1. Enable CAN master/global CAN in `CAN bus / Testmodes > CAN Parameters`, set the baud rate to match the bus (`500k` unless we deliberately change the Teensy sketch), burn, and power cycle.
2. Enable MS3 CAN broadcast output for the engine data the Pi needs. TunerStudio's built-in broadcasts use standard 11-bit IDs and predefined layouts, so the Pi decoder should either consume MS3's native broadcast format directly or use a small translator. Do not rely on TunerStudio Lite to emit arbitrary Albatross `0x100`-style frames at runtime.
3. For the current Albatross canonical telemetry map, reserve ECU/HUD IDs `0x100`-`0x10F`; `0x10D` is flex fuel ethanol percentage, byte 0 = ethanol content percent. `0x10E` is injector status: bytes 0-1 = injector pulse width in milliseconds x100, bytes 2-3 = injector duty percent x10. Duty may be 0 if the Pi should derive it from pulse width and RPM. `0x10F` is optional split boost pressure: bytes 0-1 left boost psi x10, bytes 2-3 right boost psi x10.
4. Keep controller status ownership on `0x130`-`0x13E`, including wheel speed (`0x137`) and WMI status (`0x139`).
5. Reserve Pi-to-ECU command `0x152` for rev limiter strategy selection: byte 0 = 0 fuel cut, 1 ignition/spark cut. Map this only after confirming the MS3 firmware can safely expose that strategy switch through CAN or a CAN-driven generic input.
6. Confirm periodic publish rates are stable before enabling safety logic: 20-50 Hz is enough for HUD/oil/flex data; wheel speed and WMI can remain Teensy-side at the sketch's 20 Hz status cadence until road testing proves a need for more.
7. Validate with `candump` or TunerStudio's CAN test tools that Pi/Teensy commands are visible and correctly decoded.

## 7) Limp mode behavior (critical)

When limp is asserted by Pi (and enforced by Teensy), ensure MS3Pro is configured to cooperate with:

- reduced boost ceiling / no-boost request behavior
- safe ignition table selection
- disabled flame strategy
- continued drivability for return-home conditions

Current Albatross CAN behavior:

- Pi-to-controller limp command `0x123`: byte 0 = 0/1 active, byte 1 = reason code.
- Controller-to-HUD limp status `0x147`: byte 0 = 0/1 active, byte 1 = reason code.
- Reason codes: `0x00 NONE`, `0x01 PI REQUEST`, `0x02 ENGINE RUN OFF`, `0x03 ECU CAN STALE`, `0x04 PI COMMAND STALE`, `0x05 THERMAL`, `0x06 LOW OIL PRESS`, `0x07 BATTERY VOLTAGE`, `0x08 KNOCK`, `0x09 ECU SENSOR`, `0x0A NFC AUTH`, `0x0B SAFETY SUPERVISOR`, `0x0C OVERBOOST`, `0x0D WMI FAULT`, `0x0E CLUTCH SLIP`.

MS3-side limp actions to configure and validate:

1. Boost: map limp to the lowest boost target / wastegate-safe behavior available in the tune. Teensy already drives wastegates to no-boost, but MS3 should also have a conservative boost ceiling so either controller alone fails safer.
2. Spark: switch to the conservative ignition map when limp is active. SPORT+ performance timing should be disabled.
3. Fuel: keep the correct fuel table/stoich profile for the selected fuel, but use richer high-load/thermal protection where appropriate. Limp should not accidentally switch E85/C16 lambda assumptions back to pump-gas assumptions.
4. Rev limit: force normal fuel-cut rev limiting while limp is active; ignition-cut/flame behavior should be disabled.
5. Torque reduction: accept controller torque-cut/slip request frames (`0x12A`/`0x12B`) or the equivalent mapped inputs so traction, wheel-speed faults, and limp can reduce engine torque without relying only on boost.
6. Knock/thermal protection: enable MS3 engine-protection/fault-mode strategies for knock, CLT/IAT/oil/EGT-related limits where your firmware exposes them.
7. Engine run cut: map the Albatross engine-run switch strategy to a deterministic ECU-side kill path for true shutdown requests. This should be reserved for critical/stationary-safe cases, not ordinary return-home limp.
8. Datalogging: log limp input/status, table-switch state, boost target, rev limiter strategy, torque cut, knock, oil pressure, CLT/IAT, EGT, and battery voltage for every validation run.

## 8) Validation checklist

1. Engine idles and free-revs with no sync loss.
2. CAN drop test: Teensy enters protective behavior safely.
3. Knock/thermal test: derates occur without oscillation.
4. Limp command test: boost drops, safe timing map selected, flame disabled.
5. Air Shot test: only triggers under valid conditions and respects latching/rearm.

## Notes and constraints

- TunerStudio is primarily calibration/configuration tooling; real-time actuator safety should remain on Teensy + ECU firmware.
- Keep all safety-critical overrides deterministic and testable without the Pi present.

## Traction-control implementation note

MS3 already has native traction-control provisions (wheel-speed and external slip-based strategies).
Recommended approach for this project:

1. Keep Teensy as the wheel-speed/slip pre-processor and profile selector.
2. Feed slip/torque-reduction intent to MS3 and let MS3 perform ignition/fuel/torque cuts using native strategies. Teensy publishes torque cut on `0x12A` and external slip on `0x12B`.
3. Validate cut authority in logs before road use.

If direct external throttle-cut over CAN is not available in your exact firmware build, use MS3 native traction-control inputs/tables as the authoritative cut mechanism and keep Teensy CAN outputs as the supervisory request path.
