# Albatross firmware: two Teensy 4.1 boards

Harness reference: [wiring and pinouts](../docs/wiring_pinout.md).
Network reference: [complete CAN ID table](../docs/can_id_reference.md),
including standard frames, DBWX2 extended polling and unimplemented interfaces.

The current architecture uses **two separate Teensy 4.1 boards**, each with its
own firmware and external 3.3 V CAN transceiver on the shared 500 kbit/s bus.
Pin numbers below are local to the named board; the same number on the other
Teensy is a different electrical connection.

| Board | Sketch directory under this directory | Responsibility |
| --- | --- | --- |
| Main controller | `teensy41/albatross_controller_teensy41/` | Wastegates, WMI, four-valve Air Shot V2, wheel speeds, unified DBW/TCS/AWC supervision |
| Thermal node | `teensy41/albatross_thermal_node/` | Thermocouple/analog acquisition, conversion, validation, filtering and thermal CAN |
| Legacy Mega 2560 | `legacy/mega2560/albatross_controller/` | Historical Mega/MCP2515 reference; does not implement the current stack |

The Raspberry Pi owns the HUD, USB grip controls, settings, thermal analytics,
logging and weather context. MS3Pro Mini owns engine management. DBWX2 owns
the throttle motor servo and redundant APS/TPS checking. RaceGrade supplies
six-axis inertial CAN measurements. The main Teensy combines chassis and wheel
evidence: rear-wheel slip drives TCS; chassis pitch drives AWC. Wheel-speed
difference alone is not a throttle-cut criterion.

## Main Teensy pin map

Temperature protection uses the dedicated thermal node's CAN measurements,
with fresh independent ECU coolant/IAT/oil retained for basic fallback coverage.
Individual auxiliary losses restrict advanced features; loss of basic thermal
coverage retains thermal limp. Heartbeat, value and status freshness are checked
independently. The ECU retains its own sensors pending verified ECU receiving setup.
This migration adds no main-controller temperature pins. See
[`thermal_system.md`](../docs/thermal_system.md) for the channel/source policy.

Source: `albatross_controller_teensy41.ino` and `airshot_io.cpp`.

| Pin | Direction | Function / connection |
| --- | --- | --- |
| 22 | CAN TX | CAN1 TX to transceiver TXD |
| 23 | CAN RX | CAN1 RX to transceiver RXD |
| 2 / 3 / 4 | Outputs | Wastegate 1 PWM / direction / enable to power driver |
| 5 / 6 / 9 | Outputs | Wastegate 2 PWM / direction / enable to power driver |
| 10 | PWM output | WMI pump driver, active high |
| 11 | Unassigned | No dedicated flame-mode pin; flame intent remains on CAN |
| 12 | Master air isolation | Reserved active-high driver for optional NC master valve; defaults LOW/unconfigured. Cannot be assigned to a performance valve |
| 24 | Output | Compressor relay/MOSFET command |
| 18 / 19 | Pull-up inputs | Front / rear wheel Hall pulses |
| 20 | Pull-up input | WMI flow pulses |
| 25 | Pull-up input | Neutral switch, active low |
| 26 / 27 | Inputs | Left / right indicator sense |
| 28 / 29 / 30 | Inputs | High beam / brake / stock oil-warning sense |
| 31 | Pull-up input | WMI pressure/status OK, active low |
| A0 (14) | Analog input | Fallback oil-pressure sender |
| A1 (15) | Analog input | WMI tank level |
| A2 (16) | Analog input | Air Shot tank pressure |
| Four configurable PWM pins | Outputs | Intake L/R and turbine L/R valve drivers; assignments are unset in the shipped calibration |
| Optional FIRE/service pins | Inputs | Default -1 (not wired); normal FIRE and mode selection use USB grip controls through the Pi |

The valve validator rejects reserved or duplicate pins, non-PWM outputs and
incompatible shared-timer frequencies. Do not infer a final valve harness from
unused GPIO numbers. Configure the actual drivers in `config/airshot_v2.json`
or the stopped-only HUD calibration transfer.

The main controller now owns a capability-based fault manager. Its matrix is
generated from `config/fault_manager.json`; see
[`fault_management.md`](../docs/fault_management.md) for live behavior, hardware
boundaries, telemetry, commissioning and the master pneumatic isolation circuit.
No PDM/fan/ECU RPM-cut protocol or physical wastegate-open command is assumed.

