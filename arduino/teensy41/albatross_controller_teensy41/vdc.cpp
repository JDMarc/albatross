#include "vdc.h"
namespace vdc {
static bool finitePositive(float x){return isfinite(x)&&x>0;}
static bool pairValid(const PairCalibration& p){return isfinite(p.low[0])&&isfinite(p.low[1])&&isfinite(p.high[0])&&isfinite(p.high[1])&&p.low[0]!=p.high[0]&&p.low[1]!=p.high[1]&&finitePositive(p.error)&&finitePositive(p.max_rate)&&isfinite(p.rail_low)&&p.rail_high>p.rail_low;}
bool valid(const Config& c){
 if(c.torque_axis[0]!=0||c.torque_axis[4]!=1)return false;
 for(int n=1;n<5;n++)if(!isfinite(c.torque_axis[n])||c.torque_axis[n]<=c.torque_axis[n-1])return false;
 if(!c.validated||!pairValid(c.aps)||!pairValid(c.tps)||!c.timeout_ms||c.timeout_ms>500||!c.self_test_ms||!c.confirm_ms||!c.touchdown_ms||!c.position_error_ms||!c.boost_delay_ms)return false;
 const float positive[]={c.imu_accel_max,c.imu_gyro_max,c.gravity_tolerance,c.attitude_tau,c.drift_error,c.speed_floor,c.wheel_accel_tau,c.accel_residual,c.slip_hysteresis,c.lift_angle,c.lift_rate,c.lift_accel,c.touchdown_angle,c.torque_rise,c.torque_fall,c.touchdown_rise,c.weather_slip_factor,c.weather_rise_factor,c.hard_pitch,c.hard_pitch_rate,c.lean_left,c.lean_right,c.lean_start_fraction,c.motor_current_max,c.position_error};
 for(float v:positive)if(!finitePositive(v))return false;
 for(float v:c.gyro_bias)if(!isfinite(v))return false;
 if(!isfinite(c.degraded_torque)||c.degraded_torque<0||c.degraded_torque>1||c.weather_slip_factor>1||c.weather_rise_factor>1||c.lean_start_fraction>=1||c.touchdown_angle>=c.lift_angle)return false;
 if(!isfinite(c.throttle_min)||c.throttle_min<0||!isfinite(c.throttle_max)||c.throttle_max<=c.throttle_min)return false;
 for(int n=0;n<3;n++){
  const auto& a=c.aid[n];const float av[]={a.slip,a.slip_gain,a.rate_gain,a.pitch_target,a.pitch_max,a.pitch_gain,a.pitch_rate_gain,a.pitch_rate_max,a.lean_slip_factor};
  for(float v:av)if(!finitePositive(v))return false;
  if(a.pitch_target>=a.pitch_max||a.pitch_max>c.hard_pitch||a.pitch_rate_max>c.hard_pitch_rate||a.lean_slip_factor>1)return false;
  if(!finitePositive(c.rpm_axis[n])||(n&&c.rpm_axis[n]<=c.rpm_axis[n-1]))return false;
  for(int k=0;k<5;k++){
   if(!isfinite(c.curves[n][k])||c.curves[n][k]<0||c.curves[n][k]>1||(k&&c.curves[n][k]<c.curves[n][k-1]))return false;
   if(!isfinite(c.throttle_map[n][k])||c.throttle_map[n][k]<c.throttle_min||c.throttle_map[n][k]>c.throttle_max||(k&&c.throttle_map[n][k]<c.throttle_map[n][k-1]))return false;
   if(!isfinite(c.boost_map[n][k])||c.boost_map[n][k]<0||c.boost_map[n][k]>1||(k&&c.boost_map[n][k]<c.boost_map[n][k-1]))return false;
  }
  if(c.curves[n][0]!=0||c.curves[n][4]!=1)return false;
 }
 return true;
}
float curve(const float* x,const float* y,int n,float v){if(v<=x[0])return y[0];for(int k=1;k<n;k++)if(v<=x[k])return y[k-1]+(y[k]-y[k-1])*(v-x[k-1])/(x[k]-x[k-1]);return y[n-1];}
static float surface(const Config& c,const float map[3][5],float rpm,float torque){float rows[3];for(int n=0;n<3;n++)rows[n]=curve(c.torque_axis,map[n],5,torque);return curve(c.rpm_axis,rows,3,rpm);}
static bool normalize(const PairCalibration& c,const float* raw,float& position){
 float v[2];for(int n=0;n<2;n++){if(!isfinite(raw[n])||raw[n]<=c.rail_low||raw[n]>=c.rail_high)return false;v[n]=(raw[n]-c.low[n])/(c.high[n]-c.low[n]);if(v[n]<-c.error||v[n]>1+c.error)return false;}
 if(fabsf(v[0]-v[1])>c.error)return false;position=clamp((v[0]+v[1])*.5f);return true;
}
const Output& Controller::update(const Inputs& i){
 const bool first=!initialized;float dt=first?0:float(i.now-last)/1000;last=i.now;initialized=true;
 out.faults=latched;out.air_allowed=false;out.dbw_enable=false;out.tcs_active=out.awc_active=false;
 if(!valid(c)){out=Output{};out.state=State::INIT;out.faults=CALIBRATION;return out;}
 if(dt>float(c.timeout_ms)/1000){out.faults|=IMU_LOST;dt=0;}
 if(!i.engine_valid||!isfinite(i.engine_limit)||!isfinite(i.mode_limit)||!isfinite(i.rpm)||!isfinite(i.boost)||!isfinite(i.boost_request)||i.boost_request<0)out.faults|=MS3_LOST;
 if(!i.front_valid||!isfinite(i.front)||i.front<0)out.faults|=FRONT_WSS;
 if(!i.rear_valid||!isfinite(i.rear)||i.rear<0)out.faults|=REAR_WSS;
 if(!i.imu_valid)out.faults|=IMU_LOST;
 for(int k=0;k<3;k++)if(!isfinite(i.accel[k])||!isfinite(i.gyro[k])||fabsf(i.accel[k])>c.imu_accel_max||fabsf(i.gyro[k])>c.imu_gyro_max)out.faults|=IMU_IMPLAUSIBLE;
 float aps=0,tps=0;
 if(!i.aps_valid||!normalize(c.aps,i.aps,aps))out.faults|=APS_DISAGREEMENT;
 if(!i.tps_valid||!normalize(c.tps,i.tps,tps))out.faults|=TPS_DISAGREEMENT;
 if(dt>0 && pairs_previous && i.aps_valid && fabsf(aps-last_aps)/dt>c.aps.max_rate)out.faults|=APS_RATE;
 if(dt>0 && pairs_previous && i.tps_valid && fabsf(tps-last_tps)/dt>c.tps.max_rate)out.faults|=TPS_DISAGREEMENT;
 pairs_previous=i.aps_valid&&i.tps_valid;
 last_aps=aps;last_tps=tps;
 if(!i.dbw_valid)out.faults|=DBW_COMM;
 if(i.dbw_valid&&(i.driver_fault||!isfinite(i.motor_current)||i.motor_current<0||i.motor_current>c.motor_current_max))out.faults|=DBW_DRIVER;
 out.throttle_actual=c.throttle_min+tps*(c.throttle_max-c.throttle_min);
 if(i.tps_valid && healthy_since && i.now-healthy_since>=c.self_test_ms && fabsf(out.throttle_actual-out.throttle_target)>c.position_error){if(!error_since)error_since=i.now;if(i.now-error_since>=c.position_error_ms)out.faults|=DBW_POSITION;}else error_since=0;
 uint32_t latch_mask=DBW_POSITION|DBW_DRIVER|APS_RATE;
 if(i.aps_valid)latch_mask|=APS_DISAGREEMENT;
 if(i.tps_valid)latch_mask|=TPS_DISAGREEMENT;
 latched|=out.faults&latch_mask;
 const uint32_t hard=out.faults&(APS_DISAGREEMENT|TPS_DISAGREEMENT|DBW_COMM|DBW_POSITION|DBW_DRIVER|MS3_LOST|APS_RATE);
 if(out.faults){
  healthy_since=0;armed=false;attitude_initialized=false;out.state=hard?State::FAULT:State::DEGRADED;out.event=Event::UNKNOWN_DYNAMIC_STATE;out.sensor_confidence=0;
  out.permitted=0;out.throttle_target=c.throttle_min;out.boost_target=0;out.air_margin=0;out.front_contact=0;
  return out; // no unsupported torque-to-throttle fallback during sensor loss
 }
 out.sensor_confidence=1;
 if(!healthy_since)healthy_since=i.now;
 const float rad=3.14159265358979323846f/180;
 float norm=sqrtf(i.accel[0]*i.accel[0]+i.accel[1]*i.accel[1]+i.accel[2]*i.accel[2]);
 float ap=atan2f(-i.accel[0],sqrtf(i.accel[1]*i.accel[1]+i.accel[2]*i.accel[2]))/rad;
 float ar=atan2f(i.accel[1],i.accel[2])/rad;
 if(!attitude_initialized){out.pitch=ap;out.lean=ar;estimated_speed=i.front;last_front=i.front;last_rear=i.rear;front_accel=rear_accel=0;attitude_initialized=true;dt=0;}
 float roll=out.lean*rad,pitch=out.pitch*rad;
 if(fabsf(cosf(pitch))<.001f){out.faults|=IMU_IMPLAUSIBLE;out.state=State::DEGRADED;out.permitted=out.boost_target=0;out.throttle_target=c.throttle_min;return out;}
 float p=i.gyro[0]-c.gyro_bias[0],q=i.gyro[1]-c.gyro_bias[1],r=i.gyro[2]-c.gyro_bias[2];
 // Body angular rates are not Euler rates when the bike is leaned.
 out.pitch_rate=cosf(roll)*q-sinf(roll)*r;
 out.roll_rate=p+sinf(roll)*tanf(pitch)*q+cosf(roll)*tanf(pitch)*r;
 out.yaw_rate=(sinf(roll)*q+cosf(roll)*r)/cosf(pitch);
 out.pitch+=out.pitch_rate*dt;out.lean+=out.roll_rate*dt;
 if(dt>0 && fabsf(norm-c.gravity)<c.gravity_tolerance && fabsf(rear_accel)<c.lift_accel){
  if(fabsf(out.pitch-ap)>c.drift_error||fabsf(out.lean-ar)>c.drift_error){out.faults|=IMU_DRIFT;out.state=State::DEGRADED;out.permitted=out.boost_target=0;out.throttle_target=c.throttle_min;return out;}
  float gain=dt/(c.attitude_tau+dt);out.pitch+=(ap-out.pitch)*gain;out.lean+=(ar-out.lean)*gain;
 }
 out.long_accel=i.accel[0]+c.gravity*sinf(out.pitch*rad);out.lateral_accel=i.accel[1]-c.gravity*sinf(out.lean*rad)*cosf(out.pitch*rad);
 if(dt>0){float gain=dt/(c.wheel_accel_tau+dt);front_accel+=gain*((i.front-last_front)/dt-front_accel);rear_accel+=gain*((i.rear-last_rear)/dt-rear_accel);}
 last_front=i.front;last_rear=i.rear;
 bool lift_evidence=out.pitch>c.lift_angle && (out.pitch_rate>c.lift_rate || (lift && out.pitch>c.touchdown_angle)) && (out.long_accel>c.lift_accel || lift);
 if(lift_evidence)lift=true;
 bool touchdown=lift && out.pitch<c.touchdown_angle && out.pitch_rate<=0;
 if(touchdown){lift=false;touchdown_until=i.now+c.touchdown_ms;}
 out.front_airborne=lift;out.wheelie_confidence=lift?1:clamp(out.pitch/c.lift_angle)*clamp(out.pitch_rate/c.lift_rate);
 out.front_contact=lift?0:1;
 estimated_speed=fmaxf(0,estimated_speed+out.long_accel*dt);
 // A slowing airborne front wheel is explicitly excluded from the speed reference.
 if(!lift && int32_t(touchdown_until-i.now)<=0)estimated_speed=i.front;
 else if(fabsf(rear_accel-out.long_accel)<c.accel_residual && !slipping)estimated_speed+=clamp(dt/c.attitude_tau)*(i.rear-estimated_speed);
 out.speed=estimated_speed;out.slip=(i.rear-estimated_speed)/fmaxf(c.speed_floor,estimated_speed);
 out.slip_rate=dt>0?(out.slip-last_slip)/dt:0;last_slip=out.slip;
 int ti=settings.tcs==Level::OFF?1:int(settings.tcs)-1,ai=settings.awc==Level::OFF?1:int(settings.awc)-1;
 const auto& t=c.aid[ti];const auto& a=c.aid[ai];
 out.wheelie_max=isfinite(settings.wheelie_max)?clamp(settings.wheelie_max,c.touchdown_angle,c.hard_pitch):a.pitch_max;
 out.wheelie_target=isfinite(settings.wheelie_target)?clamp(settings.wheelie_target,0,out.wheelie_max):fminf(a.pitch_target,out.wheelie_max);
 float ll=isfinite(settings.lean_left)?clamp(settings.lean_left,1,c.lean_left):c.lean_left;
 float lr=isfinite(settings.lean_right)?clamp(settings.lean_right,1,c.lean_right):c.lean_right;
 float lean_fraction=clamp(fabsf(out.lean)/(out.lean<0?ll:lr));
 bool wet=settings.weather&&i.weather_valid&&i.rain;
 out.slip_target=t.slip*(1-lean_fraction*(1-t.lean_slip_factor))*(wet?c.weather_slip_factor:1);
 float residual=rear_accel-out.long_accel;
 // Divergence needs independent chassis-acceleration evidence; it is never sufficient alone.
 bool evidence=out.slip>out.slip_target && residual>c.accel_residual && i.rear>c.speed_floor;
 if(evidence){if(!slip_since)slip_since=i.now;if(i.now-slip_since>=c.confirm_ms)slipping=true;}else slip_since=0;
 if(out.slip<out.slip_target-c.slip_hysteresis)slipping=false;
 out.slip_confidence=slipping?1:evidence?.5f:0;
 out.rider=curve(c.torque_axis,c.curves[settings.curve<3?settings.curve:0],5,aps);
 out.tcs_limit=settings.tcs==Level::OFF||!slipping?1:clamp(1-t.slip_gain*fmaxf(0,out.slip-out.slip_target)-t.rate_gain*fmaxf(0,out.slip_rate));
 float prediction=out.pitch+fmaxf(0,out.pitch_rate)*c.attitude_tau;
 out.awc_limit=settings.awc==Level::OFF?1:clamp(1-a.pitch_gain*fmaxf(0,prediction-out.wheelie_target)-a.pitch_rate_gain*fmaxf(0,out.pitch_rate-a.pitch_rate_max));
 if((settings.awc!=Level::OFF&&out.pitch>=out.wheelie_max)||out.pitch>=c.hard_pitch||out.pitch_rate>=c.hard_pitch_rate)out.awc_limit=0; // hard protection survives AWC OFF
 out.lean_limit=1-clamp((lean_fraction-c.lean_start_fraction)/(1-c.lean_start_fraction));
 out.engine_limit=clamp(i.engine_limit);out.mode_limit=clamp(i.mode_limit);
 float permitted=fminf(out.rider,fminf(out.tcs_limit,fminf(out.awc_limit,fminf(out.lean_limit,fminf(out.engine_limit,out.mode_limit)))));
 bool landing=int32_t(touchdown_until-i.now)>0;
 float rise=(landing?c.touchdown_rise:c.torque_rise)*(wet?c.weather_rise_factor:1);
 if(!armed&&(aps>c.aps.error||tps>c.tps.error))healthy_since=i.now;
 if(i.now-healthy_since<c.self_test_ms){out.state=State::SELF_TEST;out.permitted=0;out.throttle_target=c.throttle_min;out.boost_target=0;return out;}
 armed=true; // release grip and verify closed throttle before first/recovered authority
 bool emergency=out.engine_limit==0||out.awc_limit==0;
 out.permitted=emergency?0:clamp(permitted,out.permitted-c.torque_fall*dt,out.permitted+rise*dt);
 // Rider release and engine/mode ceilings are not defeated by a dynamics ramp.
 out.permitted=fminf(out.permitted,fminf(out.rider,fminf(out.engine_limit,out.mode_limit)));
 out.throttle_target=surface(c,c.throttle_map,i.rpm,out.permitted);out.dbw_enable=true;
 bool limiting=permitted<out.rider;
 if(limiting){if(!limiting_since)limiting_since=i.now;}else limiting_since=0;
 float boost_torque=(limiting_since&&i.now-limiting_since<c.boost_delay_ms)?out.rider:out.permitted;
 out.boost_target=emergency?0:i.boost_request*surface(c,c.boost_map,i.rpm,boost_torque);
 out.tcs_active=out.tcs_limit<out.rider;out.awc_active=out.awc_limit<out.rider;
 out.air_margin=clamp((out.wheelie_target-prediction)/fmaxf(c.lift_angle,out.wheelie_target));
 if(!lift)out.air_margin=1;
 out.air_allowed=!limiting&&!landing&&out.air_margin>0;
 out.event=slipping?(lift?Event::WHEELIE_AND_SLIP:Event::CONFIRMED_SLIP):landing?Event::WHEELIE_TOUCHDOWN:lift?(out.awc_active?Event::EXCESSIVE_WHEELIE:Event::CONTROLLED_WHEELIE):evidence?Event::POSSIBLE_SLIP:out.wheelie_confidence>0?Event::POSSIBLE_WHEELIE:fabsf(out.lean)>c.lift_angle?Event::CORNERING:out.long_accel>c.lift_accel?Event::ACCELERATING:out.long_accel<-c.lift_accel?Event::BRAKING:Event::NORMAL;
 out.state=out.tcs_active?(out.awc_active?State::TCS_AWC_ACTIVE:State::TCS_ACTIVE):out.awc_active?State::AWC_ACTIVE:lift?State::AWC_TRACKING:settings.tcs==Level::OFF?State::NORMAL:State::TCS_MONITOR;
 return out;
}
}
