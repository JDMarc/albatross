# Powered DBWX2 bench fixture

This adds **real position requests** for the intact MT-07 assembly through DBWX2
channel 1. It is not a simulated motor display. It is also not an on-bike test
mode: the road firmware and `bench_hud.py` observer are unchanged.

## Architecture

```text
PC / Pi: dbw_bench_hud.py
          | USB serial, bounded requests
Dedicated bench Teensy 4.1: arduino/bench/dbw_bench
          | isolated 500 kbit/s CAN, DBWX2 request + feedback polling
DBWX2 channel 1 -> MT-07 throttle motor and its dual TPS

Bench key + physical momentary deadman -> bench Teensy inputs
Bench Teensy permit -> verified external actuator-inhibit circuit
Independent latching kill -> hardware isolation, independent of all software
```

Use an isolated fixture Teensy (or a disconnected board deliberately flashed
with this image), **never the controller installed on the motorcycle**. This is
not a request to add a third on-bike controller. No ECU, engine, vehicle harness,
road controller or other DBWX2 command publisher belongs on this fixture bus.
CAN1 TX 22 / RX 23 requires a suitable 3.3 V CAN transceiver and correct bus
termination. These are not direct CAN-H/CAN-L pins. No motor or coil connects
directly to Teensy GPIO.

