# Unified vehicle dynamics: DBWX2 + RaceGrade

## Status and authority

This is an implemented, host-tested control framework, **not a calibrated or road-qualified motorcycle controller**. Do not flash it onto a running vehicle as a drop-in update. Missing engineering calibration deliberately produces zero torque authority, minimum throttle target, no boost request and no Air Shot permission. No actuator, ECU or DBWX2 firmware was flashed during development.

The main Teensy owns the shared estimator/classifier, TCS, AWC and torque arbitration. DBWX2 retains its own redundant sensor checks, motor control and internal protection. The second Teensy remains dedicated to thermal acquisition. The Pi displays telemetry, requests rider settings, records events and obtains advisory weather; it does not close the throttle servo loop. Flame mode remains a CAN feature without a new dedicated pin.

The former rear/front comparator is removed. Rear slip requires wheel divergence plus independently inconsistent chassis acceleration and time confirmation. A slowing airborne front wheel is excluded from the grounded speed reference. Controlled lift can remain permitted with AWC LOW; approaching the pitch/rate envelope reduces torque. Simultaneous lift/slip can activate both controllers. Touchdown limits torque recovery. Engine and rider-release ceilings remain authoritative.

The selected rider curve maps grip to requested torque. Separate RPM/torque tables map permitted torque to physical throttle angle and boost contribution. They are not interchangeable percentages. Existing boost-mode and engine-protection checks precede the new supervisor. Existing MS3 torque-cut request frames remain supervisory requests, not newly invented ignition/fuel-cut tables.

Startup and recovery require a released grip and closed TPS through self-test before torque authority returns. Real plausibility/driver/tracking faults latch until controller restart; simply receiving fresh CAN does not clear them. Missing startup feedback itself is recoverable once valid data arrives.

## Installation prerequisites

