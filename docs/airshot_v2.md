# Air Shot V2

## Rider controls

The main HUD tile always displays controller-confirmed OFF/MANUAL/AUTO, including
while firing. Focus AIR and press Select once; Left/Right cycles modes. Select
again opens diagnostics. Back returns to the selected tile, then Home. Pending
requests/no-ack hints are separate from confirmed mode.

Settings > AIR MODE SWITCH learns each position from the USB grip controller,
including center represented by neither button. Keep other axes/buttons still
while capturing. Select/Back/FIRE buttons are excluded. The mapping is stored by
controller GUID. Stable switch transitions command the mode; holding the switch
does not override later D-pad choices. Disconnect requests OFF. This is a CAN
mode request, not a hardwired emergency stop.

FIRE uses the existing grip button (default USB button 2) and a 150 ms renewable
lease. Release/focus loss/disconnect stops the request. A held button cannot
repeatedly fire. The secondary screen shows state/reason, profile, demand,
pressure, four valve commands/currents, shadow commands, driver faults,
compressor, last duration/pressure change, DBW, TCS/AWC, WMI and thermal status.

## Runtime calibration

Settings > AIR SHOT CALIBRATION exposes 133 named parameters. Up/Down selects a
field, Left/Right edits, Select saves a draft. APPLY TO CONTROLLER needs engine
RPM zero, speed at most 1 mph and a second confirmation. The Teensy independently
requires fresh stopped conditions throughout transfer. FIRE is suppressed in
calibration/switch-learning screens; applying a calibration commands OFF.

MANUAL/AUTO selection does not require completing a commissioning sequence.
Stage 4 uses all four valves. Stages 2/3 restrict to intake/turbine respectively;
stage 7 and auto_shadow explicitly suppress all physical shots, including FIRE.
These remain deliberate calibration tools, not mandatory default locks.

Unknown hardware measurements remain null in config/airshot_v2.json. The editor
names missing fields; it cannot manufacture safe valve settings. Supply measured
pin assignments, PWM frequencies, duty/current limits, regulator thresholds,
profile timing, gains and thermal limits. Optional local FIRE/service pins use
-1: the USB FIRE button requires no extra Teensy input pin. Reserved/duplicate
pins, non-PWM outputs and incompatible paired PWM frequencies are rejected.

Transfers have sequential field IDs, finite/type/range checks, FNV checksum,
transaction-matched acknowledgements and two checksummed EEPROM slots. Invalid
pins are rejected before writing. The previous slot survives interrupted writes.
Driver faults latch until restart; investigate the cause before restarting.

## Firmware architecture

The existing main Teensy owns four independent PWM valves at a 200 Hz control
tick. The second Teensy remains dedicated to thermals. No flame pin is allocated.
The Pi issues requests; it does not calculate duty or bypass ECU protection.

Demand combines boost deficit, measured spool rate and rider transient, with
RPM/gear/fuel/ride/profile/pressure scaling and bounded left/right balancing.
Normal spool handoff/release tapers. Faults abort immediately. Duration, recovery
and rolling usage budgets limit shots. The old fixed latch and fake wastegate
boost substitution are removed.

The usage budget now counts FIRING and TAPERING time in the trailing
`budget_window_ms`, including the active interval immediately before OFF or a
fault. Usage expires incrementally; crossing a clock boundary does not refill it.
Accounting has control-tick resolution, not a separate hardware shutoff timer.
The bounded 64-interval history coalesces adjacent active ticks. If full, it merges
the oldest intervals including their idle gap, conservatively restricting usage
rather than forgetting it. Mode changes do not clear usage; controller
reinitialization/configuration does reset this runtime history. Shadow events
also consume simulated usage so test timing matches deployed timing.

RECOVERY state and RECOVERY profile are distinct. After an event ends,
`recovery_ms` prohibits another shot. For one further `recovery_ms`, an accepted
follow-up may use the RECOVERY profile. The context then expires, returning to
LAUNCH/MID_TRANSIENT/HIGH_RPM selection. Left/right imbalance has priority over
both recent-event and RPM selection. This uses the existing recovery calibration;
no new timing value or CAN field was introduced.

## Modes, profiles and stages

- OFF: shot outputs closed; compressor management remains separate.
- MANUAL: a fresh FIRE press requests one supervised event. Release normally
  tapers; holding FIRE does not repeatedly trigger events.
- AUTO: automatic request requires boost deficit, sufficient normalized demand
  and a rider-request rise. FIRE can also request a manual event. Automatic
  rearming requires demand below `auto_reset` with FIRE released.

Profiles are selected at event start, not separate rider modes: LAUNCH below
`launch_rpm`, HIGH_RPM above `high_rpm`, MID_TRANSIENT between them, RECOVERY for
a recent follow-up, or LEFT_LAG/RIGHT_LAG for bank imbalance. Each profile defines
intake/turbine weighting, intake decay and maximum duration. The bank-balancing
correction currently acts on turbine valves; intake valves retain individual trims.
Names do not imply validated performance or automatic launch-control arming.

