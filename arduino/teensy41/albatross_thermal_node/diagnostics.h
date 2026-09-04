#pragma once
#include <Arduino.h>

enum class SensorStatus : uint8_t {
  VALID = 0, OPEN_CIRCUIT = 1, SHORT_TO_GROUND = 2, SHORT_TO_SUPPLY = 3,
  OUT_OF_RANGE = 4, IMPLAUSIBLE_RATE = 5, STALE = 6,
  FRONT_END_FAULT = 7, NOT_CONFIGURED = 8,
};

struct SensorRuntime {
  uint16_t raw = 0;
  float instantaneous_c = NAN;
  float filtered_c = NAN;
  float derivative_c_s = 0.0f;
  SensorStatus status = SensorStatus::NOT_CONFIGURED;
  uint32_t last_sample_ms = 0;
};
