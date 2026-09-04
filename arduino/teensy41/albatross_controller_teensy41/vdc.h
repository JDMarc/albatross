#pragma once
#include <stdint.h>
#include <math.h>
namespace vdc {
enum class Level:uint8_t {OFF,LOW_AID,MED,HIGH_AID};
enum class State:uint8_t {INIT,SELF_TEST,READY,NORMAL,TCS_MONITOR,TCS_ACTIVE,AWC_TRACKING,AWC_ACTIVE,TCS_AWC_ACTIVE,DEGRADED,FAULT};
enum class Event:uint8_t {NORMAL,ACCELERATING,BRAKING,CORNERING,POSSIBLE_SLIP,CONFIRMED_SLIP,POSSIBLE_WHEELIE,CONTROLLED_WHEELIE,EXCESSIVE_WHEELIE,WHEELIE_TOUCHDOWN,SENSOR_DISAGREEMENT,UNKNOWN_DYNAMIC_STATE,WHEELIE_AND_SLIP};
enum Fault:uint32_t {CALIBRATION=1,FRONT_WSS=2,REAR_WSS=4,IMU_LOST=8,IMU_IMPLAUSIBLE=16,APS_DISAGREEMENT=32,TPS_DISAGREEMENT=64,DBW_COMM=128,DBW_POSITION=256,DBW_DRIVER=512,MS3_LOST=1024,APS_RATE=2048,IMU_DRIFT=4096};
struct PairCalibration {float low[2]={NAN,NAN},high[2]={NAN,NAN},rail_low=NAN,rail_high=NAN,error=NAN,max_rate=NAN;};
struct AidCalibration {float slip=NAN,slip_gain=NAN,rate_gain=NAN,pitch_target=NAN,pitch_max=NAN,pitch_gain=NAN,pitch_rate_gain=NAN,pitch_rate_max=NAN,lean_slip_factor=NAN;};
struct Config {
 bool validated=false; uint32_t timeout_ms=0,self_test_ms=0,position_error_ms=0,confirm_ms=0,touchdown_ms=0,boost_delay_ms=0;
 PairCalibration aps,tps; AidCalibration aid[3];
 float gravity=9.80665f; // physical unit conversion, not a vehicle calibration
 float imu_accel_max=NAN,imu_gyro_max=NAN,gravity_tolerance=NAN,attitude_tau=NAN,gyro_bias[3]={NAN,NAN,NAN},drift_error=NAN;
 float speed_floor=NAN,wheel_accel_tau=NAN,accel_residual=NAN,slip_hysteresis=NAN,lift_angle=NAN,lift_rate=NAN,lift_accel=NAN,touchdown_angle=NAN;
 float torque_rise=NAN,torque_fall=NAN,touchdown_rise=NAN,weather_slip_factor=NAN,weather_rise_factor=NAN;
 float hard_pitch=NAN,hard_pitch_rate=NAN,lean_left=NAN,lean_right=NAN,lean_start_fraction=NAN,degraded_torque=NAN;
 float throttle_min=NAN,throttle_max=NAN,motor_current_max=NAN,position_error=NAN;
 float rpm_axis[3]={NAN,NAN,NAN},torque_axis[5]={0,.25f,.5f,.75f,1};
 float curves[3][5],throttle_map[3][5],boost_map[3][5];
 Config(){for(int n=0;n<3;n++)for(int k=0;k<5;k++)curves[n][k]=throttle_map[n][k]=boost_map[n][k]=NAN;}
};
struct Settings {Level tcs=Level::MED,awc=Level::MED;uint8_t curve=0;bool weather=true;float wheelie_target=NAN,wheelie_max=NAN,lean_left=NAN,lean_right=NAN;};
struct Inputs {
 uint32_t now=0;float front=0,rear=0,rpm=0,boost=0,boost_request=0,engine_limit=1,mode_limit=1;
 float accel[3]={0,0,0},gyro[3]={0,0,0},aps[2]={0,0},tps[2]={0,0},motor_current=0;
 uint8_t gear=0;bool front_valid=false,rear_valid=false,imu_valid=false,aps_valid=false,tps_valid=false,dbw_valid=false,engine_valid=false,driver_fault=false;
 bool rain=false,weather_valid=false; // advisory only; no connectivity dependency
};
struct Output {
 State state=State::INIT;Event event=Event::UNKNOWN_DYNAMIC_STATE;uint32_t faults=0;
 float speed=0,long_accel=0,lateral_accel=0,lean=0,pitch=0,pitch_rate=0,roll_rate=0,yaw_rate=0;
 float slip=0,slip_target=0,slip_rate=0,slip_confidence=0,wheelie_confidence=0,front_contact=0,sensor_confidence=0;
 float rider=0,permitted=0,tcs_limit=1,awc_limit=1,lean_limit=1,engine_limit=0,mode_limit=0;
 float throttle_target=0,throttle_actual=0,boost_target=0,air_margin=0,wheelie_target=0,wheelie_max=0;
 bool front_airborne=false,tcs_active=false,awc_active=false,air_allowed=false,dbw_enable=false;
};
inline float clamp(float x,float lo=0,float hi=1){return x<lo?lo:x>hi?hi:x;}
bool valid(const Config&);
float curve(const float* x,const float* y,int count,float input);
class Controller {
 public: explicit Controller(const Config& cfg):c(cfg){} Settings settings;Output out;
 const Output& update(const Inputs&);
 private:Config c;bool initialized=false,armed=false,attitude_initialized=false,pairs_previous=false,lift=false,slipping=false;uint32_t last=0,healthy_since=0,slip_since=0,touchdown_until=0,error_since=0,limiting_since=0;
 uint32_t latched=0;float last_front=0,last_rear=0,front_accel=0,rear_accel=0,last_aps=0,last_tps=0,last_slip=0,estimated_speed=0;
};
// Contract helper for a dedicated DBW node. It does not drive any motor pins.
// The actual dedicated controller must apply its own TPS/current checks too.
class CommandWatchdog {
 uint32_t at=0;uint8_t seq=0;bool seen=false;
 public:bool accept(uint8_t next,uint32_t now){if(seen && uint8_t(next-seq)==0)return false;if(seen && uint8_t(next-seq)>=128 && now-at<1000)return false;seq=next;at=now;seen=true;return true;}
 bool live(uint32_t now,uint32_t timeout)const{return seen && timeout && now-at<=timeout;}
};
}