Stage 2 restricts output to intake valves; stage 3 to turbine valves; stage 4 is
combined. Stage 7 is shadow-only. `auto_shadow=true` suppresses physical valve
output in MANUAL as well as AUTO. Accepted stage values 5, 6, 8 and 9 currently
have no separate behavior: they use combined outputs unless shadow is enabled.
They must not be interpreted as additional implemented test features or safety
levels. Stage/shadow selection does not disable separate compressor operation.

Required ECU frames 100/101/102/104/105/108/10C and bank boost 10F expire
independently. Permission, regulator, wastegate and four driver inputs also need
fresh data. Thermal values/status groups expire independently of heartbeat.
Missing feedback inhibits deployment; TPS is not treated as DBW torque permission.

The integrated main sketch now gets DBW permission and physical feedback from the [unified VDC and native DBWX2 adapter](vehicle_dynamics.md), not external frame 192. AWC tracking alone does not inhibit Air Shot; active correction, faults, torque limits and remaining pitch margin do. The remaining external pneumatic/wastegate driver feedback is still required.

Existing tank conversion and compressor settings are retained (95/145 psi,
15-second restart delay). Filling is a separate state, prohibited during shots,
movement, cranking, low voltage, stale ECU data or invalid tank ADC. Reported
compressor states are OFF/FILLING/COOLDOWN/FAULT. Physical pressure relief and
compressor duty/thermal protection remain necessary.

## CAN contract

Standard 11-bit IDs, existing 500 kbit/s bus. All new frames start with version
byte 2; integers and IEEE float32 use big endian. The table describes bytes after
the version. External DBW/driver hardware must publish actual feedback; firmware
for unspecified external hardware is not invented here.

| ID | DLC | Payload after version |
| --- | --- | --- |
| 180 | 8 | mode, state, reason, profile, demand %, available %, flags |
| 181 | 8 | intake L/R %, turbine L/R %, driver faults, event uint16 |
| 182 | 8 | tank/regulator/pressure-used uint16 psi x10, validity |
| 183 | 8 | event uint16, duration uint16 ms, starting tank uint16 psi x10, stage |
| 184 | 8 | four predicted %, config uint16, compressor enum |
| 185 | 8 | config status, pins-valid, stage, field-count uint16, token uint16 |
| 190 | 3 | mode (0 OFF, 1 MANUAL, 2 AUTO), A5 |
| 191 | 5 | FIRE pressed, sequence uint16, reserved |
| 192 | 8 | rider %, DBW permitted %, DBW actual %, flags, target uint16 psi x10, reserved |
| 193 | 8 | regulator uint16 psi x10, four reserved bytes, validity |
| 194 | 6 | WG commands L/R %, WG positions L/R %, validity |
| 198–19B | 5 | one driver's current uint16 mA, fault byte, reserved |
| 19C | 8 | begin=1, A5, token uint16, three reserved bytes |
| 19D | 8 | field uint16, float32 value, reserved |
| 19E | 8 | FNV uint32, field-count uint16, A5 |

192 flags: valid=bit0, ECU protection=bit1, AWC active=bit2. Status flags:
manual request=bit0, AUTO request=bit1, accepted=bit2, shadow=bit3. Enum order is
shared by airshot_types.h and albatross_pi/airshot.py. Legacy 130/133 telemetry
remains compatible; legacy 125 FIRE is no longer an actuation route.

## Checks and remaining physical work

Run python tests/run_airshot_checks.py and python tests/run_thermal_checks.py.
Compile tests/airshot_core_test.cpp with airshot_config.cpp, airshot_safety.cpp,
airshot_profiles.cpp and airshot_controller.cpp using a C++17 compiler. Arduino
The standalone `tests/airshot_budget_test.cpp` also builds with C++17 and checks
trailing-window expiration, partial overlaps, timer rollover and bounded-history
saturation against a per-millisecond oracle.
CLI target: teensy:avr:teensy41. Generate/check the calibration header with
python tools/generate_airshot_config.py [--check].

Timestamped raw RX/TX JSONL includes calibration transfers. Replay uses the same
decoder and preserves timeouts. A bounded background writer reports failures to
the HUD. Telemetry is sampled at 20 Hz, not a lossless per-request ECU recorder;
pressure drop is not air mass or proof of performance improvement.

Software tests and compilation are not road qualification. This release does
not include an energized individual-valve bench override, calibrated air-mass
estimator, matched assisted/unassisted performance scorer, turbo-speed sensor
integration, or compressor thermal-sensor firmware. Hardware-in-loop testing
must verify drivers/close timing, regulation, permission publishers, ECU
integration and plumbing before riding. Do not bypass missing physical feedback
to turn an inhibited display into READY.
