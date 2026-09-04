#pragma once
#include "diagnostics.h"

void updateFilter(SensorRuntime& runtime, float sample_c, float dt_s, float tau_s, float derivative_tau_s);
