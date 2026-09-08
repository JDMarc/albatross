# Albatross CAN ID reference

Repository contract, reviewed 2026-09-08. This consolidates the current main
Teensy, thermal Teensy, Pi and configured external-device interfaces.
It is not a claim that the ECU or unselected driver hardware already implements
every publisher. Python names containing Arduino refer to the main Teensy.

## Bus and interpretation

- Classical CAN at 500 kbit/s. Tables use hexadecimal **11-bit standard IDs**
  unless explicitly marked extended. DBWX2 polling also needs 29-bit frames.
- Integers are big-endian unless noted. u16/s16 mean unsigned/signed 16-bit.
  "x10" means the transmitted integer is ten times the engineering value.
- Air Shot V2 frames start with byte 0 = 2. VDC/fault telemetry starts with
  byte 0 = 1, except 0x210 and 0x229. Legacy frames have no common version byte.
- One physical publisher per message. Demo tools impersonate nodes and belong
  on an isolated bench bus, never alongside the corresponding operating nodes.
- A frame definition is not authentication, proven actuator response, or ECU
  configuration. Status, version, length, sequence and freshness remain mandatory.
- Unlisted IDs are **unallocated by this repository**, not guaranteed free on
  purchased devices. Do not transmit on them without an allocation review.

## ECU telemetry: configured MS3 integration -> main Teensy / Pi

These are Albatross mappings, not a statement of stock MS3 broadcast defaults.
Verify the installed ECU firmware/TunerStudio mapping; see
[MS3 setup](ms3_tunerstudio_setup.md). Temperatures from the thermal node remain
the primary HUD source; the ECU retains independent CLT/IAT/oil protection.

| ID | Name | Payload / implementation boundary |
| --- | --- | --- |
| 0x100 | ENGINE_RPM | u16 RPM (2 bytes) |
| 0x101 | THROTTLE_POSITION | u8 percent (1) |
| 0x102 | BOOST_PRESSURE | u16 boost psi x10 (2); not absolute MAP kPa |
| 0x103 | AFR_BANKS | L/R u16 AFR x100 (4) |
| 0x104 | KNOCK_STATUS | Bitmask, 1 or 2 bytes accepted |
| 0x105 | OIL_PRESSURE_TEMP | u16 oil psi x10; optional u16 ECU oil C x10 (2/4). HUD oil temperature comes from thermal node |
| 0x106 | COOLANT_TEMP | u16 ECU CLT C x10 (2), independent fallback; not primary HUD temperature |
| 0x107 | FUEL_LEVEL | u8 percent (1) |
| 0x108 | GEAR_POSITION | u8: 0 neutral, 1-6 gears (1) |
| 0x109 | ENGINE_LOAD | u8 percent (1) |
| 0x10A | INTAKE_AIR_TEMP | u16 ECU IAT C x10 (2); main fallback, does not overwrite thermal plenum reading |
| 0x10B | EXHAUST_GAS_TEMP | Retired primary temperature input; ID retained, main/Pi do not use it for EGT |
| 0x10C | BATTERY_VOLTAGE | u16 millivolts (2) |
| 0x10D | FLEX_FUEL | u8 ethanol percent (1) |
| 0x10E | INJECTOR_STATUS | u16 pulse width ms x100; optional u16 duty percent x10 (2/4) |
| 0x10F | BOOST_PRESSURE_BANKS | L/R u16 boost psi x10 (4); requires actual bank-pressure publishers |

## Requests and ECU status

Requests do not override the main controller's capability/torque arbitration.
ECU-bound requests require a verified ECU integration, not just a transmitted frame.