DBWX2 retains the motor PID and its dual-controller protections. The official
[DBWX2 page](https://www.dbwx2.com/) identifies TunerStudio as its configuration
tool. Use the correct manufacturer documentation for the actual hardware and
firmware; this code targets the repository's **0.92** native runtime layout.
It does not discover, flash or configure DBWX2 automatically.

## Mandatory commissioning inputs

`arduino/bench/dbw_bench/bench_config.h` is deliberately uncommissioned. The
request path is implemented, but the shipped profile cannot energize outputs.
Provide measured/reviewed values rather than copying the synthetic test fixture:

- `fixtureConfig()`: both TPS closed/open counts (including reversed polarity),
  electrical rails, allowed channel disagreement, starting-position envelope,
  maximum requested opening, independent hard actual-position ceiling, request
  rise rate, motor current ceiling, tracking tolerance
  and persistence. Percent means **calibrated travel**, not blade angle or torque.
- Host lease, feedback age, arming window, maximum run duration, and watchdog
  reset budget. These must be compatible with measured USB/CAN scheduling and
  DBWX2 behavior. Host sends holds at up to 50 Hz; board status is up to 20 Hz.
  Do not choose timing budgets below measured worst-case communication latency.
  The sketch uses WDT1, whose configured seconds must be 0.5–128 in half-second
  steps; that hardware resolution is not a recommended actuator fault budget.
- Unique fixture revision and verified DBWX2 0.92 identity, custom receive mapping,
  native sensor behavior, command-loss response, independent kill and external
  permit/inhibit wiring.
- Three distinct available fixture pins: maintained bench key and momentary
  deadman contacts to ground (`INPUT_PULLUP`), and active-high permit output.
  Pins 22/23 are CAN; 13 is excluded. Pins default to -1, not guessed assignments.

The permit circuit must be **deenergize-to-inhibit**, with an external pull-down
so a reset/unpowered Teensy cannot enable it. The independent kill must work even
if the Teensy output sticks high. Verify the actual DBWX2 electrical inhibit /
actuator power architecture with its documentation; this project does not infer
an undocumented DBWX2 enable pin or claim a GPIO itself isolates motor power.
Power the fixture with appropriate fusing/current limitation, guard the throttle
plates, and verify spring return and physical kill before sending nonzero demand.
DBWX2 electronics/feedback must remain observable with the fixture permit off.

Configure DBWX2 Custom CAN receive for the verified fixture position mapping:
standard `0x210`, unsigned 16-bit big-endian byte 0, 0–1000 representing 0–100%
travel. Defaults match the existing project adapter; they are not proof your
device is configured. Disable any competing command/standalone fallback path and
verify zero/partial/end-point behavior. The other six command bytes are zero;
**no imaginary enable bit is relied on**. Keep DBWX2's own protections enabled.
DBWX2 node 10 / fixture node 9 and the 0.92 table-5 offsets 0/64/76/60 must match.
See [existing native adapter notes](vehicle_dynamics.md#installation-prerequisites).

## Build and use

```sh
arduino-cli compile --fqbn teensy:avr:teensy41 arduino/bench/dbw_bench
python dbw_bench_hud.py --port COM5 --profile 1
```

COM5 and revision 1 are examples; supply the isolated Teensy's actual USB port
and your compiled revision. This port is **not DBWX2's USB configuration port**.
Install Pygame and pyserial in the Python environment. Flash only after reviewing
the dedicated fixture profile and identifying the correct disconnected board.
No firmware upload is performed by the HUD. Profile revision matching prevents
accidental mismatches; it is not cryptographic firmware attestation.

1. Start with independent kill engaged; inspect wiring and guarded mechanics.
2. Establish DBWX2 logic/feedback communication and verify inhibit/return behavior
   with your physical commissioning procedure. Missing feedback is unavailable,
   not assumed healthy. An uncommissioned board reports CONFIGURATION REQUIRED.
3. Turn the bench key on, leave the momentary deadman **released**, choose target
   with up/down (1% UI increments, bounded by the board limit), press A then Enter.
4. Wait for **ARMED** acknowledgement. Hold the physical deadman and keyboard H
   together to request movement. The board ramps the request within its profile.
5. Release either hold control to end the run. Re-arm explicitly for another test.
   Target edits require H released. There are no unattended sweeps in this version.
6. Space/Escape or closing the app requests STOP. **Use the independent kill for
   emergency isolation**, particularly if acknowledgement is absent.

Zero demand / PERMIT OFF is not a claim that the throttle is physically closed.
The screen separately shows command, TPS and current. Focus loss, broken USB,
expired host lease, maximum run duration, feedback loss, driver faults, current
or TPS faults and persistent tracking error remove permit / zero demand. Serious
faults latch until controller restart and inspection; USB has no fault-clear
command. Stopped sessions cannot resume from renewed HOLD packets. A scheduling
gap also faults; hardware watchdog reset and external pull-down cover a firmware
hang, subject to real validation of their timing and electrical behavior.

## Protocol and recording

USB ASCII, newline-delimited, bounded 96-byte command buffer:
`ARM epoch`, `HOLD epoch sequence target_permille`, `STOP`. Epoch changes on stop;
strictly increasing sequence rejects duplicates. ARM requires released deadman,
bench key, fresh healthy feedback and a position within the startup envelope.
HOLD requires both physical inputs and the current armed epoch. No calibration,
motor PWM, Air Shot, automatic fault-clear or road-enable command exists.

Status JSON explicitly identifies protocol 1, profile, configuration, state,
reason, epoch, sequence, physical inputs, permit, feedback quality, command,
position, current, maximum request and host lease. Invalid current/position uses
sentinel -1 plus `good=0`. Board feedback health uses all four native groups.
Wrong-length/unmatched/stale CAN replies cannot refresh them. Observing another
standard CAN writer on the command ID latches a fault; this is an extra check,
not a guarantee that all possible bus contention is detected.

`logs/bench` stores real USB TX/RX records with `hardware_tx=true`. Logging failure
requests stop. The session also records the requested fixture revision. Keep the
exact compiled `bench_config.h`, DBWX2 configuration export and wiring revision
with each test record; local road-config hashes do not prove flashed bench limits.
The legacy raw-CAN replay tool does not accept these USB journals.

## Air Shot provisions

`config/bench_airshot.json` reserves INTAKE L/R, TURBINE L/R and MASTER NC, and
lists the unknown part/driver/current/PWM/pulse/rest/pressure fields. No solenoid
pins are assigned and no solenoid power command exists yet. Do not reuse DBWX2
motor channels as an assumed solenoid driver.

After parts are selected, add one-channel bounded pulse/current-response tests
with the NC master interlock. Begin unpressurized; pressurized flow tests require
rated guarded plumbing, independent isolation, relief and venting. Compressor
testing is outside this implementation. No valve duty-cycle or current limit is
invented here.

## Validation status

Host fake-USB tests: `python tests/run_powered_bench_checks.py`.
Controller native tests: compile/run `tests/bench_core_checks.cpp` with C++17.
Sketch fake-I/O tests: compile `tests/bench_io_checks.cpp` with C++17 and
`-Itests/bench_stubs`. These exercise the actual sketch parser, CAN request
encoding, polling and permit-removal path against mocked hardware. Its synthetic
profile is blocked from Arduino-target builds.
Teensy compilation validates the shipped **disabled** profile, not your eventual
wiring/calibration. No powered actuator, reset trajectory, return behavior, CAN
bus-off condition or independent kill has been physically validated by these
software tests. Complete those fixture checks before treating this as accepted
bench equipment.
