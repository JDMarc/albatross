#pragma once
#include <Arduino.h>

enum class SensorTechnology : uint8_t { K_TYPE, IAT_NTC, COOLANT_NTC, PT1000, DISABLED };
enum class SourceBus : uint8_t { MAX31856, ADS7953, NONE };

struct SensorConfig {
  uint8_t id;
  const char* key;
  SensorTechnology technology;
  SourceBus bus;
  uint8_t channel;
  uint16_t sample_period_ms;
  uint16_t report_period_ms;
  float filter_tau_s;
  float derivative_tau_s;
  float minimum_c;
  float maximum_c;
  uint16_t raw_minimum;
  uint16_t raw_maximum;
  bool enabled;
};

constexpr size_t THERMAL_SENSOR_COUNT = 32;
extern const SensorConfig SENSOR_CONFIG[THERMAL_SENSOR_COUNT];