| ID | Publisher -> consumer | Purpose / status |
| --- | --- | --- |
| 0x110 | ECU -> main | Legacy flame status, bool byte; deprecated alternative to Pi 0x122 |
| 0x111 | ECU -> main | WMI trigger u16 percent x10; retained input |
| 0x112 | ECU -> main | Engine status byte |
| 0x120 | Pi -> main | Boost request u16 psi x10 |
| 0x121 | Pi -> main | Ride mode byte: 1 ECO, 2 NORMAL, 3 SPORT, 4 RACE, 5 ALBATROSS |
| 0x122 | Pi -> main | Flame intent bool; no dedicated flame GPIO |
| 0x123 | Pi -> main | Limp bool + reason byte |
| 0x124 | Pi -> main | Legacy traction setting: 1 LOW, 2 MED, 3 HIGH, 4 OFF; VDC uses 0x208 |
| 0x125 | Pi -> main | Legacy momentary Air Shot request; ignored as an actuation route in V2 |
| 0x126 | Pi -> main (declared) | PHONE_LINK enum retained; no dedicated main switch handler |
| 0x127 | Pi -> main | Engine-run bool; OFF latches powertrain stop, ON cannot clear latch |
| 0x128 | Pi -> main | Legacy WMI arm byte retained; automatic WMI remains main-owned |
| 0x129 | Pi -> main | Fuel code byte |
| 0x12A | Main -> ECU | Torque-cut request; verify ECU acceptance and protection behavior |
| 0x12B | Main -> ECU | Traction-slip request; verify ECU acceptance |
| 0x140 | Pi -> main | NFC authorization bool |
| 0x14A | Pi -> main (declared) | MEDIA_CONTROL enum retained; no dedicated main handler; media is otherwise Pi/phone-owned |
| 0x150 | Pi -> ECU | Fuel code, fuel-table byte, u16 stoichiometric AFR x100 (4) |
| 0x151 | Pi -> ECU | Spark-table selection byte |
| 0x152 | Pi -> ECU | Rev limiter strategy: 0 fuel cut, 1 ignition cut; ECU mapping required |
| 0x1F0 | Utility requester -> main | Legacy POST request; not the current HUD's evidence-based POST |
| 0x1F1 | Main -> utility/HUD | Legacy reply A4 01; canned presence acknowledgement, NOT a physical health certificate |

## Main Teensy -> HUD compatibility and service telemetry

Published by the current main sketch. Prefer V2/VDC telemetry for rich Air Shot
and dynamics state; legacy messages are not independent corroborating sensors.

| ID | Purpose | Payload |
| --- | --- | --- |
| 0x130 | Air Shot compatibility | Remaining-count byte, legacy active byte (2); use 0x180-0x184 |
| 0x131 | AWC compatibility | Active byte, signed lean byte (2); use VDC for full state |
| 0x132 | RGB lighting | RGB bytes (3); status is not a new lamp-driver assignment |
| 0x133 | Tank pressure | u16 psi x10 (2) |
| 0x134 | Twin-turbo status | L/R u16 psi x10 (4); not turbo shaft speed |
| 0x135 | Wastegate status | L/R commanded duty percent bytes (2), NOT measured position |
| 0x136 | Gear position | ECU gear byte relayed (1) |
| 0x137 | Wheel speeds | Front/rear u16 m/s x100 (4) |
| 0x138 | Fuel level | Relayed percent byte (1), not a separate fuel-level sensor |
| 0x139 | WMI status | Tank %, command u16 cc/min, actual u16 cc/min, fault byte (6) |
| 0x13A | Clutch slip | Percent and severity bytes (2) |
| 0x13B | Light status | Input bitmask (1); see decode.py |
| 0x13C | Oil pressure fallback | u16 psi x10 (2); source can be ECU or main A0 fallback |
| 0x13D | Fuel type | Fuel code byte (1) |
| 0x13E | Traction compatibility | s16 slip percent x10, torque-cut %, flags (4) |
| 0x13F | Service sensor voltages | Four u16 mV: oil A0, WMI A1, reference, tank A2 (8) |
| 0x145 | Digital service states | Input/output/command/fault masks (4); output bit 4 reports main pin 12 master command |
| 0x146 | Main firmware identity | Device, major/minor/patch, u16 build (6) |
| 0x147 | Limp status | Active bool, reason (2) |

## Dedicated thermal Teensy -> main / Pi

Protocol v1, node address byte 5; configuration thermal-2.0.0. Stable sensor
IDs 1-32, with 30-32 disabled. See [thermal protocol](thermal_can_protocol.md)
and [sensor wire schedule](thermal_wiring.md). Raw values have technology-specific
signedness. Missing/invalid measurements must never become plausible zeros.

