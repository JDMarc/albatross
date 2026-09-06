"""Bench observations and synthetic exercises, never vehicle calibration.

SIM exercises use a deliberately simple plant, not the production VDC or a
validated actuator model. LIVE and REPLAY cannot invoke those exercises.
"""
from collections import deque
from dataclasses import dataclass
import math

MODES = ('SIM', 'LIVE', 'REPLAY')
AXES = ('DBW', 'EWG LEFT', 'EWG RIGHT')
SCENARIOS = ('NORMAL', 'SLOW MOTOR', 'STUCK MOTOR', 'FEEDBACK LOSS', 'DRIVER FAULT')


@dataclass(frozen=True)
class Reading:
    value: float
    unit: str
    at: float
    source: str
    valid: bool = True
    max_age: float = .3  # display freshness only; not an actuator watchdog


class BenchModel:
    def __init__(self, mode='SIM'):
        if mode not in MODES:
            raise ValueError('Unknown source')
        self.mode = mode
        self.time = 0.0
        self.readings = {}
        self.events = deque(maxlen=100)
        self.event_count = 0
        self.trace = deque(maxlen=1200)  # nominal 60 seconds at 20 Hz
        self.state = 'DISARMED' if mode == 'SIM' else 'OBSERVING'
        self.reason = 'No hardware output exists in this application'
        self.axis = 0
        self.scenario = 0
        self.limit = 25.0
        self.duration = 5.0
        self.armed_until = 0.0
        self.started = None
        self.exercise = None
        self.sim_position = [0.0, 0.0, 0.0]
        self.frames = 0
        self.rejected = 0
        self.transport_error = ''
        self.fault_names = []
        self.results = []
        self.result_count = 0
        self.last_error = 0.0
        self.progress = 0.0

    def event(self, text):
        self.event_count += 1
        self.events.appendleft((self.time, text))

    def put(self, key, value, unit, *, source=None, valid=True, max_age=.3):
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            valid = False
            value = 0.0
        self.readings[key] = Reading(value, unit, self.time,
                                     source or self.mode, valid, max_age)

    def get(self, key):
        r = self.readings.get(key)
        if r is None or not r.valid or not 0 <= self.time-r.at <= r.max_age:
            return None
        return r.value

    def quality(self, key):
        r = self.readings.get(key)
        if r is None:
            return 'MISSING'
        if not r.valid:
            return 'INVALID'
        return 'FRESH' if self.get(key) is not None else 'STALE'

    def configure(self, *, axis=None, scenario=None, limit=None, duration=None):
        if self.mode != 'SIM' or self.state in ('ARMED', 'RUNNING'):
            return False
        if axis is not None and (type(axis) is not int or not 0 <= axis < len(AXES)): return False
        if scenario is not None and (type(scenario) is not int or not 0 <= scenario < len(SCENARIOS)): return False
        if limit is not None and (type(limit) not in (int,float) or not math.isfinite(limit) or not 0 <= limit <= 100): return False
        if duration is not None and (type(duration) not in (int,float) or not math.isfinite(duration) or not 1 <= duration <= 15): return False
        if axis is not None:
            if type(axis) is not int or not 0 <= axis < len(AXES): return False
            self.axis = axis
        if scenario is not None:
            if type(scenario) is not int or not 0 <= scenario < len(SCENARIOS): return False
            self.scenario = scenario
        if limit is not None:
            if not math.isfinite(limit) or not 0 <= limit <= 100: return False
            self.limit = float(limit)
        if duration is not None:
            if not math.isfinite(duration) or not 1 <= duration <= 15: return False
            self.duration = float(duration)
        return True

    def arm(self):
        if self.mode != 'SIM' or self.state == 'RUNNING': return False
        self.state = 'ARMED'
        self.armed_until = self.time + 10
        self.reason = 'Simulation armed for 10 seconds; select RUN separately'
        self.event('SIM ARM / no physical output')
        return True

    def run(self):
        if self.mode != 'SIM' or self.state != 'ARMED' or self.time >= self.armed_until:
            return False
        self.state = 'RUNNING'
        self.reason = 'Synthetic exercise running / SPACE cancels / no physical output'
        self.started = self.time
        self.exercise = dict(axis=self.axis, scenario=self.scenario,
                             limit=self.limit, duration=self.duration)
        self.last_error = 0.0
        self.progress = 0.0
        self.event('SIM RUN / '+AXES[self.axis]+' / '+SCENARIOS[self.scenario])
        return True

    def stop(self, reason='Operator stopped exercise'):
        if self.mode != 'SIM':
            self.event('Read-only source: no hardware stop transmitted')
            self.reason = 'Use the independent physical kill circuit; this monitor cannot stop hardware'
            return False
        if self.state == 'RUNNING':
            self._result('ABORTED', reason)
        self.state = 'DISARMED'
        self.reason = reason
        self.event('SIM DISARM / '+reason)
        return True

    def _result(self, outcome, reason):
        self.result_count += 1
        self.results.append(dict(number=self.result_count, source='SIMULATED', outcome=outcome,
            reason=reason, axis=AXES[self.exercise['axis']], scenario=SCENARIOS[self.exercise['scenario']],
            limit_pct=self.exercise['limit'], duration_s=self.time-self.started,
            max_tracking_error_pct=self.last_error, at_s=self.time,
            hardware_acceptance=False))
        self.results = self.results[-100:]
        self.event('SIM '+outcome+' / '+reason)

    def tick(self, now):
        if not math.isfinite(now) or now < self.time:
            raise ValueError('Bench clock must be finite and monotonic')
        elapsed = now-self.time
        self.time = now
        if self.mode == 'SIM':
            if self.state == 'ARMED' and now >= self.armed_until:
                self.stop('Arm window expired')
            if self.state == 'RUNNING' and elapsed > .25:
                self.stop('Application scheduling gap')
            target = 0.0
            if self.state == 'RUNNING':
                self.progress = min(1.0, (now-self.started)/self.exercise['duration'])
                target = self.exercise['limit']*math.sin(math.pi*self.progress)**2
                if self.progress >= 1:
                    self._result('COMPLETED', 'Synthetic exercise ended; not a hardware PASS')
                    self.state = 'DISARMED'
                    self.reason = 'Exercise complete; re-arm required'
                    target = 0.0
            scenario = SCENARIOS[self.scenario]
            for n, axis in enumerate(AXES):
                requested = target if n == self.axis else 0.0
                speed = 8.0 if n == self.axis and scenario == 'SLOW MOTOR' else 100.0
                delta = max(-speed*elapsed, min(speed*elapsed, requested-self.sim_position[n]))
                if n == self.axis and scenario in ('STUCK MOTOR', 'DRIVER FAULT'):
                    delta = 0.0
                self.sim_position[n] += delta
                feedback = not (n == self.axis and scenario == 'FEEDBACK LOSS')
                self.put(axis+' target', requested, '%')
                self.put(axis+' actual', self.sim_position[n], '%', valid=feedback)
                self.put(axis+' current', abs(delta)*.08, 'A')
                if n == self.axis and self.state == 'RUNNING':
                    self.last_error = max(self.last_error, abs(requested-self.sim_position[n]))
            if self.state == 'RUNNING' and scenario in ('FEEDBACK LOSS', 'DRIVER FAULT'):
                self.stop('Synthetic '+scenario.lower())
                self.put(AXES[self.axis]+' target', 0.0, '%')
            self.put('RPM', 0, 'rpm')
            self.put('Battery', 13.5, 'V')
            self.fault_names = [] if scenario == 'NORMAL' else ['SIM FIXTURE: '+scenario]
        axis = AXES[self.axis]
        self.trace.append((now, self.get(axis+' target'), self.get(axis+' actual'), self.get(axis+' current')))

    def report(self):
        return dict(schema='albatross-bench-report-1', source=self.mode, hardware_acceptance=False,
            warning='No actuator commands sent. SIM plant is illustrative, not the production controller.',
            time_s=self.time, frames=self.frames, rejected=self.rejected,
            transport_error=self.transport_error, result_count=self.result_count,
            results=list(self.results), results_truncated=self.result_count > len(self.results),
            signals={key:dict(value=self.get(key), unit=r.unit, quality=self.quality(key),
                              source=r.source, age_s=self.time-r.at)
                     for key, r in self.readings.items()}, events=list(self.events))
