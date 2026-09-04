#pragma once
#include <stdint.h>
#include <math.h>
namespace airshot {
enum class Mode : uint8_t { OFF, MANUAL, AUTO };
enum class State : uint8_t { DISABLED, READY, ARMED, REQUESTED, PRECHECK, FIRING, TAPERING, RECOVERY, INHIBITED, FAULT };
enum class Reason : uint8_t { NONE, OFF, UNCALIBRATED, CAN_STALE, PRESSURE_SENSOR, LOW_PRESSURE, REGULATOR, ENGINE_COLD, RPM_RANGE, TORQUE_LOW, DBW, TRACTION, WHEELIE, THERMAL, WMI, ECU_PROTECTION, DRIVER, ALREADY_BOOSTED, RECOVERY, MAX_DURATION, RELEASED, SPOOL_COMPLETE, OVERBOOST, BUDGET, WASTEGATE, SHADOW, SERVICE, FUEL };
enum class CompressorState : uint8_t { OFF, FILLING, COOLDOWN, FAULT };
enum class Profile : uint8_t { LAUNCH, MID_TRANSIENT, RECOVERY, HIGH_RPM, LEFT_LAG, RIGHT_LAG };
struct Inputs {
  uint32_t now = 0;
  float rpm=0, speed=0, rider=0, dbw_command=0, dbw_actual=0;
  float boost[2]={0,0}, target=0, tank=0, regulated=0;
  float wg_command[2]={0,0}, wg_position[2]={0,0}, turbo_speed[2]={NAN,NAN};
  float coolant=NAN, oil=NAN, head[2]={NAN,NAN}, egt[2]={NAN,NAN}, turbine[2]={NAN,NAN}, charge[2]={NAN,NAN}, ic[2]={NAN,NAN};
  float currents[4]={NAN,NAN,NAN,NAN};
  uint8_t gear=0, fuel=0, ride_mode=0, driver_faults=0;
  bool can_valid=false, pressure_valid=false, dbw_valid=false, wg_valid=false, thermal_valid=false;
  bool driver_valid=false, tcs=false, awc=false, traction_fault=false, ecu_protection=true;
  bool wmi_verified=false, wmi_fault=false, manual=false, service_key=false;
  bool vdc_valid=false,vdc_permitted=true;float vdc_margin=1;
};
struct Outputs {
  State state=State::DISABLED;
  Reason reason=Reason::OFF;
  Profile profile=Profile::MID_TRANSIENT;
  float demand=0, valve[4]={0,0,0,0}, predicted[4]={0,0,0,0}, available=0, boost_rate=0;
  uint32_t event_id=0, last_duration=0;
  float tank_before=0, tank_after=0, pressure_used=0;
  bool auto_request=false, manual_request=false, accepted=false, shadow=false;
};
inline float clamp(float x,float lo,float hi) { return x<lo?lo:(x>hi?hi:x); }
inline float meanBoost(const Inputs& i) { return (i.boost[0]+i.boost[1])*0.5f; }
}