| ID | Purpose | DLC / encoding |
| --- | --- | --- |
| 0x160 | Heartbeat | 8: version, node, flags, u32 uptime seconds, sequence |
| 0x161 | Temperatures 1-4 | 8: four s16 C x10; -32768 invalid |
| 0x162 | Temperatures 5-8 | 8: four s16 C x10; -32768 invalid |
| 0x163 | Temperatures 9-12 | 8: four s16 C x10; -32768 invalid |
| 0x164 | Temperatures 13-16 | 8: four s16 C x10; -32768 invalid |
| 0x165 | Temperatures 17-20 | 8: four s16 C x10; -32768 invalid |
| 0x166 | Temperatures 21-24 | 8: four s16 C x10; -32768 invalid |
| 0x167 | Temperatures 25-28 | 8: four s16 C x10; -32768 invalid |
| 0x168 | Temperatures 29-32 | 8: four s16 C x10; -32768 invalid |
| 0x169 | Statuses 1-8 | 4: eight nibbles, earlier sensor in high nibble |
| 0x16A | Statuses 9-16 | 4: eight nibbles, earlier sensor in high nibble |
| 0x16B | Statuses 17-24 | 4: eight nibbles, earlier sensor in high nibble |
| 0x16C | Statuses 25-32 | 4: eight nibbles, earlier sensor in high nibble |
| 0x16D | Configuration | 8: canonical JSON CRC32, semantic 2/0/0, channel count 32 |
| 0x16E | Fault summary 1-8 | 1: bit per channel |
| 0x16F | Fault summary 9-16 | 1: bit per channel |
| 0x170 | Fault summary 17-24 | 1: bit per channel |
| 0x171 | Fault summary 25-32 | 1: bit per channel |
| 0x176 | Raw diagnostics 1-4 | 8: four raw front-end words; status authoritative |
| 0x177 | Raw diagnostics 5-8 | 8: four raw front-end words; status authoritative |
| 0x178 | Raw diagnostics 9-12 | 8: four raw front-end words; status authoritative |
| 0x179 | Raw diagnostics 13-16 | 8: four raw front-end words; status authoritative |
| 0x17A | Raw diagnostics 17-20 | 8: four raw front-end words; status authoritative |
| 0x17B | Raw diagnostics 21-24 | 8: four raw front-end words; status authoritative |
| 0x17C | Raw diagnostics 25-28 | 8: four raw front-end words; status authoritative |
| 0x17D | Raw diagnostics 29-32 | 8: four raw front-end words; status authoritative |

Heartbeat/status/fault groups: 10 Hz; temperature groups: 25 Hz; configuration:
0.5 Hz; raw groups: 2 Hz. These are publish schedules, not new physical samples.

## Air Shot V2

