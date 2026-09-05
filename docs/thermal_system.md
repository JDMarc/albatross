# Albatross thermal subsystem

The dedicated `THERMAL_NODE` is a second Teensy 4.1. It acquires and validates 32 configured channels, performs sensor conversion and fast per-channel IIR filtering, propagates hardware faults, and broadcasts a versioned binary CAN protocol. The Pi owns derived metrics, condition-relative models, exposure logs, and the HUD. The existing controller and MS3 keep safety authority.

## Hardware boundary

The complete [thermal Teensy pin map and 32-channel connector assignment](../arduino/README.md#dedicated-thermal-teensy-pin-map)
are maintained in the firmware README. This is a physically separate board:
SPI 11/12/13, MAX31856 CS 10/9/8/7, ADS7953 CS 6/5, CAN1 RX/TX 22/23.
The current configuration enables 29 of the 32 stable sensor IDs; three are reserved.

- CAN remains 500 kbit/s, 11-bit identifiers, through a 3.3 V automotive CAN transceiver. Terminate only at the two physical bus ends.
- Four K-type probes use four MAX31856-class cold-junction-compensated front ends. Never wire a thermocouple to a Teensy ADC. Use K extension wire and connectors through the cold-junction point.
- Two ADS7953 16-channel SPI ADCs provide 32 analog inputs. Each installed circuit requires the calibration network named in `config/thermal_system.json`, a stable reference/excitation supply, RC filtering, series/current limiting, ESD and load-dump/transient protection, and a low-noise sensor return.
- PT1000 channels assume a precision 500 µA excitation circuit. NTC channels use the profile-specific precision pull-up. The firmware constants are initial engineering values and must be calibrated against the actual selected probes and conditioning PCB.
- Keep thermocouple and analog harnesses separated from ignition, injectors, starter/stator wiring, DBW, wastegate actuators, WMI pump, Air Shot solenoids, and other switched-current wiring.
- `AMBIENT_AIR` must be shielded from radiator discharge, exhaust radiation, sunlight, and heated bodywork.

## Safety ownership

The dedicated thermal Teensy is now the primary temperature source for the HUD and main controller. HUD coolant is the hotter head-coolant channel, oil is OIL_GALLERY, intake is PLENUM_IAT, and EGT is the hotter exhaust bank. Both bank values must be valid for a paired summary; unavailable summaries display `--`, never a fabricated temperature. Air Shot warmup uses the colder head-coolant channel.

The Pi is never in the protection chain. The main Teensy checks heartbeat, value and status freshness independently. Missing channels inhibit Air Shot and advanced thermal-dependent capabilities. Remaining head coolant and fresh independent ECU CLT/IAT/oil retain basic coverage; loss of that basic coverage requests the existing thermal limp path. One auxiliary EGT failure alone does not remove throttle authority. The existing 8 psi thermal-degraded ceiling is not permission to make boost when other protections demand less. Actual overtemperature retains the existing hard response; staged recovery needs engineering calibration. See [fault management](fault_management.md). No new thermal thresholds were introduced. Flame architecture remains provisional with no dedicated output pin.

ECU wiring currently retains dedicated coolant, IAT and oil-temperature sensors. Replacement with thermal-node CAN data is preferred where supported, but is not enabled in this update: generic CAN oil-temperature reception and replacement of the primary fueling MAT input are different capabilities. See [ECU receiving boundary](ms3_tunerstudio_setup.md#thermal-node-input-replacement). Do not remove ECU sensors based only on a working HUD or TunerStudio gauge.

Before vehicle use, review thresholds with the engine builder/tuner, prove every failure mode on a bench, validate CAN loading, and verify that disconnecting the Pi does not remove overtemperature protection.

## Pi architecture

See the [thermal error catalogue and Ignore Error controls](thermal_alerts.md)
for main-HUD warning conditions, audio mapping, clearing and recurrence behavior.

`albatross_pi/thermal/service.py` is the single live model. SocketCAN, simulation, and JSONL replay all feed this model. It owns timestamps, stale/offline behavior, component-specific ABS normalization, ambient deltas, left/right and stage deltas, intercooler effectiveness, diagnostic compressor-efficiency estimates, filtered derivatives, persistent/hysteretic alerts, and protected condition bins.

Baseline learning starts disabled. It must be deliberately authorized only during known-healthy commissioning. Factory, long-term, and recent dictionaries remain separate so degradation cannot silently redefine the only good baseline.

Select the System Vitals window to open TEMPS. ECO/NORMAL use a compact TEMP tile beside Air Shot instead; its label changes color with thermal condition and its subtext reports the operating/fault state. Merely hovering never opens the menu. Up/down in the menu chooses Overview, Thermal Map, Thermal Δ / DEV, Intake / Turbos, Engine / Cooling, Oil System, Sensor Status, or History / Logs; Select opens the page. ABS answers “what is hot”; DEV answers “what is behaving unusually.”

Heat maps display all 29 active sensors on a functional overhead schematic of the twin-turbo transverse V-twin: a forward radiator, mirrored intercoolers and compressor/turbine housings, shared pre/post-WMI and plenum, separate runners and projecting cylinder banks, central crankcase, oil cooler and turbo oil drains. Charge-air/exhaust arrows show direction; coolant and oil connections are schematic, not a fabrication drawing or a specified pump/thermostat installation. Cylinder/scroll outlines and sensor callouts use measured thermal colors, with unavailable readings gray. Turbo drain temperatures are fluid temperatures, not the disabled CHRA housing sensors.

While either heat map is open, animated arrows travel along the charge-air, exhaust and turbo-drain paths. Both rotor drawings on each turbo share a smoothly changing phase: more bank boost means faster visual rotation; missing bank pressure falls back to common boost. Invalid common pressure uses the slow idle visual speed. Motion is a presentation-only **boost proxy, not measured shaft RPM or proof of fluid flow**; that explanation stays in documentation rather than on the HUD. Presentation constants are bounded separately from engineering calibrations, and animation does not issue commands or alter thermal alerts. Coolant paths remain unarrowed because exact circulation plumbing is unspecified.

The map uses a restrained avionics treatment: a chamfered bezel, subtle background raster with a slow CRT sweep, edge graduations and steady corner brackets on the selected sensor. The sweep stays behind components and sensor text, and data and alert colors retain their meaning. Cylinder fins are derived from the same bank polygons as the castings, inset within each bank and mirrored together; `tests/run_thermal_geometry_checks.py` guards their alignment.

Backgrounds, raster/sweep, grid, neutral mechanical details, labels and focus brackets follow the selected AMBER, NIGHT, NIGHT OPS or HIGH-CON theme. Diagnostic heat colors, gray unavailable readings and the four fluid-path colors remain fixed. Theme changes do not reset sensor selection or animation. `tests/run_thermal_theme_checks.py` verifies the rendered colors across all four themes, both map modes and both supported display sizes.

All four D-pad directions select a visible neighbor, preferring nearby aligned sensors and stopping at the edge. Navigation and rendering share the same sensor coordinates. The selected sensor remains selected when switching ABS/DEV pages. Select or Back returns to the TEMPS menu; Back from that menu returns to the vitals/TEMP tile. Tests in `tests/run_thermal_navigation_checks.py` cover menu entry, all five drive modes, complete sensor reachability, non-overlapping callout geometry at 1280×480 and 1920×720, and animation bounds, fallback and timing.

## Commissioning sequence

Synthetic 1280×480 architecture preview (sample temperatures; indicative component placement):

![Twin-turbo transverse V-twin thermal schematic](assets/thermal-architecture.png)

1. Run `py -3.12 tools/check_thermal_config.py` and resolve all drift.
2. Power the acquisition PCB without probes. Confirm every installed channel reports an explicit open/front-end fault.
3. Apply known resistances and thermocouple simulator points at cold, operating, warning, and critical temperatures. Record calibration residuals.
4. Confirm channel IDs and physical labels one connector at a time.
5. Confirm heartbeat loss produces `THERMAL NODE OFFLINE`, unavailable values, the main-controller degraded cap, and no fabricated temperatures.
6. Exercise every built-in simulator scenario before first engine operation.
7. Keep baseline learning disabled until the tuner explicitly marks operating regions healthy.

## Development commands

```text
py -3.12 tests/run_thermal_checks.py
py -3.12 tests/run_thermal_navigation_checks.py
py -3.12 tests/run_thermal_theme_checks.py
py -3.12 tools/check_thermal_config.py
py -3.12 main.py --simulator --thermal-scenario full_boost_pull
```

Optional offline animation preview (requires Pygame and Pillow, opens no CAN/network connection): `py -3.12 tools/render_thermal_motion.py thermal-motion.gif`. Add `--theme "NIGHT OPS"` to choose a theme or `--cycle-themes` to preview all four. The synthetic 0–20 psi sweep demonstrates visual spool-up/down only; it is not calibration or test evidence for the motorcycle.

Thermal logs are written independently of the selected page under `logs/thermal`. Every record carries the configuration version and vehicle-state context.
