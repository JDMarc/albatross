# Fault detection, isolation and recovery

## Authority and implementation boundary

The main Teensy's `FAULT_MANAGER` owns the inhibit matrix and fault ceilings.
Its pure C++ core has no hardware drivers. The VDC receives a fault torque
ceiling alongside its existing engine/mode ceilings; the boost target is capped
before wastegate supervision, and Air Shot consumes a capability permission.
The Pi decodes this authority and uses the existing HUD error presentation.
It cannot clear a controller latch by ignoring a HUD error.

This is an implemented foundation with live integrations, **not completion or
road qualification of every proposed detector**. Unsupported sensors/protocols
and unset engineering thresholds remain explicit. No MS3 tune, DBWX2 firmware,
PDM configuration or physical harness was changed.

## Live changes

- Pi timeout no longer independently requests limp or disables WMI. Last accepted
  rider configuration remains local. Pi-mediated MANUAL FIRE still expires when
  its lease stops; local AUTO remains independently evaluated. Prior explicit
  STOP/limp requests are not cleared by losing the Pi. Startup authentication and
  DBW commissioning requirements remain.
- Thermal-node loss and individual EGT/coolant/plenum sensor loss remove advanced
  boost/Air Shot/WMI-dependent capability, retaining the existing 8 psi degraded
  ceiling. Fresh independent ECU CLT/IAT/oil or remaining appropriate thermal
  measurements must still cover basic temperatures. Total basic thermal blindness
  retains the previous zero-authority response. Existing actual-overtemperature
  thresholds and hard responses remain unchanged pending staged calibration.
- One auxiliary EGT fault alone no longer removes engine torque authority.
- Dynamics-only WSS/IMU loss, after successful VDC arming, can retain the validated
  throttle map up to the existing `degraded_torque` limit. TCS/AWC/lean-aware
  functions and Air Shot are unavailable; boost request is zero. No one-wheel
  slip estimator or redundant APS bypass is invented. Hard DBW/ECU faults still
  remove authority. Sensor recovery retains the existing release-grip/self-test
  process and calibrated torque-rise behavior.
- Zero oil pressure above the existing 2200 RPM gate is no longer excluded from
  the existing below-8-psi protection. This legacy hard rule remains as backup;
  the new dynamic oil envelope is not commissioned.
- WMI failure removes dependent boost/Air Shot capability. No dry high-performance
  map is supplied, so requested boost goes to zero. No automatic MS3 map switch is
  claimed. Idle/no-demand WMI evidence is UNKNOWN, not proof the pump recovered.
- Air driver faults isolate the optional subsystem, request compressor inhibition
  and master isolation without automatically removing normal engine torque.
- Supervisory overboost detection uses the existing commissioned Air Shot
  overboost margin and fresh MAP/bank pressure, even while Air Shot is OFF.
  It removes boost/Air Shot capability and requests isolation. It does not claim
  that a zero boost request physically opens the wastegates.

The coordinator sees native VDC fault classification on the following 5 ms tick;
the VDC's own protective output acts in the detecting tick. Air Shot still checks
that tick's VDC permission directly. Telemetry masks are not motor feedback.

## Configuration and lifecycle

`config/fault_manager.json` is the source for the embedded policy matrix.
Run `python tools/generate_fault_config.py` after engineering edits, and
`python tools/generate_fault_config.py --check` in verification. Reflash the main
Teensy to apply it. This is service configuration, not a rider/HUD editing menu.

The registry separates source, class, severity, rideability, capabilities, actions,
clear policy and ceilings. UNKNOWN evidence never heals an active fault or counts
toward stable recovery. The state machine supports NORMAL, SUSPECT, CONFIRMED,
ACTIVE, MITIGATING, DEGRADED, RECOVERING, CLEARED and LATCHED. It records occurrence
count, first/last time and total active time within the controller session.
Key-cycle/service/latch policies are distinct. No remote service-clear command
is exposed; authorized stopped service clearing is a core API only.

Definitive existing source fault flags act immediately after their source's
existing checks. New analog/rate/plausibility monitors require explicit enabled
status, thresholds, hysteresis, confirmation time and verified context. Null
recovery times inherit validated VDC `self_test_ms`; without that calibration,
automatic stable recovery is unavailable. The engine's existing hard protections
are not silently weakened to accommodate an unset new policy.

`FULL_DBW`/`FULL_RPM` removal without a supplied ceiling is flagged as missing
calibration. Missing DBW ceiling retains the existing zero-authority hard fallback,
never full torque. A requested action with no implementation is marked UNAVAILABLE.
RPM ceilings are published but have no verified MS3 actuator protocol here.
Zero boost request is not proof of physically open wastegates or zero boost.

## Monitor coverage

| Area | Implemented | Still required |
|---|---|---|
| Electrical/node health | Existing CAN/thermal/DBW/driver flags into registry | PDM, bus-off counters, optional-node isolation topology |
| Fuel | Differential-pressure and rate primitives; low-DP + dual-lambda fusion | Rail sensor and lambda adapters, common pressure reference, thresholds, ECU mitigation contract |
| Oil | RPM/temperature envelope and rate monitor; legacy hard backup | Measured curve, thermal coefficient, hysteresis and staged limits |
| EWG | Calibrated command-position error rules and response-verifier core | Direction-specific position/current calibration, verified open command, deadlines |
| Air Shot | Existing current/driver checks, capability gating, master output | Leak/flow characterization, pressure-decay context, physical closure feedback |
| Thermal substitution | Provenance-aware helpers; remaining coolant diagnostics | Placement validation for MAT/ambient estimates; no ECU MAT substitution |
| Dynamics | Native plausibility plus validated reduced-throttle path | Stationary norm/freeze/jitter calibration and raw tone-ring history analysis |
| Turbo/cylinder | Optional speed/lambda/rate monitors and generic fusion | Speed hardware, cylinder baseline bins, validated five-signal balance rules |
| Cooling/electrical | Existing voltage faults; generic rate/response/baseline primitives | Fan/PDM/current telemetry, fan/load commands, battery start-event analysis |
| Recovery | Persistence, stable-data requirement, local actuator protections | Per-mitigation response criteria and escalation deadlines |
| Trends | Healthy/authorized-only baseline primitive | Persistent operating bins and commissioned degradation detectors |