All Teensy GPIO/ADC signals must be conditioned to 0–3.3 V; they are not 5 V
tolerant. Use power drivers for motors, pumps and valves, and condition bike
lamp feeds and pressure senders. Reset-state pulldowns belong on driver inputs.

## Dedicated thermal Teensy pin map

Thermal configuration 2.0.0 implements the [wiring pack](../docs/thermal_wiring.md).
These pins belong to the SECOND Teensy, not the main controller.
Generated thermal_hardware.h and sensor_config.cpp derive from
config/thermal_system.json; rerun tools/generate_thermal_config.py after edits.

| Thermal pin(s) | Function | Connection |
| --- | --- | --- |
| 11 / 12 / 13 | MOSI / MISO / SCK | All 4 MAX31856 and 7 MAX31865 boards |
| 10 / 9 / 8 / 7 | TC0-TC3 CS | EGT L/R, turbine outlet L/R |
| 2 / 3 / 4 / 5 / 6 / 14 / 15 | R0-R6 CS | Seven PT1000 boards |
| 18 / 19 | Wire SDA / SCL | N0 0x48, N1 0x49, N2 0x4A |
| 17 / 16 | Wire1 SDA / SCL | N3 0x48, N4 0x49 |
| 22 / 23 | CAN1 TX / RX | Separate 3.3 V logic CAN transceiver |
| VIN / GND | Power | Protected regulated 5 V; isolate VUSB for dual supply |

Breakouts use an independently budgeted 3.3 V rail. MAX VIN connects to that
rail; MAX 3Vo outputs stay unconnected. DRDY/FLT/ALRT pins are not assigned.
Initialize all chip selects high before acquisition.

## Thermal sensor/ADC connector assignment

Stable CAN IDs are not GPIO numbers. ADS1115 logical channel = 4 * board + AIN.
N4.A2 (logical 18) monitors excitation and is not a temperature ID.
N4.A3 is unused. PT1000 boards use 4300-ohm references; baseline two-wire
jumpers tie RTD+ to F+ and RTD- to F-. Do not ground an RTD lead.

| Sensor ID | Key | Technology | Front end |
| --- | --- | --- | --- |
| 1 | EGT_LEFT | k_type | TC0 / CS 10 |
| 2 | EGT_RIGHT | k_type | TC1 / CS 9 |
| 3 | TURBINE_OUT_LEFT | k_type | TC2 / CS 8 |
| 4 | TURBINE_OUT_RIGHT | k_type | TC3 / CS 7 |
| 5 | COMP_IN_LEFT | iat_ntc | N0 / A0 |
| 6 | COMP_IN_RIGHT | iat_ntc | N0 / A1 |
| 7 | COMP_OUT_LEFT | iat_ntc_high | N0 / A2 |
| 8 | COMP_OUT_RIGHT | iat_ntc_high | N0 / A3 |
| 9 | IC_IN_LEFT | iat_ntc_high | N1 / A0 |
| 10 | IC_IN_RIGHT | iat_ntc_high | N1 / A1 |
| 11 | IC_OUT_LEFT | iat_ntc | N1 / A2 |
| 12 | IC_OUT_RIGHT | iat_ntc | N1 / A3 |
| 13 | PRE_WMI | iat_ntc | N2 / A0 |
| 14 | POST_WMI | iat_ntc | N2 / A1 |
| 15 | PLENUM_IAT | iat_ntc | N2 / A2 |
| 16 | RUNNER_IAT_LEFT | iat_ntc | N2 / A3 |
| 17 | RUNNER_IAT_RIGHT | iat_ntc | N3 / A0 |
| 18 | HEAD_COOLANT_LEFT | coolant_ntc | N3 / A1 |
| 19 | HEAD_COOLANT_RIGHT | coolant_ntc | N3 / A2 |
| 20 | HEAD_METAL_LEFT | pt1000 | R0 / CS 2 |
| 21 | HEAD_METAL_RIGHT | pt1000 | R1 / CS 3 |
| 22 | RAD_IN | coolant_ntc | N3 / A3 |
| 23 | RAD_OUT | coolant_ntc | N4 / A0 |
| 24 | OIL_GALLERY | pt1000 | R2 / CS 4 |
| 25 | OIL_COOLER_IN | pt1000 | R3 / CS 5 |
| 26 | OIL_COOLER_OUT | pt1000 | R4 / CS 6 |
| 27 | TURBO_OIL_DRAIN_LEFT | pt1000 | R5 / CS 14 |
| 28 | TURBO_OIL_DRAIN_RIGHT | pt1000 | R6 / CS 15 |
| 29 | AMBIENT_AIR | iat_ntc | N4 / A1 |
| 30 | CHRA_TEMP_LEFT | pt1000 | Disabled / no hardware |
| 31 | CHRA_TEMP_RIGHT | pt1000 | Disabled / no hardware |
| 32 | RESERVED_THERMAL_32 | disabled | Disabled / no hardware |

