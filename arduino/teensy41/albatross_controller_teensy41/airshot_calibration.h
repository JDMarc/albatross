#pragma once
#include "airshot_config.h"
namespace airshot {
inline Config calibration() {
  Config c;
  c.validated = true;
  c.stage = 4;
  c.auto_shadow = false;
  c.require_wmi = true;
  c.fire_pin = -1;
  c.service_pin = -1;
  return c;
}
}
