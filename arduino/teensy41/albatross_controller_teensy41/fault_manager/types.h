#pragma once
#include <stdint.h>
#include <math.h>
namespace fm {
enum class Quality:uint8_t {VALID,ESTIMATED,DEGRADED,INVALID};
enum class Life:uint8_t {NORMAL,SUSPECT,CONFIRMED,ACTIVE,MITIGATING,DEGRADED,RECOVERING,CLEARED,LATCHED};
enum class Severity:uint8_t {ADVISORY,WARNING,CRITICAL};
enum class Ride:uint8_t {FULL,DEGRADED,LIMP,STOP_REQUIRED,ENGINE_PROTECT};
enum class Clear:uint8_t {AUTO_CLEAR,CLEAR_AFTER_STABLE,CLEAR_AFTER_KEY_CYCLE,SERVICE_CLEAR,LATCHED};
enum class Evidence:uint8_t {UNKNOWN,GOOD,BAD};
enum class Result:uint8_t {NOT_REQUESTED,REQUESTED,CONTAINED,FAILED,UNAVAILABLE};
enum Capability:uint32_t {HIGH_BOOST=1,AIR_AUTO=2,AIR_MANUAL=4,WMI_POWER=8,TCS=16,AWC=32,LEAN=64,FULL_RPM=128,FULL_DBW=256,NORMAL_LOAD=512,ALL=1023};
enum Action:uint16_t {CLOSE_AIR=1,ISOLATE_AIR=2,STOP_COMPRESSOR=4,OPEN_EWG=8,FAN_MAX=16,SHED_OPTIONAL=32,ECU_PROTECT_REQUEST=64};
enum class Id:uint8_t {PI_OFFLINE,THERMAL_OFFLINE,THERMAL_BLIND,THERMAL_HOT,EGT_SENSOR,COOLANT_SENSOR,MAT_SENSOR,
 MS3_OFFLINE,MAP_INVALID,IMU_FAULT,FRONT_WSS,REAR_WSS,DBW_FAULT,WMI_FAILED,AIR_DRIVER,AIR_STUCK,
 FUEL_DP_LOW,FUEL_DP_CRITICAL,OIL_LOW,OIL_CRITICAL,EWG_LEFT,EWG_RIGHT,OVERBOOST,BOOST_UNCONTAINED,
 CHARGING,COOLING,LAMBDA_LEFT,LAMBDA_RIGHT,CYLINDER_LEFT,CYLINDER_RIGHT,KNOCK,TURBO_OVERSPEED,COUNT};
constexpr unsigned count=unsigned(Id::COUNT);
struct Policy {
 uint32_t remove=0;uint16_t actions=0;Severity severity=Severity::WARNING;Ride ride=Ride::DEGRADED;
 Clear clear=Clear::CLEAR_AFTER_STABLE;
 uint32_t confirm_ms=0,recover_ms=0;bool recovery_configured=false;
 float torque=NAN,boost=NAN,rpm=NAN;
};
struct Fault {
 Life state=Life::NORMAL;Severity worst=Severity::ADVISORY;Evidence evidence=Evidence::UNKNOWN;
 Result result=Result::NOT_REQUESTED;
 uint32_t first_seen=0,last_seen=0,episodes=0,total_active_ms=0,since=0;
 uint32_t primary_signal=0,corroborating=0,suspected=0;
 uint8_t confidence=0;bool active=false,timing=false,stable=false;
};
struct Capabilities {
 uint32_t available=ALL,inhibited=0,degraded=0;uint16_t actions=0;
 float torque=1,boost=INFINITY,rpm=INFINITY;Ride ride=Ride::FULL;
 bool missing_calibration=false;
};
struct Signal {
 float value=NAN;uint32_t at=0,max_age_ms=0;Quality quality=Quality::INVALID;bool seen=false;
 bool valid(uint32_t now)const{return seen&&max_age_ms&&now-at<=max_age_ms&&quality==Quality::VALID&&isfinite(value);}
};
inline float minimum(float a,float b){return a<b?a:b;}
}
