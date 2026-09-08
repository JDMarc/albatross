#pragma once
#include "sensor_config.h"
float convertNtcToCelsius(const SensorConfig& config,int16_t raw,float excitation_v);
float convertRtdToCelsius(uint16_t raw);
