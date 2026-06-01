# Roadgoing Motorcycle Readiness Checklist

This is the gap list for turning the Albatross electronics from a bench/project
system into something appropriate for a street motorcycle. It is an engineering
checklist, not a legal certification. Final requirements depend on registration
state, inspection rules, insurance, and whether the bike is treated as a
modified production motorcycle, reconstructed vehicle, or custom build.

## Current Architecture

- Pi: HUD, settings, logging, update flow, boost target planning, fuel/spark
  profile requests.
- Teensy controller: actual boost controller, WMI pump command, Air Shot, compressor relay,
  wheel speed, traction slip calculation, light status sensing, and limp
  enforcement.
- MS3Pro Mini: core engine control, fueling, ignition, hard engine protections,
  oil pressure, oil temperature, flex fuel, and engine telemetry.

The Teensy controller is not connected to an external boost controller. It is the boost
controller. The wastegate outputs must feed actuator power stages/H-bridges
suited to the wastegate actuator current.

## Must-Have Before Road Use

| Area | Status | Gap / requirement |
| --- | --- | --- |
| Legal lighting | Partial | Headlight high/low, tail, brake, plate lamp, reflectors, indicators if required, and visible high-beam/indicator telltales must be verified with local rules. |
| Brake system | External | Front/rear brakes, brake switches, hydraulic condition, brake light activation, and inspection compliance are outside the code but mandatory. |
| Kill switch / run switch | Partial | Pi sends engine-run state and Teensy requests torque cut/no boost, but the bike still needs a hardwired ignition/fuel/ECU kill path independent of software. |
| Fusing and power distribution | Missing in code | Every branch needs fuse sizing, relay strategy, wire gauge, and serviceable connectors documented. |
| Load dump/transient protection | Hardware provision documented | Pi, Teensy, CAN modules, and sensor inputs still need selected automotive power protection, reverse polarity protection, and brownout validation. See `docs/power_nfc_watchdogs.md`. |
| Weather/vibration | Hardware | Enclosures, strain relief, sealed connectors, conformal coating where appropriate, and vibration mounts need to be selected. |
| Watchdog/fail-silent behavior | Partial | Teensy hardware watchdog, source-specific CAN stale behavior, and Pi render-loop systemd watchdog are implemented. Bench fault-injection and powered-actuator validation are still required. |
| Boost actuator power stage | Required | Teensy logic pins must feed a current-rated H-bridge/driver. Add position feedback if the chosen wastegate actuator supports it. |
| Mechanical boost failsafe | Required | Wastegate should fail to spring/base boost or no boost on power loss, blown fuse, Teensy reset, CAN loss, or driver fault. |
| MS3 hard limits | Required | MS3 must enforce boost/fuel/ignition/overboost/AFR/oil/temperature safeties even if Pi or Teensy misbehaves. |
| Sensor calibration | Required | Wheel circumference, magnet count, gear ratios, WMI flow pulses/L, tank sender scaling, oil/flex/fuel sensors, and boost/MAP scaling need measured calibration. |
| Logging and recovery | Partial | Fault JSONL, readable summaries, USB export, and readable 30-second pre-fault timelines exist. Define the post-ride review workflow before relying on logs for diagnosis. |
| Updates | Partial | USB/GitHub bundle flow and automatic application-overlay rollback exist. Verify rollback and "engine off, voltage OK" installs on the actual Pi. |
| EMI/grounding | Hardware | CAN twisted pair, shield strategy, star/sensor grounds, ignitor/injector noise separation, and alternator noise testing need validation. |
| Human factors | Partial | HUD has indicator/high-beam icons and fault voice lines; verify sunlight readability, glove controls, startup time, and no critical text overlap on the real display. |
| Battery/charging health | Partial | Voltage faults and low-voltage controlled Pi shutdown exist; add current draw budget, parasitic draw target, alternator capacity check, and external hold-up/latch validation. |
| Road-test plan | Missing | Add staged tests: powered bench, spinning-wheel bench, no-boost ride, spring/base-boost ride, low-boost ride, WMI-disabled ride, CAN-fault injection, thermal soak. |

## Highest-Priority Engineering Additions

1. Add a hardware kill path that does not depend on Pi, Teensy, CAN, or Python.
2. Add or confirm mechanical boost fail-safe behavior with the wastegate actuator
   and driver powered off.
3. Bench-validate the Teensy watchdog reset and Pi systemd render-loop watchdog path.
4. Bench-test Teensy CAN stale timeout behavior with the wastegate actuator
   driver powered, confirming zero boost, no Air Shot, no flame, and stable HUD
   reporting when Pi or ECU frames stop.
5. Add actual actuator position feedback or driver fault feedback if the
   electronic wastegate actuator hardware supports it.
6. Replace placeholder gear-ratio constants with measured road/stand data.
7. Verify every 12 V input uses automotive-safe conditioning before connecting
   the motorcycle harness.

## Street Equipment To Confirm

- DOT/legal headlight assembly, low beam, high beam, and high-beam indicator.
- Tail lamp, stop lamp, license plate lamp, rear reflector.
- Turn indicators and telltale behavior as required by the bike year/state.
- Horn.
- Mirrors.
- Front and rear brakes and brake-light switches.
- Tires, rims, chain/driveline guards, and speedometer/odometer requirements.
- Secure battery, fuel system routing, overflow/vent routing, and exhaust heat
  shielding.
- VIN/title/inspection requirements for the final configuration.
