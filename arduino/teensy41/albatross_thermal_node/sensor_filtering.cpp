#include "sensor_filtering.h"
#include <math.h>

void updateFilter(SensorRuntime& runtime, float sample, float dt, float tau, float derivative_tau) {
  const float previous = runtime.filtered_c;
  runtime.instantaneous_c = sample;
  if (!isfinite(previous) || dt <= 0.0f) { runtime.filtered_c = sample; runtime.derivative_c_s = 0.0f; return; }
  const float alpha = dt / (tau + dt);
  runtime.filtered_c += alpha * (sample - runtime.filtered_c);
  const float raw_rate = (runtime.filtered_c - previous) / dt;
  const float d_alpha = dt / (derivative_tau + dt);
  const float deadbanded = fabsf(raw_rate) < 0.05f ? 0.0f : raw_rate;
  runtime.derivative_c_s += d_alpha * (deadbanded - runtime.derivative_c_s);
}
