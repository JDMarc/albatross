# Thermal errors and acknowledgement

Thermal errors reach the main alert tile, bottom message line, fault-detail
menu, audio queue and fault logs. The live renderer combines subsystem errors
with its engine warnings. Thermal-only and desktop UDP data follow the same path.

## Error catalogue

`<KEY>` below is any enabled sensor key in `config/thermal_system.json`, including
both EGTs, turbine outlets, compressor/intercooler temperatures, pre/post WMI,
plenum/runners, head coolant/metal, radiator, oil gallery/cooler/turbo drains and
ambient. The three disabled/reserved channels do not generate sensor warnings.

| Error | Trigger and activation delay | Sound |
| --- | --- | --- |
| THERMAL NODE OFFLINE | No heartbeat within configured timeout, or incompatible protocol; immediate | Existing CAN-timeout voice, otherwise beep |
| <KEY> SENSOR OPEN CIRCUIT | Reported open probe, 0.25 s | Existing sensor-range voice, otherwise beep |
| <KEY> SENSOR SHORT TO GROUND / SHORT TO SUPPLY | Reported short, 0.25 s | Sensor-range voice or beep |
| <KEY> SENSOR OUT OF RANGE | Reported invalid electrical/temperature range, 0.25 s | Sensor-range voice or beep |
| <KEY> SENSOR IMPLAUSIBLE RATE | Reported implausible temperature change, 0.25 s | Sensor-range voice or beep |
| <KEY> SENSOR FRONT END FAULT | Front-end failure or missing valid sample, 0.25 s | Sensor-range voice or beep |
| <KEY> SENSOR STALE | Node online but channel data stale, 0.25 s | Sensor-range voice or beep |
| <KEY> SENSOR NOT CONFIGURED | Enabled channel reports not configured, 0.25 s | Sensor-range voice or beep |
| <KEY> TEMP HIGH | Valid value at/above configured warning but below critical, 1 s | EGT voice for exhaust, overheating voice for head/radiator, intake-hot voice for charge path; otherwise beep |
| <KEY> TEMP CRITICAL | Valid value at/above configured critical temperature; immediate, replaces HIGH | Same applicable voice or beep; separate error episode from HIGH |
| <KEY> DEVIATION | Healthy-baseline deviation score at least 80, 2 s | Warning beep |
| HEAD L/R IMBALANCE | Absolute valid head-coolant difference at least 10 C, 2 s | Warning beep |
| IC-L / IC-R PERFORMANCE LOW | Valid effectiveness below 45%, engine load above 50%, 3 s | Warning beep |
| WMI THERMAL RESPONSE LOW | WMI commanded, valid pre/post drop below 2 C, 3 s | Warning beep |

Temperature warning/critical thresholds remain the existing per-sensor
configuration values; no new motor-control calibration is introduced. Derived
thresholds above retain the existing thermal service values (now applied to both
intercoolers). Effectiveness is only evaluated when the input temperatures allow
the existing calculation. Missing baseline data cannot generate a deviation.
These are observed thermal symptoms, not proof of a particular mechanical cause.
The error detail shows the actual channel value/status when available.

Node loss produces one offline warning rather than 29 identical stale-channel
warnings. Temperature/derived conditions stop when their inputs are invalid;
the sensor/offline warning then reports the loss of visibility. Fault conditions
clear as soon as the service observes recovery; activation delays restart on
recurrence. The home alert tile can retain a steady, post-clear display for up to
3.5 seconds. That display hold does not keep audio or ignore state active. At
most two errors are shown together, with a count and rotating pages for larger
batches; the detail menu exposes the complete current list.

## Ignore Error

Open the main alert tile. Left/Right browses errors. Up/Down chooses NEXT ERROR
or IGNORE ERROR; Select activates the highlighted action. IGNORE ERROR opens
an **ARE YOU SURE?** prompt with **CANCEL selected by default**. Change to YES,
IGNORE and press Select to suppress that exact error's current occurrence.
Back cancels. If the selected error resolves while confirmation is open, the
confirmation is cancelled; it cannot silently apply to a later occurrence.

Suppression hides the current error from the main HUD/error menu and cancels its
queued or currently playing audio. It does not alter source telemetry, logging,
thermal pages, ECU/controller protection, or other warnings. It is held only in
memory. When the source condition clears, suppression is removed. If it returns,
the warning displays and sounds again after its normal activation delay. Escalation
from HIGH to CRITICAL has its own identity and is not silenced by ignoring HIGH.

Unmapped errors and unavailable voice clips fall back to the existing
`new_error_sound.wav` warning beep. Audio plays once per visible occurrence;
resolved/ignored errors are removed from the queue before playback.

Run `python tests/run_alert_checks.py` for lifecycle, live-renderer propagation,
confirmation, recurrence and audio queue checks. The existing thermal, dynamics,
Air Shot and CAN-demo regression runners cover the surrounding integrations.