Optional `SubsystemMonitors.signals` are the integration boundary: drivers supply
engineering units, timestamp, maximum age and validity. Missing inputs remain
INVALID. RAIL and MAP must have the same pressure reference; existing MAP is psi
gauge. Lambda is not inferred from a fuel-dependent AFR without a verified
stoichiometric conversion. Oil pressure is psi and oil temperature degrees C.
No left/right lambda substitution is provided.

Learned baselines never write policy or engineering limits. Optional configured
rules run the same C++ algorithms in production and host tests. New monitors are
disabled by default, not shown as commissioned or proven healthy.
Fuel fusion also requires explicit commissioning and enabled differential-pressure
and dual-lambda rules; its escalation is not silently enabled by adding sensors.
Conflicting evidence is deterministic: BAD dominates UNKNOWN, which dominates
GOOD. Confidence here describes source evidence, not a proven component diagnosis.
Fault torque recovery uses existing VDC ramps. Dedicated progressive boost-ceiling
restoration and response-driven escalation remain to be commissioned/integrated;
stable fault clearing alone is not a claim that those functions exist.

## Master NC pneumatic valve

Plumbing: tank -> regulator -> normally-closed master -> four performance valves.
Main Teensy **pin 12** is reserved for an active-high protected master driver;
it is now rejected as an individual performance-valve pin. Use an external
pulldown, rated driver/fuse/flyback arrangement and a correctly rated NC valve.
GPIO cannot power the coil. Include this circuit in the independent pneumatic
kill path; removing ECU/DBW power alone does not isolate stored compressed air.

The shipped `master_air_isolation.pin` is null and `driver_verified` false.
After wiring verification, set pin 12 and verification true, regenerate and
reflash. Boot commands LOW. In operation it opens only during allowed physical
Air Shot output, and closes on OFF/end/reset/protective isolation requests.
Power-loss closure is a hardware property that must be tested. No physical
position/flow feedback exists in this build; telemetry explicitly marks it INVALID.
Until the master is installed, a mechanically stuck-open downstream valve cannot
be guaranteed isolated by software. Shadow suppresses downstream shot outputs,
not all compressor activity.

## Telemetry, unchanged HUD and recording

New standard 11-bit 500 kbit/s telemetry, version byte 1:

| ID | Remaining bytes |
|---|---|
| 0x240 | rideability, available u16, requested actions u16, missing-calibration flag, sequence |
| 0x241 | torque percent, boost psi-x10 u16, RPM u16, reserved, sequence |
| 0x242 | fault index, lifecycle, severity, evidence confidence, mitigation result, session count u16 |
| 0x243 | complete active-fault mask u32, reserved x2, sequence |
| 0x245 | master configured, commanded-open, physical-quality INVALID, reserved x4 |

0x240/241/243 commit atomically by sequence. Incomplete/mixed/duplicate bundles
do not refresh freshness. The Pi uses the existing 300 ms supervision timeout;
expired authority becomes UNKNOWN with unavailable limits, never FULL/healthy.
One detail record rotates per publish; details have receive timestamps and must
not override the complete current mask. Infinity/no ceiling is wire 65535, not 0.
Existing fault presentation, ignore confirmation and episode re-alert behavior
are reused; ignoring the display does not mutate main-controller capabilities.

When live CAN logging is enabled, `fault_windows` captures up to 10 seconds of
pre-fault raw RX/TX CAN, the active episode and 20 seconds afterward. Writes are
asynchronous and bounded. Overflow/disk failures raise an existing-style HUD
fault; recordings disclose dropped/truncated data. This records received CAN
resolution, not a claim of 200 Hz logging for every sensor. Pi loss removes rich
recording; controller recurrence/history is session-local and not a persistent
onboard black box. Frozen/missing telemetry cannot be recorded retrospectively.

`python tools/replay_fault_log.py <fault_windows.jsonl>` replays captured telemetry
through the same Pi decoder without opening CAN or driving hardware. This is
decoder/lifecycle-display replay, **not** rerunning the embedded controller against
all original sensor samples. Master command status is decoded separately with
freshness and physical-quality metadata; commanded-open never proves valve motion.

## Verification and remaining commissioning

Host C++: `tests/fault_manager_test.cpp` (header-only) and the existing
`tests/vdc_scenarios.cpp` linked with `vdc.cpp`. Python:
`tests/run_fault_manager_checks.py`, `tests/run_fault_config_checks.py`, existing thermal, Air Shot, dynamics,
navigation and alert regression runners. Arduino target: `teensy:avr:teensy41`.
`tests/air_isolation_test.cpp` builds with `-Itests/host` and verifies GPIO command
behavior only. Synthetic test thresholds are not production calibrations.

Before engine/road testing, supply the PDM model/protocol, fuel/pressure/current
sensor specifications and mappings, EWG driver polarity/position convention,
master valve/driver details, ECU protection interface and measured engineering
thresholds. Verify physical shutdown and degraded recovery with independent
kill equipment. Software tests and compilation do not certify safe rideability.
