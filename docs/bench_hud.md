# Bench-only HUD

Run `python bench_hud.py` from the repository root. This is a separate Pygame
application; the riding HUD and firmware are unchanged. Requires Python 3.10+
and Pygame; live observation additionally requires python-can and the appropriate
adapter driver/backend. Install these in your normal project environment.

## What this version does

- **SIM (default):** offline illustrative DBW / left EWG / right EWG plant.
  Select a normal, slow, stuck, feedback-loss, or driver-fault fixture; choose
  synthetic peak request and duration; confirm ARM, then separately select RUN.
  The bounded rise/return exercise is recorded, never marked hardware PASS.
- **LIVE:** application-level receive-only CAN inspection. Shows reported
  actuator requests/positions, optional observed DBWX2 raw channels/current,
  RPM, voltage, Air Shot pressures/current, and fault-manager telemetry.
- **REPLAY:** offline raw CAN JSONL replay with recorded timing and stale-data
  behavior. This is telemetry playback, not production-controller execution.
- Signal inspector with individual age, validity and source; event view;
  timestamped JSON session reports and trace CSV exports.

There is **no hardware transmitter, actuator jog, configuration upload, fault
clear, or road-enable bypass**. The simulated values are not calibration values.
The SIM plant is not the production VDC and cannot validate throttle-body safety,
return springs, actuator travel, pressure plumbing, or controller tuning.
No connected hardware has been tested by these software checks.

## Launch examples

```sh
python bench_hud.py --theme amber
python bench_hud.py --live --interface socketcan --channel can0 --bitrate 500000
python bench_hud.py --live --interface slcan --channel COM5 --bitrate 500000
python bench_hud.py --replay logs/bench/your_recording.jsonl
python bench_hud.py --controller 0
python bench_hud.py --screenshot bench-preview.png
```

COM5 is an example, not an automatically detected adapter. Use your actual
backend/channel and verified bus rate. CAN adapters may still acknowledge traffic
electrically: this is **not a guarantee of hardware listen-only mode**. Configure
that separately if your adapter supports it. Do not connect a synthetic telemetry
sender such as `can_demo_controls.py` to a safety-critical live vehicle bus.
An adapter error remains an error; LIVE never silently switches to simulation.

`--native-v092` enables passive decoding of the repository's DBWX2 0.92 read
exchanges, only after you verify that firmware layout applies. Node defaults are
local 9 / DBWX2 10; override with `--local-node` / `--dbwx2-node`. Existing hardware
must generate the poll request and matching reply: this tool sends neither.
APS/TPS raw values are **counts**, not fabricated volts or calibrated angles.
The VDC position display requires fresh nonfaulted position-related status;
the raw reported value is separately labeled unverified because unavailable
values can be serialized as zero. Freshness is not proof of physical accuracy.

## Controls

- Tab or 1–4: page. Up/down: exercise item. Left/right: edit, or signal paging.
- Enter: select/confirm. Arming expires after 10 seconds; RUN is separate.
- Mouse: select an item, click again to activate; arrows edit. Confirmation uses
  Enter (or controller select), not an accidental second mouse click.
- Space/Escape: stop/cancel **SIM only**. E: export. Q: quit.
- Replay: P pauses the playback clock; paused readings do not age until resumed.
- Optional `--controller INDEX`: hat navigation, button 0 select, 1 cancel,
  4 next page. Mapping is bench-specific, not the riding grip mapping.

Focus loss, controller removal, exit, or a scheduling gap aborts a running SIM
exercise. None of these stop physical hardware. Use the independent physical
kill circuit for that. Never rely on the Pi/window as the actuator safety loop.

## Recording and limits

Default output is `logs/bench` (override `--logs`). Live recordings preserve raw
classic-CAN frames and direction/format flags. SIM journals contain synthetic
samples; they cannot be replayed as wire data. Reports include up to 100 exercise
results/events and the current axis's last 1,200 trace samples; the log records
the session samples. Local configuration hashes identify files on this computer,
not confirmed flashed firmware. Queue/write failures are displayed and marked
in reports; inspect these flags before relying on a recording.

Replay accepts chronological `time_s` or `monotonic_s`, integer `frame_id`, hex
`data`, and optional boolean `extended`, `remote`, `error`, plus `direction`.
Limit: 200,000 classic-CAN frames, 256 KiB per row. The display freshness budget
is 300 ms, not an engineering watchdog or a new controller calibration.

## Next powered-bench phase

Before adding movement commands, establish verified pinouts and supply protection,
current-limited power, mechanical guarding, independent kill, actuator bounds and
controller identity. Implement a controller-side bench protocol with local
physical authorization, bounded requests, timeout/return behavior and measured
feedback. DBWX2 must retain its own protection authority; the Pi must not close
the throttle or wastegate motor loop. Pneumatic testing additionally needs rated
plumbing, pressure relief and verified normally-closed isolation.

Validation: `python tests/run_bench_checks.py`. No powered-hardware acceptance or
road-readiness conclusion follows from passing these tests.
