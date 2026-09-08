# Power-on self test

The HUD POST is a read-only startup report, not an actuator commissioning test
and not a roadworthiness certificate. Controller-local protections remain active
independently of the Pi and this screen.

## Sequence and evidence

24 checks appear at 0.45-second intervals, with a short introduction and final
hold (11.6 seconds total). Results remain live throughout the sequence, so
late-arriving telemetry can replace WAIT before the deadline. Even a healthy
system displays the full sequence. Two columns fit 1280x480 and 1920x720.

- OK: fresh received evidence and the check's stated plausibility criteria.
- WAIT: evidence has not arrived yet.
- UNVERIFIED: evidence was still missing/stale when the sequence ended.
- FAULT: received evidence failed the check.
- DEFER: physical testing cannot be established by this read-only POST.

FAULT/UNVERIFIED requires a new press of the configured acknowledgement key
or grip SELECT. Held keys do not pre-acknowledge. Dismissal does not clear
controller faults, enable a capability, or suppress the normal HUD error system.
Individual result details are written to the application log at completion.

## Coverage

ECU RPM reception (including valid zero RPM), main Teensy, thermal heartbeat
and configuration CRC, all 18 NTCs / seven PT1000s / four thermocouples,
VDC bundle/configuration, VDC-reported DBWX2/APS/TPS and IMU health,
wheel-speed faults, fault-manager health/calibration, Air Shot V2 and pressure
validity, WMI status, oil-pressure plausibility, battery-voltage telemetry,
fuel level, display framebuffer and USB controller enumeration.

A reported DBW/IMU fault-free state is not accepted before the VDC is calibrated
and out of INIT/SELF TEST. It is supervisory evidence, not a replacement for
the DBWX2's own safety checks. Legacy receive evidence is tracked by message ID
and minimum payload length, never inferred from unrelated nonzero values,
unknown traffic or local TX. Typed services retain their own protocol validation.

Legacy telemetry uses the existing 1.5-second HUD freshness window; thermal
configuration allows 2.5 seconds because it broadcasts every two seconds.
Thermal and VDC/Air/Fault services retain their existing freshness rules.
Snapshot age is added so a frozen upstream snapshot cannot keep passing.

## Deferred physical checks

Stationary wheel-speed readings cannot prove pulses. EWG position/current
response, pneumatic master physical closure, fan/PDM response, WMI flow,
charging under load and DBW actuator tracking require controlled commissioning.
A commanded-closed isolation valve is not proof of physical closure.
Zero oil pressure is expected with fresh zero RPM and is deferred, not a
fabricated sensor failure. Positive running pressure is only coarse plausibility;
the ECU/controller owns dynamic oil-pressure protection.

No throttle sweep, wastegate movement, fan test, pump run or air-valve firing is
performed at startup. Use the separate bench-only interface and hardware
commissioning procedures for powered tests.

## Verification

Run `python tests/run_post_checks.py` with the HUD's pygame dependency installed.
It checks missing/malformed/TX-only evidence, zero RPM, late arrivals, stale
snapshots, configuration mismatch, subsystem faults and staged completion.
It renders both supported layouts into output/post for visual review.
