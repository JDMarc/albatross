#pragma once
#include "airshot_types.h"
namespace airshot {
// No pneumatic hardware calibration has been validated. Zero values prevent
// enabling deployment; test fixtures provide synthetic values only.
struct ValveCalibration {
  int pin=-1; uint32_t pwm_hz=0;
  float minimum=0, maximum=0, trim=1, opening_ms=0, closing_ms=0;
  float flow_coefficient=0, min_current=0, max_current=0, pressure_reference=0;
};
struct ProfileCalibration { float intake=0, turbine=0, intake_decay=0; uint32_t maximum_ms=0; };
struct Config {
  bool validated=false, auto_shadow=true, require_wmi=true;
  uint8_t stage=0; int fire_pin=-1, service_pin=-1;
  uint32_t debounce_ms=25, timeout_ms=250, request_lease_ms=150;
  uint32_t recovery_ms=0, budget_window_ms=0, budget_ms=0, taper_ms=0;
  float rpm_min=0, rpm_max=0, launch_rpm=0, high_rpm=0;
  float min_tank=0, full_tank=0, min_regulated=0, max_regulated=0, min_headroom=0;
  float min_torque=0, dbw_tolerance=0, min_coolant=0, min_oil=0;
  float boost_start=0, boost_done=0, boost_full=0, spool_rate=0, overboost_margin=0;
  float transient_rate=0, auto_start=0, auto_reset=0, wg_open_limit=0, balance_limit=0;
  float thermal_egt=0, thermal_turbine=0, thermal_charge=0, thermal_ic=0, thermal_head=0;
  float gear[7]={0}, fuel[6]={0}, ride[6]={0};
  float rpm_axis[4]={0}, rpm_gain[4]={0};
  ValveCalibration valves[4];
  ProfileCalibration profiles[6];
  uint32_t version=2;
};
bool validConfig(const Config& c);
float rpmGain(const Config& c,float rpm);
}
