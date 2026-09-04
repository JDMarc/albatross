#pragma once
#include "sensor_config.h"
#include "diagnostics.h"

SensorStatus validateAnalog(const SensorConfig& config, uint16_t raw, float temperature_c, float previous_c, float dt_s);
