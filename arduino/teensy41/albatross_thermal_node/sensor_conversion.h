#pragma once
#include "sensor_config.h"

float convertAnalogToCelsius(const SensorConfig& config, uint16_t raw);
