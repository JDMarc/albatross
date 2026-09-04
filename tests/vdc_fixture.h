#pragma once
#include <initializer_list>
#include "../arduino/teensy41/albatross_controller_teensy41/vdc.h"
// SYNTHETIC TEST PLANT ONLY. Never included by the vehicle sketch or generator.
inline vdc::Config testCalibration(){
 vdc::Config c;c.validated=true;c.timeout_ms=250;c.self_test_ms=100;c.position_error_ms=150;c.confirm_ms=40;c.touchdown_ms=300;c.boost_delay_ms=100;
 for(auto* p:{&c.aps,&c.tps}){p->low[0]=500;p->high[0]=4500;p->low[1]=4500;p->high[1]=500;p->rail_low=100;p->rail_high=4900;p->error=.05;p->max_rate=100;}
 c.imu_accel_max=100;c.imu_gyro_max=500;c.gravity_tolerance=.2;c.attitude_tau=.2;c.drift_error=20;
 for(float& x:c.gyro_bias)x=0;
 c.speed_floor=2;c.wheel_accel_tau=.08;c.accel_residual=2;c.slip_hysteresis=.02;c.lift_angle=3;c.lift_rate=2;c.lift_accel=1;c.touchdown_angle=1;
 c.torque_rise=2;c.torque_fall=5;c.touchdown_rise=.2;c.weather_slip_factor=.8;c.weather_rise_factor=.8;c.hard_pitch=40;c.hard_pitch_rate=150;
 c.lean_left=c.lean_right=50;c.lean_start_fraction=.6;c.degraded_torque=0;
 c.throttle_min=0;c.throttle_max=80;c.motor_current_max=5;c.position_error=5;
 for(int n=0;n<3;n++){
  auto& a=c.aid[n];a.slip=.12-n*.03;a.slip_gain=3+n;a.rate_gain=.02;a.pitch_target=18-n*4;a.pitch_max=25-n*4;a.pitch_gain=.08;a.pitch_rate_gain=.02;a.pitch_rate_max=40-n*8;a.lean_slip_factor=.6;
  c.rpm_axis[n]=2000+n*3000;
  for(int k=0;k<5;k++){float x=k*.25f;c.curves[n][k]=n==0?x*x:n==1?x:sqrtf(x);c.throttle_map[n][k]=80*x*x;c.boost_map[n][k]=x;}
 }
 return c;
}
