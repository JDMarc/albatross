#include "airshot_config.h"
namespace airshot {
bool validConfig(const Config& c) {
  const float values[]={c.rpm_min,c.rpm_max,c.launch_rpm,c.high_rpm,c.min_tank,c.full_tank,c.min_regulated,c.max_regulated,c.min_headroom,c.min_torque,c.dbw_tolerance,c.min_coolant,c.min_oil,c.boost_start,c.boost_done,c.boost_full,c.spool_rate,c.overboost_margin,c.transient_rate,c.auto_start,c.auto_reset,c.wg_open_limit,c.balance_limit,c.thermal_egt,c.thermal_turbine,c.thermal_charge,c.thermal_ic,c.thermal_head};
  for(float v:values) if(!isfinite(v) || v<0) return false;
  if(c.auto_start>1 || c.auto_reset<0 || c.balance_limit>1 || c.min_torque>100 || c.dbw_tolerance>100 || c.wg_open_limit>100 ||
     c.launch_rpm<c.rpm_min || c.high_rpm>c.rpm_max || c.launch_rpm>=c.high_rpm ||
     c.recovery_ms>3600000 || c.budget_window_ms>3600000 || c.budget_ms>c.budget_window_ms ||
     !c.timeout_ms || c.timeout_ms>500 || !c.request_lease_ms || c.request_lease_ms>500) return false;
  for(float v:c.gear) if(!isfinite(v) || v<0 || v>2) return false;
  for(float v:c.fuel) if(!isfinite(v) || v<0 || v>2) return false;
  for(float v:c.ride) if(!isfinite(v) || v<0 || v>2) return false;
  if(!c.validated || c.stage<2 || c.stage>9 || c.rpm_min<=0 || c.rpm_max<=c.rpm_min ||
     c.min_tank<=0 || c.full_tank<=c.min_tank || c.min_regulated<=0 || c.max_regulated<=c.min_regulated ||
     c.boost_start<=c.boost_done || c.boost_full<c.boost_start || c.spool_rate<=0 ||
     c.min_torque<=0 || c.min_coolant<=0 || c.min_oil<=0 || c.dbw_tolerance<=0 ||
     !c.recovery_ms || !c.budget_ms || c.budget_window_ms<c.budget_ms || !c.taper_ms ||
     c.auto_start<=c.auto_reset || c.transient_rate<=0 || c.overboost_margin<=0 ||
     c.thermal_egt<=0 || c.thermal_turbine<=0 || c.thermal_head<=0 || c.thermal_charge<=0 || c.thermal_ic<=0) return false;
  for(int n=0;n<4;n++) {
    const auto& v=c.valves[n];
    const float vv[]={v.minimum,v.maximum,v.trim,v.opening_ms,v.closing_ms,v.flow_coefficient,v.min_current,v.max_current,v.pressure_reference,c.rpm_axis[n],c.rpm_gain[n]};
    for(float x:vv) if(!isfinite(x) || x<0) return false;
    if(v.opening_ms>1000 || v.closing_ms>1000 || v.pwm_hz>20000 || c.rpm_gain[n]>2) return false;
    if(v.minimum<0 || v.maximum<=0 || v.maximum>1 || v.minimum>v.maximum || v.trim<=0 ||
       !v.pwm_hz || v.max_current<=v.min_current || v.min_current<0 || v.pressure_reference<=0) return false;
    if(n && c.rpm_axis[n]<=c.rpm_axis[n-1]) return false;
  }
  for(const auto& p:c.profiles) if(!isfinite(p.intake) || !isfinite(p.turbine) || !isfinite(p.intake_decay) || p.intake_decay<0 || p.intake_decay>1 || !p.maximum_ms || p.maximum_ms>c.budget_ms || p.intake<0 || p.turbine<0 || p.intake>1 || p.turbine>1) return false;
  return true;
}
float rpmGain(const Config& c,float rpm) {
  if(rpm<=c.rpm_axis[0]) return c.rpm_gain[0];
  for(int n=1;n<4;n++) if(rpm<=c.rpm_axis[n]) return c.rpm_gain[n-1]+(c.rpm_gain[n]-c.rpm_gain[n-1])*(rpm-c.rpm_axis[n-1])/(c.rpm_axis[n]-c.rpm_axis[n-1]);
  return c.rpm_gain[3];
}
}
