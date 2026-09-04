# Albatross thermal subsystem

The dedicated `THERMAL_NODE` is a second Teensy 4.1. It acquires and validates 32 configured channels, performs sensor conversion and fast per-channel IIR filtering, propagates hardware faults, and broadcasts a versioned binary CAN protocol. The Pi owns derived metrics, condition-relative models, exposure logs, and the HUD. The existing controller and MS3 keep safety authority.

## Hardware boundary

- CAN remains 500 kbit/s, 11-bit identifiers, through a 3.3 V automotive CAN transceiver. Terminate only at the two physical bus ends.
- Four K-type probes use four MAX31856-class cold-junction-compensated front ends. Never wire a thermocouple to a Teensy ADC. Use K extension wire and connectors through the cold-junction point.
- Two ADS7953 16-channel SPI ADCs provide 32 analog inputs. Each installed circuit requires the calibration network named in `config/thermal_system.json`, a stable reference/excitation supply, RC filtering, series/current limiting, ESD and load-dump/transient protection, and a low-noise sensor return.
- PT1000 channels assume a precision 500 µA excitation circuit. NTC channels use the profile-specific precision pull-up. The firmware constants are initial engineering values and must be calibrated against the actual selected probes and conditioning PCB.
- Keep thermocouple and analog harnesses separated from ignition, injectors, starter/stator wiring, DBW, wastegate actuators, WMI pump, Air Shot solenoids, and other switched-current wiring.
- `AMBIENT_AIR` must be shielded from radiator discharge, exhaust radiation, sunlight, and heated bodywork.

## Safety ownership

Primary coolant, MAT/IAT, and any ECU-required EGT remain directly available to MS3/main control. The Pi is never in the protection chain. The main Teensy consumes valid supplemental thermal values directly and enters an explicit degraded state when the thermal heartbeat is absent: boost is capped at 8 psi, CAN-level flame intent and Air Shot are inhibited, while independent WMI and ECU protections remain available. Flame implementation remains intentionally provisional and has no dedicated Teensy output pin. A valid supplemental critical temperature requests the existing thermal limp path. Invalid channels never become `0°C`.

Before vehicle use, review thresholds with the engine builder/tuner, prove every failure mode on a bench, validate CAN loading, and verify that disconnecting the Pi does not remove overtemperature protection.

## Pi architecture

`albatross_pi/thermal/service.py` is the single live model. SocketCAN, simulation, and JSONL replay all feed this model. It owns timestamps, stale/offline behavior, component-specific ABS normalization, ambient deltas, left/right and stage deltas, intercooler effectiveness, diagnostic compressor-efficiency estimates, filtered derivatives, persistent/hysteretic alerts, and protected condition bins.

Baseline learning starts disabled. It must be deliberately authorized only during known-healthy commissioning. Factory, long-term, and recent dictionaries remain separate so degradation cannot silently redefine the only good baseline.

The HUD adds TEMPS to the existing focus/navigation abstraction. Focusing it exposes Overview, Thermal Map, Thermal Δ / DEV, Intake / Turbos, Engine / Cooling, Oil System, Sensor Status, and History / Logs. ABS answers “what is hot”; DEV answers “what is behaving unusually.”

## Commissioning sequence

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
py -3.12 tools/check_thermal_config.py
py -3.12 main.py --simulator --thermal-scenario full_boost_pull
```

Thermal logs are written independently of the selected page under `logs/thermal`. Every record carries the configuration version and vehicle-state context.