All listed V2 frames include version byte 2 in their DLC. The payload column
describes bytes AFTER that version. Complete enums/transaction rules:
[Air Shot V2](airshot_v2.md#can-contract), airshot_io.cpp and airshot.py.

| ID | Publisher -> consumer | DLC | Payload / boundary |
| --- | --- | --- | --- |
| 0x180 | Main -> Pi | 8 | Mode, state, reason, profile, demand %, available %, flags |
| 0x181 | Main -> Pi | 8 | Four valve commands %, driver faults, u16 event |
| 0x182 | Main -> Pi | 8 | Tank/regulator/used u16 psi x10, validity |
| 0x183 | Main -> Pi | 8 | u16 event, u16 duration ms, u16 starting tank psi x10, stage |
| 0x184 | Main -> Pi | 8 | Four shadow commands %, u16 config version, compressor enum |
| 0x185 | Main -> Pi | 8 | Config status, pins-valid, stage, u16 field count, u16 token |
| 0x190 | Pi -> main | 3 | Mode 0 OFF / 1 MANUAL / 2 AUTO; A5 |
| 0x191 | Pi -> main | 5 | FIRE pressed byte, u16 sequence, reserved; renewable request lease |
| 0x192 | External/test -> Air Shot adapter | 8 | Rider/DBW permitted/actual %, flags, target u16 psi x10, reserved. Integrated sketch overrides DBW authority with VDC; not a bypass |
| 0x193 | Regulator feedback provider -> main | 8 | u16 regulated psi x10, four reserved bytes, validity. Priming requires a verified post-master sensor location; publisher hardware still to be selected |
| 0x194 | EWG feedback provider -> main | 6 | L/R commands %, L/R actual positions %, validity. External feedback publisher required |
| 0x195 | Unimplemented / demo-observer reservation | — | Referenced in Python input-ID bookkeeping; no production main receive handler or assigned payload |
| 0x198 | Valve driver feedback -> main | 5 | Intake L: u16 current mA, fault byte, reserved; physical publisher required |
| 0x199 | Valve driver feedback -> main | 5 | Intake R: u16 current mA, fault byte, reserved; physical publisher required |
| 0x19A | Valve driver feedback -> main | 5 | Turbine L: u16 current mA, fault byte, reserved; physical publisher required |
| 0x19B | Valve driver feedback -> main | 5 | Turbine R: u16 current mA, fault byte, reserved; physical publisher required |
| 0x19C | Pi service -> main | 8 | Begin=1, A5, u16 token, three reserved bytes |
| 0x19D | Pi service -> main | 8 | Sequential u16 field ID, float32 value, reserved |
| 0x19E | Pi service -> main | 8 | u32 FNV hash, u16 field count, A5; commit validated calibration |

Calibration transfers require the existing stopped/engine-off checks; they are
not rider-mode frames. Current/position payloads must represent physical
measurements, not echoes of desired commands.

## VDC / DBW / TCS / AWC

See [vehicle dynamics](vehicle_dynamics.md#can-additions) and vdc_io.cpp.
All rows except 0x210/0x229 start with version 1. Control/telemetry rates are
separate: the main control tick is 200 Hz, status publication 20 Hz.

| ID | Publisher -> consumer | DLC | Purpose |
| --- | --- | --- | --- |
| 0x207 | Pi -> main | 4 | Weather validity, rain, context; advisory only |
| 0x208 | Pi -> main | 8 | TCS/AWC levels (0 OFF,1 LOW,2 MED,3 HIGH), curve, weather enable, reserved, request ID, A5 |
| 0x209 | Pi -> main | 8 | Parameter ID, float32 envelope value, request ID, A5; engineering bounds enforced |
| 0x20A | Pi -> main | 6 | Exact 01 53 54 4F 50 A5; latched powertrain STOP, no clear command |
| 0x210 | Main -> DBWX2 | 8 | NO version: u16 travel 0-1000 at bytes 0-1; sequence, enable, u16 permitted torque, reserved x2. Stock DBWX2 must NOT be assumed to enforce diagnostic bytes |
| 0x220 | Main -> Pi | 8 | State, event, levels, curve, flags, ACK |
| 0x221 | Main -> Pi | 8 | Rider/permitted/TCS/AWC/lean/engine/mode torque percentages |
| 0x222 | Main -> Pi | 8 | Front/rear/estimated u16 speed m/s x100, confidence |
| 0x223 | Main -> Pi | 8 | s16 pitch/lean/pitch-rate x100, reserved |
| 0x224 | Main -> Pi | 8 | s16 slip/target ratio x10000, slip/lift/contact confidence |
| 0x225 | Main -> Pi | 8 | Throttle command/actual angle x100, boost psi x10, Air Shot margin |
| 0x226 | Main -> Pi | 8 | u32 faults, confidence, weather state, engineering-calibration valid |
| 0x227 | Main -> Pi | 8 | Target/max pitch x100, left/right lean bytes, weather enable |
| 0x228 | Main -> Pi | 8 | Original boost request float32 psi, reserved x3; replay context |
| 0x229 | Main -> Pi | 8 | NO version: first 8 bytes of calibration SHA-256 fingerprint |

## Fault manager / master isolation

All frames have version 1 at byte 0 and DLC 8. Payload below follows the version.
Source: [fault management](fault_management.md#telemetry-unchanged-hud-and-recording),
fault_manager/telemetry.h and main publishStatusFrames().

| ID | Publisher -> consumer | Payload |
| --- | --- | --- |
| 0x240 | Main -> Pi | Rideability, u16 capabilities, u16 requested actions, missing-calibration flag, sequence |
| 0x241 | Main -> Pi | Torque %, u16 boost psi x10, u16 RPM limit, reserved, sequence |
| 0x242 | Main -> Pi | Rotating fault index, lifecycle, severity, confidence, mitigation result, u16 recurrence count |
| 0x243 | Main -> Pi | u32 complete active fault mask, reserved x2, sequence |
| 0x245 | Main -> Pi | Master configured, commanded open, physical closure quality (currently INVALID); byte 4 extension version 1, byte 5 prime state, bytes 6-7 reserved zero |

0x240/241/243 must form a complete matching-sequence bundle; 0x242 rotates
historical detail. 0x245 does not prove valve closure or pneumatic isolation.
Prime state values: 0 UNCONFIGURED, 1 OFF, 2 INHIBITED, 3 FILLING,
4 PRIMED (controller-qualified fresh post-master pressure), 5 FAULT, 6 SHADOW.
Legacy extension byte 4 = 0 provides no priming proof. Pressure-qualified
readiness is separate from physical master-valve position/closure quality.
Air Shot reason IDs append 28 PRIMING and 29 PRIME FAULT without renumbering
existing reasons. Old Pi decoders need updating to recognize these reasons.
PDM control, fuel-pressure feedback, turbo-speed telemetry and other future
hardware do not acquire CAN allocations merely because a monitor is planned.

## External standard CAN devices (installation-dependent defaults)

| ID | Publisher -> consumer | DLC | Current adapter interpretation |
| --- | --- | --- | --- |
| 0x300 | DBWX2 -> main | 8 | Remapped native aggregate pedal/throttle broadcast; diagnostic only, not independent dual APS/TPS validation |
| 0x470 | RaceGrade IMU -> main | 6 or 8 | Three s16 BE accelerations, 0.001 g/count; configured mounting transform |
| 0x471 | RaceGrade IMU -> main | 6 or 8 | Three s16 BE angular rates, 0.001 Hz/count = 0.360 deg/s/count |

These bases are configured in vdc_io.h; they are NOT proof that purchased devices
use them. DBWX2's default base 0x100 conflicts with ECU RPM: remap it before
joining the bus. Audit the device's entire enabled broadcast range, not only
the base frame the adapter consumes. RaceGrade must use the expected STANDARD
two-frame format and 500 kbit/s.

## DBWX2 extended CAN polling (29-bit identifiers)

This is a second addressing scheme, not additional fixed standard IDs.
The adapter targets the DBWX2 0.92 runtime layout and reads only channel 1.
Local node = 9; DBWX2 node = 10; both must be unique on the installed network.

```text
ID = (offset << 18) | (type << 15) | (from << 11) |
     (to << 7) | (table << 3)

Request: offset = runtime byte offset, type=1, from=9, to=10, table=5
Reply:   offset = rotating token (0..2047), type=2, from=10, to=9, table=6
```

| Runtime offset | Requested bytes | Meaning |
| --- | --- | --- |
| 0 | 8 | Dual APS and channel-1 dual TPS, four LITTLE-endian u16 words |
| 64 | 4 | Motor current; first LE u16 scaled 0.01 A |
| 76 | 8 | Error / CPU / bridge / CAN status |
| 60 | 4 | Channel / calibration status |

Request DLC 3: table 6, token >> 3, ((token & 7) << 5) OR requested length.
Responses must match the exact computed extended ID, expected DLC and pending
request deadline. One request is outstanding at a time; polling is proposed
at 5 ms intervals, gated by verified hardware/configuration. No calibration
write or burn command is sent. See vdc_io.cpp for status-bit interpretation.

## Reserved, retired and bench boundaries

- 0x172-0x175, 0x186-0x18F, 0x196-0x197 and 0x244 are gaps, not implemented frames.
- 0x200-0x206 are not accepted synthetic APS/TPS/IMU replacement inputs by the
  current VDC adapter. Native DBWX2 polling and RaceGrade frames supply evidence.
- 0x126, 0x14A and 0x195 have definitions/bookkeeping but no corresponding
  production main-controller handling; do not assume functionality from an ID.
- 0x125 no longer fires Air Shot. 0x192 is not the integrated DBW authority.
- Bench-only powered actuator control uses the separate USB serial protocol;
  it is not a second CAN DBWX2 command writer.
- Current HUD POST uses fresh subsystem evidence, not the canned 0x1F1 reply.
- Legacy Mega firmware is outside this current production table.

## Source and maintenance checks

Sources: [Python legacy/thermal IDs](../albatross_pi/canbus/ids.py),
[main sketch](../arduino/teensy41/albatross_controller_teensy41/albatross_controller_teensy41.ino),
[Air Shot adapter](../arduino/teensy41/albatross_controller_teensy41/airshot_io.cpp),
[VDC adapter](../arduino/teensy41/albatross_controller_teensy41/vdc_io.cpp),
[thermal transport](../arduino/teensy41/albatross_thermal_node/can_transport.cpp).
Run `python tools/check_can_reference.py` after protocol edits to check documented
standard IDs against enum definitions, adapter IDs and thermal ranges.
This verifies coverage, not every payload field or hardware configuration.
