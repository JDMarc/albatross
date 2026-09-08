#pragma once
#include "sensor_config.h"
#include "diagnostics.h"
SensorStatus validateTemperature(const SensorConfig&,float value,float previous,float dt_s);
SensorStatus validateNtc(const SensorConfig&,int16_t raw,float excitation_v,float value,float previous,float dt_s);
