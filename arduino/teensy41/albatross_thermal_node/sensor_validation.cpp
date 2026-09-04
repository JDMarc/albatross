#include "sensor_validation.h"
#include <math.h>

SensorStatus validateAnalog(const SensorConfig& config, uint16_t raw, float value, float previous, float dt_s) {
  if (!config.enabled) return SensorStatus::NOT_CONFIGURED;
  if (raw < 8) return SensorStatus::SHORT_TO_GROUND;
  if (raw > 4087) return SensorStatus::SHORT_TO_SUPPLY;
  if (raw < config.raw_minimum || raw > config.raw_maximum) return SensorStatus::OPEN_CIRCUIT;
  if (!isfinite(value) || value < config.minimum_c || value > config.maximum_c) return SensorStatus::OUT_OF_RANGE;
  const float maximum_rate = config.technology == SensorTechnology::K_TYPE ? 600.0f : 50.0f;
  if (isfinite(previous) && dt_s > 0.0f && fabsf(value - previous) / dt_s > maximum_rate) return SensorStatus::IMPLAUSIBLE_RATE;
  return SensorStatus::VALID;
}
