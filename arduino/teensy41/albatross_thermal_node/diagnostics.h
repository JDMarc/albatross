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
  uint32_t generation = 0;
  uint8_t good_samples = 0;
};

struct AcquisitionSample {
  uint16_t raw = 0;
  uint32_t captured_ms = 0;
  uint32_t generation = 0;
  SensorStatus status = SensorStatus::STALE;
  void set(uint16_t value, uint32_t now, SensorStatus health) {
    raw=value; captured_ms=now; status=health; ++generation;
  }
};
