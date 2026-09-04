#include "airshot_safety.h"
namespace airshot {
Reason permissive(const Config& c,const Inputs& i) {
  if(!validConfig(c)) return Reason::UNCALIBRATED;
  if(!i.can_valid) return Reason::CAN_STALE;
  if(!isfinite(i.rpm) || !isfinite(i.speed) || !isfinite(i.target)) return Reason::CAN_STALE;
  if(!i.pressure_valid || !isfinite(i.tank) || !isfinite(i.regulated)) return Reason::PRESSURE_SENSOR;
  if(!i.driver_valid || i.driver_faults) return Reason::DRIVER;
  if(!i.dbw_valid || !isfinite(i.rider) || !isfinite(i.dbw_command) || !isfinite(i.dbw_actual)) return Reason::DBW;
  if(i.ecu_protection) return Reason::ECU_PROTECTION;
  if(i.traction_fault || i.tcs) return Reason::TRACTION;
  if(i.awc) return Reason::WHEELIE;
  if(!i.thermal_valid) return Reason::THERMAL;
  for(int n=0;n<2;n++) {
    if(!isfinite(i.boost[n]) || !isfinite(i.head[n]) || !isfinite(i.egt[n]) || !isfinite(i.turbine[n]) ||
       !isfinite(i.charge[n]) || !isfinite(i.ic[n])) return Reason::THERMAL;
    if(i.head[n]>=c.thermal_head || i.egt[n]>=c.thermal_egt || i.turbine[n]>=c.thermal_turbine ||
       i.charge[n]>=c.thermal_charge || i.ic[n]>=c.thermal_ic) return Reason::THERMAL;
    if(i.boost[n]>i.target+c.overboost_margin) return Reason::OVERBOOST;
  }
  if(i.tank<c.min_tank) return Reason::LOW_PRESSURE;
  if(i.regulated<c.min_regulated || i.regulated>c.max_regulated || i.regulated<meanBoost(i)+c.min_headroom) return Reason::REGULATOR;
  if(!isfinite(i.coolant) || !isfinite(i.oil) || i.coolant<c.min_coolant || i.oil<c.min_oil) return Reason::ENGINE_COLD;
  if(i.rpm<c.rpm_min || i.rpm>c.rpm_max) return Reason::RPM_RANGE;
  if(i.gear==0 || i.gear>6 || i.fuel>=6 || i.ride_mode>=6 || c.gear[i.gear]<=0 || c.fuel[i.fuel]<=0 || c.ride[i.ride_mode]<=0) return Reason::FUEL;
  if(i.rider<c.min_torque) return Reason::TORQUE_LOW;
  // Permitted torque dominates rider grip, including after-throttle air injection.
  if(i.dbw_command<c.min_torque || i.dbw_command+c.dbw_tolerance<i.rider ||
     fabsf(i.dbw_actual-i.dbw_command)>c.dbw_tolerance) return Reason::DBW;
  if(!i.wg_valid || !isfinite(i.wg_position[0]) || !isfinite(i.wg_position[1]) || !isfinite(i.wg_command[0]) || !isfinite(i.wg_command[1]) || i.wg_position[0]>c.wg_open_limit || i.wg_position[1]>c.wg_open_limit ||
     i.wg_command[0]>c.wg_open_limit || i.wg_command[1]>c.wg_open_limit) return Reason::WASTEGATE;
  if(c.require_wmi && (!i.wmi_verified || i.wmi_fault)) return Reason::WMI;
  return Reason::NONE;
}
}
