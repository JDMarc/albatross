# Albatross firmware: two Teensy 4.1 boards

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
| 22 | CAN RX | CAN1 RX to transceiver RXD |
| 23 | CAN TX | CAN1 TX to transceiver TXD |
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

Four MAX31856 thermocouple front ends and two ADS7953 16-channel ADCs share
hardware SPI. Each device has its own chip-select. Sources:
`thermocouple_driver.h`, `analog_adc_driver.h`, and `can_transport.h`.

| Thermal Teensy pin | Direction | Connection |
| --- | --- | --- |
| 11 | SPI MOSI | All MAX31856 SDI and ADS7953 SDI inputs |
| 12 | SPI MISO | Shared MAX31856 SDO and ADS7953 SDO outputs |
| 13 | SPI SCK | All six devices' serial clocks |
| 10 | CS output | MAX31856 channel 0: EGT_LEFT |
| 9 | CS output | MAX31856 channel 1: EGT_RIGHT |
| 8 | CS output | MAX31856 channel 2: TURBINE_OUT_LEFT |
| 7 | CS output | MAX31856 channel 3: TURBINE_OUT_RIGHT |
| 6 | CS output | ADS7953 device 0: logical analog channels 0–15 |
| 5 | CS output | ADS7953 device 1: logical analog channels 16–31 |
| 22 | CAN RX | CAN1 RX to this board's transceiver RXD |
| 23 | CAN TX | CAN1 TX to this board's transceiver TXD |
| GND | Reference | Front-end, transceiver and conditioned sensor returns |
| 3.3 V | Logic supply | Compatible logic circuitry only; size the front-end/reference power supplies for the actual PCB |

No data-ready or fault GPIO is allocated; front ends are polled over SPI.
CANH/CANL connect to transceivers, never directly to Teensy pins. Terminate only
the two physical ends of the whole CAN trunk, not every board.

## Thermal sensor/ADC connector assignment

Sensor ID is the stable CAN/HUD identity, not a Teensy GPIO number. ADC channel
numbers are zero-based. Logical analog channel = 16 × device + local channel.
The 32-entry configuration currently enables 29 sensors and reserves three.

| Sensor ID | Key | Technology | Front end |
| --- | --- | --- | --- |
| 1 | EGT_LEFT | K type | MAX31856 0, CS 10 |
| 2 | EGT_RIGHT | K type | MAX31856 1, CS 9 |
| 3 | TURBINE_OUT_LEFT | K type | MAX31856 2, CS 8 |
| 4 | TURBINE_OUT_RIGHT | K type | MAX31856 3, CS 7 |
| 5 | COMP_IN_LEFT | IAT NTC | ADC 0 / CH 0 |
| 6 | COMP_IN_RIGHT | IAT NTC | ADC 0 / CH 1 |
| 7 | COMP_OUT_LEFT | IAT NTC | ADC 0 / CH 2 |
| 8 | COMP_OUT_RIGHT | IAT NTC | ADC 0 / CH 3 |
| 9 | IC_IN_LEFT | IAT NTC | ADC 0 / CH 4 |
| 10 | IC_IN_RIGHT | IAT NTC | ADC 0 / CH 5 |
| 11 | IC_OUT_LEFT | IAT NTC | ADC 0 / CH 6 |
| 12 | IC_OUT_RIGHT | IAT NTC | ADC 0 / CH 7 |
| 13 | PRE_WMI | IAT NTC | ADC 0 / CH 8 |
| 14 | POST_WMI | IAT NTC | ADC 0 / CH 9 |
| 15 | PLENUM_IAT | IAT NTC | ADC 0 / CH 10 |
| 16 | RUNNER_IAT_LEFT | IAT NTC | ADC 0 / CH 11 |
| 17 | RUNNER_IAT_RIGHT | IAT NTC | ADC 0 / CH 12 |
| 18 | HEAD_COOLANT_LEFT | Coolant NTC | ADC 0 / CH 13 |
| 19 | HEAD_COOLANT_RIGHT | Coolant NTC | ADC 0 / CH 14 |
| 20 | HEAD_METAL_LEFT | PT1000 | ADC 0 / CH 15 |
| 21 | HEAD_METAL_RIGHT | PT1000 | ADC 1 / CH 0 |
| 22 | RAD_IN | Coolant NTC | ADC 1 / CH 1 |
| 23 | RAD_OUT | Coolant NTC | ADC 1 / CH 2 |
| 24 | OIL_GALLERY | PT1000 | ADC 1 / CH 3 |
| 25 | OIL_COOLER_IN | PT1000 | ADC 1 / CH 4 |
| 26 | OIL_COOLER_OUT | PT1000 | ADC 1 / CH 5 |
| 27 | TURBO_OIL_DRAIN_LEFT | PT1000 | ADC 1 / CH 6 |
| 28 | TURBO_OIL_DRAIN_RIGHT | PT1000 | ADC 1 / CH 7 |
| 29 | AMBIENT_AIR | IAT NTC | ADC 1 / CH 8 |
| 30 | CHRA_TEMP_LEFT | Disabled | Reserved logical 25 (ADC 1 / CH 9); not acquired |
| 31 | CHRA_TEMP_RIGHT | Disabled | Reserved logical 26 (ADC 1 / CH 10); not acquired |
| 32 | RESERVED_THERMAL_32 | Disabled | No physical input assigned |

Thermocouples connect to their compensated front ends, not an ADC input.
PT1000 conditioning currently assumes 500 µA excitation; NTC channels require
the configured pull-ups and calibration profiles. Reference, filtering,
protection and conversion constants must match the actual acquisition PCB.
See [thermal design](../docs/thermal_system.md) and
[thermal protocol](../docs/thermal_can_protocol.md).

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
