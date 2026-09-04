#include "sensor_conversion.h"
#include <math.h>

float convertAnalogToCelsius(const SensorConfig& config, uint16_t raw) {
  if (raw == 0 || raw >= 4095) return NAN;
  if (config.technology == SensorTechnology::PT1000) {
    constexpr float excitation_a = 0.0005f;
    const float voltage = raw * 3.3f / 4095.0f;
    const float resistance = voltage / excitation_a;
    return (resistance / 1000.0f - 1.0f) / 0.00385f;
  }
  const float pullup = config.technology == SensorTechnology::COOLANT_NTC ? 2490.0f : 10000.0f;
  const float r0 = config.technology == SensorTechnology::COOLANT_NTC ? 2500.0f : 10000.0f;
  const float t0_c = config.technology == SensorTechnology::COOLANT_NTC ? 80.0f : 25.0f;
  const float beta = config.technology == SensorTechnology::COOLANT_NTC ? 3977.0f : 3435.0f;
  const float resistance = pullup * raw / (4095.0f - raw);
  const float inverse_k = 1.0f / (t0_c + 273.15f) + logf(resistance / r0) / beta;
  return 1.0f / inverse_k - 273.15f;
}