NTC pull-up/probe profiles remain provisional. Confirm actual resistances,
protection/filtering and lead errors before use. See
[acquisition and bench checks](../docs/thermal_wiring.md#commissioning-holds)
and [raw CAN semantics](../docs/thermal_can_protocol.md).

## Air Shot V2 and dynamics

Air Shot runs four independent valves at the main 200 Hz control cadence.
OFF/MANUAL/AUTO selection and renewable FIRE requests arrive on CAN; the main
Teensy checks pressure, driver feedback, thermal state, engine state, torque
permission and pitch margin. The former fixed shot latch and fake wastegate
boost substitution are removed. Compressor refill remains separate from demand.
[Air Shot V2](../docs/airshot_v2.md) describes calibration, driver feedback,
EEPROM persistence and the USB three-position switch.

DBWX2 channel 1 is the intended single driven channel for the 2026 MT-07
throttle-body assembly. Its connector pinout, polarity, redundant sensor wiring
and kill/interlock circuit remain hardware verification items; this repository
does not assign them to Teensy GPIO. RaceGrade uses CAN rather than local I2C.
Installation proposals in `vdc_io.h` include RaceGrade base 0x470, DBWX2 node 10,
main node 9 and DBWX2 broadcast base 0x300 to avoid ECU IDs. Verify device setup
against [vehicle dynamics](../docs/vehicle_dynamics.md).

Engineering limits/maps live in `config/vdc_engineering.json`. Missing measured
values remain null. Rider levels, curves and bounded envelopes are separate.
The latched stop request 0x20A (or engine-run OFF) removes powertrain authority;
run-ON does not clear it. See the dynamics document for recovery and independent
kill requirements. Software implementation is not a road-qualified calibration.

## CAN families

| IDs (hex) | Purpose |
| --- | --- |
| 100–10F | ECU telemetry |
| 130–147 | Existing controller/status/service frames, including legacy Air Shot compatibility |
| 160–17D | Thermal heartbeat, values, statuses, configuration, faults and raw diagnostics |
| 180–185 | Air Shot V2 telemetry |
| 190–19E | Air Shot requests, external feedback and calibration transactions; see protocol for allocated IDs |
| 207–20A | Weather, rider settings/envelopes and latched stop |
| 210 | DBWX2 physical-position request |
| 220–229 | Unified dynamics telemetry and configuration fingerprint |

DBWX2 native polling also uses extended 29-bit frames; an 11-bit-only filter
will lose its replies. Flame intent remains provisional CAN behavior, with no
dedicated flame output pin on either board.

## Build, flash and verify

Install the Teensy board package plus FlexCAN_T4 and Watchdog_t4. The thermal
sketch additionally needs Adafruit MAX31856 and its Adafruit BusIO dependency.
Build each sketch independently:

```sh
arduino-cli compile --fqbn teensy:avr:teensy41 arduino/teensy41/albatross_controller_teensy41
arduino-cli compile --fqbn teensy:avr:teensy41 arduino/teensy41/albatross_thermal_node
```

Run these from the repository root. Label the two USB devices and flash the
matching image to each board. Do not assume the existing single-controller
update bundle flashes or identifies the thermal Teensy; verify the target and
use a separate thermal flashing step.

```sh
python tools/check_thermal_config.py
python tools/generate_airshot_config.py --check
python tools/generate_vdc_config.py --check
python tests/run_thermal_checks.py
python tests/run_airshot_checks.py
python tests/run_dynamics_checks.py
python tests/run_can_demo_checks.py
```

The CAN demo includes all three subsystems; see
[demo controls](../docs/can_demo_controls.md). Validate firmware builds and
physical conversion, pin mapping, bus timing and failure behavior separately.