Intended donor is now the user's **2026 Yamaha MT-07 throttle-body assembly**, with one DBWX2 driven channel retained. [Yamaha's 2026 specifications](https://yamahamotorsports.com/models/mt-07/features) confirm YCC-T electronic throttle, but do not supply a motor-count/pinout drawing. Motor count, shared mechanical linkage, dual TPS outputs, connector orientation, motor polarity and spring-rest position must be checked against the actual assembly and matching Yamaha service information. Do not infer a pinout from older cable-throttle MT-07 parts. `throttle_body_verified` and `independent_kill_verified` remain false until those hardware checks are actually completed; these flags are not a substitute for the checks.

1. Configure the RaceGrade device to the motorcycle's **500 kbit/s**, STANDARD two-frame mode. Verify its base ID and mounting transform in `vdc_io.h`. Defaults propose base `0x470`; they do not assert that the device has been configured. The axis transform must produce forward/lateral/up specific force and roll/pitch/yaw body rates with the signs expected by the estimator. Verify stationary gravity, positive nose-up rotation and both lean directions on a fixture. Do not auto-zero a moving motorcycle.
2. The adapter targets the **DBWX2 0.92 runtime layout**. Verify actual firmware/INI identity before setting `dbwx2_v092_verified`. Runtime sensor words are little-endian; protocol addressing is big-endian. Read-only table-5 requests fetch offsets 0 (dual APS + channel-1 dual TPS), 64 (current), 76 (error/CPU/bridge/CAN status) and 60 (channel/calibration status). One outstanding request, exact reply address/length and bounded age prevent unrelated replies refreshing safety data. No calibration writes or flash/burn commands are sent.
3. Proposed MegaSquirt node IDs are main Teensy 9 and DBWX2 10. Confirm uniqueness. These are node addresses inside extended CAN headers, not standard arbitration IDs. Native DBWX2 broadcast base `0x100` conflicts with Albatross ECU messages: remap it, proposed `0x300`, and update all consumers. Extended receive must remain enabled on the bus. Verify bus utilization and worst-case latency with every installed node.
4. **Only DBWX2 throttle channel 1 is supervised here.** Do not use this as a validated dual-actuator implementation. A second controlled throttle requires independent channel-2 feedback, actuator bounds, monitoring and tests.
5. Configure DBWX2 Custom CAN receive for standard `0x210`, unsigned big-endian word at byte 0. The word represents requested physical travel, 0–1000 (0.1% travel). Its conversion/table must preserve the commissioned physical-position request; do not apply an additional rider curve or positive adder. Disable standalone rollback. DBWX2's own maximum-opening and plausibility protections remain enabled. Verify all endpoints and intermediate points without a running engine.
6. Bytes 2 (sequence), 3 (enable), 4–5 (permitted torque, 0–1000) are Albatross diagnostics. **Stock Custom CAN receive must not be assumed to enforce these bytes.** A zero position word is the software inhibit; it is not a proven independent electrical motor disable. No GPIO/interlock pin is invented. Prove the actual DBWX2 command-loss timeout, zero-demand behavior, mechanical return and independent kill/interlock path. Only then set `dbwx2_custom_receive_verified` and `watchdog_verified`. The helper `CommandWatchdog` is not code running inside DBWX2.

The manufacturer describes DBWX2 for competition/off-road use. This software does not change that designation. Manufacturer references: [DBWX2](https://www.dbwx2.com/), [0.92 firmware package and INI](https://www.dbwx2.com/Files/Firmware/Revision-C/FwUpdater_Ver092_inifix.zip), [adder/limiter application note](https://www.dbwx2.com/Files/Manuals/App%20note%20-%20Using%20Adder%20and%20Limitter%20tables.pdf).

RaceGrade signed axis scaling is 0.001 g/bit for acceleration and 0.001 Hz/bit for angular rate; the adapter converts angular rate to degrees/second, including the factor of 360. See [RaceGrade RG_SPEC-0027 v1.9](https://racegrade.com/downloads/RG_SPEC-0027%20IMU%20V1.9.pdf). Extended read addressing follows the [MegaSquirt 29-bit protocol](https://www.msextra.com/doc/pdf/Megasquirt_29bit_CAN_Protocol-2015-01-20.pdf).

## Calibration and rider controls

The [rider-curve editor](throttle_curves.md) now provides baseline COMFORT/ROAD/RESPONSE shapes and a fixed 1:1 option. These are source calibration edits with immediate local preview; applying edited points requires a rebuilt main-controller image and matching Pi configuration. They are not actuator calibration or a live CAN point-upload protocol.

`config/vdc_engineering.json` is the service source. Generate/check the firmware header with `python tools/generate_vdc_config.py` / `--check`. All missing physical numbers remain null. The only retained aid numbers are the repository's previous LOW/MED/HIGH slip thresholds; retaining them does **not** validate the new classifier. Synthetic test constants live only in `tests/vdc_fixture.h`, never in the vehicle configuration.

Measure APS/TPS endpoints, rails, disagreement/rate thresholds, actuator travel/current/tracking limits, IMU mounting/bias/ranges, wheel geometry, plausible accelerations, slip targets/gains, pitch/rate envelopes, lean envelopes, torque ramps, weather factors and both actuator maps. Set `validated` only after reviewing the complete set. The Pi cannot casually change those engineering fields. After successful arming, dynamics-only sensor failure can retain the validated throttle map bounded by `degraded_torque`, with boost and Air Shot disabled. Hard DBW/ECU faults and failed commissioning still remove authority. See `fault_management.md` for the supervisory matrix and remaining validation requirements.

On the main HUD, focus the TCS/AWC tile and press Select. Up/down chooses a row; left/right requests independent OFF/LOW/MED/HIGH levels, COMFORT/ROAD/RESPONSE curve, weather assist or bounded rider pitch/lean settings. Select on LIVE TELEMETRY or EVENT HISTORY opens the secondary page. Back returns. OFF remains visible on the home tile. Tracking and correction are distinguished; normal intervention is not a generic fault warning. Genuine faults and stale telemetry remain faults.

The plotted curves come from the configuration, not decorative guessed curves. Missing points show a calibration warning. Firmware broadcasts a truncated SHA-256 configuration fingerprint; the HUD refuses curve changes/plots if its configuration version is not confirmed. Screenshot fixtures explicitly display SYNTHETIC PREVIEW. Requests wait for a controller acknowledgement; the home HUD always shows reported settings. No acknowledgement is not success.

Restart policy defaults to RESET ON START (MED/MED, first curve, weather assist on), with a stopped-only REMEMBER option. Remembered engineering-bounded rider envelopes restore serially after acknowledgements. Hard engineering pitch protection remains active even if rider AWC is OFF. This must be explained to the rider during commissioning.

## CAN additions

All standard messages below use protocol version 1 in byte 0, except the raw fingerprint. Multi-byte numbers are big-endian. Telemetry is 20 Hz; control runs on the existing main control cadence. Hardware polling is paced separately (proposed 5 ms requests, four groups), subject to measured bus timing.

| ID | Purpose |
| --- | --- |
| 207 | Weather validity/context (4 bytes); connectivity never grants torque authority |
| 208 | Rider levels/curve/weather; 8 bytes, request ID byte 6, marker A5 byte 7 |
| 209 | Bounded rider envelope; parameter byte 1, float32 bytes 2–5, ID/marker 6–7 |
| 20A | Powertrain stop: exact 6-byte payload `01 53 54 4F 50 A5`; stop only, no clear command |
| 210 | DBWX2 physical-position request; see installation prerequisites |
| 220 | State, event, TCS/AWC levels, curve, intervention flags, last request ACK |
| 221 | Rider/permitted/TCS/AWC/lean/engine/mode torque percentages |
| 222 | Front/rear/estimated speed (0.01 m/s), sensor confidence |
| 223 | Pitch/lean/pitch rate (signed 0.01 degree or degree/s) |
| 224 | Slip/target (signed ratio ×10000), slip/lift/contact confidence |
| 225 | Throttle command/actual (0.01 degree), boost (0.1 psi), Air Shot margin |
| 226 | 32-bit fault mask, confidence, weather state, calibration-valid flag |
| 227 | Rider target/max pitch, left/right lean bounds, weather-assist setting |
| 228 | Original boost request (float32 psi), for offline replay |
| 229 | Eight-byte firmware configuration fingerprint (no version byte) |

## Air Shot and weather

Air Shot evaluates VDC validity, torque authority, active correction and envelope margin during operation, including FIRE. It no longer compares physical throttle percentage with requested torque percentage when VDC monitoring is available. Controlled lift alone is not an inhibit; the allowed air profile tapers with remaining pitch margin. Sensor/DBW faults or torque reduction inhibit it. Its existing pressure, temperature, driver, WMI and wastegate checks remain intact.

Weather is advisory, not a grip measurement. The Pi uses phone GPS rounded to 0.1 degree to request temperature, humidity and precipitation from [Open-Meteo](https://open-meteo.com/en/docs), with low-rate fetching, a bounded timeout and freshness states. This sends approximate location to that service. Rain can only tighten calibrated targets/recovery. Phone/internet loss removes that advisory context without becoming a dynamics sensor fault. No pavement-temperature or surface-grip value is fabricated. Weather assist is rider-selectable.

## Logging, replay and verification

The bounded background event recorder stores raw RX/TX CAN with monotonic timestamps, UTC trigger, 3-second pre/post windows, weather context and calibration identity. Events can extend to 12 seconds; row/queue limits prevent unbounded memory. Long continuous events are bounded clips, not unlimited continuous logging. Capture failures are surfaced on the HUD. Logs normally live beside Air Shot logs in a `dynamics` directory.

`tools/vdc_replay.cpp` compiles against the **same `vdc.cpp`** used on Teensy. `tools/replay_dynamics_log.py` reconstructs held inputs from raw RaceGrade frames, matched native DBWX2 requests/replies, ECU frames and supervisor telemetry, then runs that binary offline. It never transmits CAN. A matching recorded firmware/configuration fingerprint is required. No real motorcycle log was available during development; synthetic replay conversion and native execution are tested.

Example build/run (substitute your compiler and paths):

```sh
c++ -std=c++17 tools/vdc_replay.cpp arduino/teensy41/albatross_controller_teensy41/vdc.cpp -o vdc_replay
python tools/replay_dynamics_log.py event.jsonl --binary ./vdc_replay --installation installation.json --output replay.csv
```

`installation.json` must reflect the verified hardware transform, e.g. keys `accel_axis`, `gyro_axis`, `accel_sign`, `gyro_sign`, `imu_base`, `node` matching `Hardware` in `vdc_io.h`. The default proposed transform is axis `[1,0,2]` / `[2,1,0]`, signs `[1,1,1]`, base 1136 and node 10. Do not copy that as a claim of verified mounting.

Replay uses sampled speed/engine-limit telemetry and a cold estimator at the clip start. It is **not bit-identical ISR reconstruction** and cannot recover earlier unlogged estimator state. For exact timing validation, capture raw wheel edges/control input snapshots and a longer steady-state lead-in on the bench.

Host checks: `tests/vdc_scenarios.cpp` covers all 25 requested scenarios; `tests/vdc_io_checks.cpp` checks native packet endian/scaling, malformed/stale replies, command markers and missing-feedback cold-start recovery. `python tests/run_dynamics_checks.py` checks HUD navigation, telemetry, logging, weather and replay conversion. Existing Air Shot and thermal Python suites remain applicable. Teensy 4.1 compilation is checked separately. None of these replaces hardware-in-the-loop testing.

## Remaining qualification work

### Latched powertrain stop (software backup)

In the Dynamics menu select POWERTRAIN STOP, then Select again within three seconds. The Pi repeats the stop request until the controller reports fault bit 13 (`0x2000`, POWERTRAIN STOP LATCHED). Unconfirmed transmission explicitly directs the rider to the physical kill switch. This menu is **not an emergency substitute** for a directly accessible hardwired switch.

The main Teensy latches stop immediately on the exact `0x20A` packet or an existing `0x127` engine-run OFF request. A subsequent run-ON packet, settings change, TCS/AWC OFF, fresh sensor data or phone reconnect cannot clear the latch. On following control ticks it sends zero DBWX2 travel demand, removes DBW torque/boost/Air Shot authority, stops WMI/compressor/flame intent, deasserts the existing wastegate enable pins and sends the existing 100% ECU torque-cut request. HUD, lights and logging remain operational. This disables the powertrain controls; it is **not a ride-through bypass** that turns off supervision while leaving the electronic throttle uncontrolled.

Recovery requires key-off/controller restart after inspecting the cause, then released-grip/closed-throttle self-test. If the Pi is still alive with an unconfirmed stop request, it continues requesting stop, so cycling only the Teensy does not intentionally authorize a restart. The latch is volatile across a full power cycle; an independent physical latching kill circuit must provide the electrical safety boundary.

Important: zero CAN demand and ECU cut are software requests, not evidence that power has been removed from a stuck actuator. Wire and validate an independent kill/interlock that removes combustion authority and safely inhibits DBWX2/pneumatic actuators even if Pi, Teensy or CAN fails. Validate wastegate behavior when its enable is removed. Do not merely cut power to the ECU/CAN sender while leaving DBWX2 able to retain a previous command. Neither the schematic nor final interlock components/pins have been supplied, so this repository does not fabricate them or assert they are installed.

No road-use enable or claimed legal approval is provided by this change. DBWX2's competition/off-road designation remains an unresolved road-deployment constraint; obtain manufacturer guidance and a qualified review of the complete installation. A kill safeguard alone cannot validate unmeasured maps, sensing or actuator response.

- Earn the calibration on a fixture/dynamometer and controlled test course; validate all fault trajectories before enabling torque. An abrupt protective reduction itself has riding risk.
- Verify command loss, frozen target streams, processor resets, power/brownout, CAN bus-off/load, wiring faults, motor-stuck/slow and kill-switch behavior with DBWX2. Software flags do not prove electrical isolation.
- Validate front/rear sensing electrically. At standstill and with an airborne front wheel, absence of pulses alone cannot prove a healthy wire. Long airborne speed estimates accumulate uncertainty; a six-axis IMU cannot independently bound absolute yaw drift or guarantee pitch accuracy under sustained acceleration.
- Measure estimator confidence/error envelopes on actual geometry/tires and mixed lift/slip events. Present confidence is heuristic, not a certified probability; measured plant replay and fault injection must refine it.
- Validate MS3 torque authority and integration rather than assuming stock ECU CAN support for arbitrary Albatross requests. Confirm that no second writer can increase DBWX2 demand.
- Review ergonomics/distraction and all rider-setting transitions with the actual grip controller and display. Hardware switching is not validated by a headless screenshot.

These prerequisites are intentionally not concealed by convenient final numbers or an assertion of road readiness.
