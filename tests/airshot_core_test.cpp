#include "../arduino/teensy41/albatross_controller_teensy41/airshot_controller.h"
#include <assert.h>
#include <stdio.h>
#include "../arduino/teensy41/albatross_controller_teensy41/airshot_fields.h"
using namespace airshot;
// Synthetic plant fixture only. These are NOT vehicle calibration values.
Config fixture() {
 Config c;c.validated=true;c.stage=8;c.auto_shadow=false;c.require_wmi=true;
 c.recovery_ms=500;c.budget_window_ms=10000;c.budget_ms=3000;c.taper_ms=100;
 c.rpm_min=2000;c.rpm_max=10000;c.launch_rpm=3000;c.high_rpm=8000;
 c.min_tank=40;c.full_tank=180;c.min_regulated=25;c.max_regulated=100;c.min_headroom=5;
 c.min_torque=30;c.dbw_tolerance=5;c.min_coolant=60;c.min_oil=70;
 c.boost_start=3;c.boost_done=1;c.boost_full=10;c.spool_rate=100;c.overboost_margin=3;
 c.transient_rate=20;c.auto_start=.4;c.auto_reset=.2;c.wg_open_limit=20;c.balance_limit=.1;
 c.thermal_egt=950;c.thermal_turbine=900;c.thermal_head=180;c.thermal_charge=180;c.thermal_ic=100;
 for(int n=0;n<7;n++)c.gear[n]=1;
 for(int n=0;n<6;n++)c.fuel[n]=c.ride[n]=1;
 for(int n=0;n<4;n++){c.rpm_axis[n]=2000+n*2500;c.rpm_gain[n]=1;c.valves[n].pwm_hz=100;c.valves[n].minimum=.05;c.valves[n].maximum=.9;c.valves[n].trim=1-n*.04;c.valves[n].min_current=.1;c.valves[n].max_current=3;c.valves[n].pressure_reference=60;}
 for(auto& p:c.profiles){p.intake=.6;p.turbine=.8;p.intake_decay=.8;p.maximum_ms=1000;}
 return c;
}
Inputs healthy() {
 Inputs i;i.now=1000;i.rpm=4500;i.gear=3;i.fuel=2;i.ride_mode=4;i.rider=i.dbw_command=i.dbw_actual=80;
 i.target=15;i.boost[0]=i.boost[1]=5;i.tank=150;i.regulated=60;i.coolant=90;i.oil=100;
 for(int n=0;n<2;n++){i.head[n]=110;i.egt[n]=700;i.turbine[n]=500;i.charge[n]=80;i.ic[n]=40;}
 i.can_valid=i.pressure_valid=i.dbw_valid=i.wg_valid=i.thermal_valid=i.driver_valid=i.wmi_verified=true;i.ecu_protection=false;
 return i;
}
bool closed(const Outputs& o){for(float v:o.valve)if(v!=0)return false;return true;}
void start(Controller& c,Inputs& i){c.setMode(Mode::MANUAL);c.update(i);i.manual=true;i.now+=5;c.update(i);i.now+=30;c.update(i);assert(c.output().state==State::FIRING);}
int main(){
 auto cfg=fixture();assert(validConfig(cfg));assert(!validConfig(Config{}));
 // A recent follow-up uses RECOVERY; later unrelated requests use RPM profiles.
 for(int rollover=0;rollover<2;rollover++) for(int scenario=0;scenario<5;scenario++) {
  Controller c(cfg);auto i=healthy();if(rollover)i.now=0xfffffe00u;start(c,i);
  c.setMode(Mode::OFF);i.now+=100;c.update(i);uint32_t ended=i.now;
  i.manual=false;i.now+=30;c.update(i);i.now+=30;c.update(i);
  i.now=ended+(scenario==0?cfg.recovery_ms:2*cfg.recovery_ms);
  i.rpm=scenario==2?2500:scenario==3?9000:4500;
  if(scenario==4)i.boost[0]=0;
  start(c,i);
  Profile expected=scenario==0?Profile::RECOVERY:scenario==2?Profile::LAUNCH:scenario==3?Profile::HIGH_RPM:scenario==4?Profile::LEFT_LAG:Profile::MID_TRANSIENT;
  assert(c.output().profile==expected);
 }
 // Usage before OFF counts; crossing the old fixed boundary cannot replenish it.
 {
  auto c0=cfg;c0.budget_window_ms=1000;c0.budget_ms=200;c0.recovery_ms=50;
  for(auto& p:c0.profiles)p.maximum_ms=200;
  Controller c(c0);auto i=healthy();i.now=1800;start(c,i);
  i.now+=150;c.setMode(Mode::OFF);c.update(i);
  i.manual=false;i.now+=5;c.update(i);i.now+=30;c.update(i);
  i.now+=30;start(c,i);i.now+=50;
  assert(closed(c.update(i)) && c.output().reason==Reason::BUDGET);
 }
 // Taper consumes budget too; it cannot extend the permitted time allowance.
 {
  auto c0=cfg;c0.budget_ms=200;
  for(auto& p:c0.profiles)p.maximum_ms=200;
  Controller c(c0);auto i=healthy();start(c,i);
  i.manual=false;i.now+=100;c.update(i);i.now+=30;c.update(i);
  assert(c.output().state==State::TAPERING);
  i.now+=70;assert(closed(c.update(i)) && c.output().reason==Reason::BUDGET);
 }
 {auto bad=cfg;bad.boost_start=NAN;assert(!validConfig(bad));bad=cfg;bad.gear[1]=NAN;assert(!validConfig(bad));}
 {auto c=cfg;assert(!setField(c,0,0.5));assert(!setField(c,1,258));assert(!setField(c,6,-1));assert(!setField(c,4,7.5));}
 {auto c0=cfg;c0.stage=4;Controller c(c0);auto i=healthy();c.setMode(Mode::AUTO);i.rider=i.dbw_actual=i.dbw_command=40;c.update(i);i.now+=50;i.rider=i.dbw_actual=i.dbw_command=80;assert(c.update(i).accepted);}
 {auto c0=cfg;c0.auto_shadow=true;Controller c(c0);auto i=healthy();start(c,i);assert(c.output().shadow && closed(c.output()));}
 {Controller c(cfg);auto i=healthy();start(c,i);c.setMode(Mode::OFF);i.now+=5;assert(closed(c.update(i)));}
 for(int f=0;f<4;f++){Controller c(cfg);auto i=healthy();start(c,i);if(f==0)i.rider=NAN;if(f==1)i.target=NAN;if(f==2)i.wg_position[0]=NAN;if(f==3)i.rpm=NAN;i.now+=5;assert(closed(c.update(i)));}
 {Controller c(cfg);auto i=healthy();i.manual=true;c.update(i);i.now+=50;assert(closed(c.update(i)));assert(c.output().reason==Reason::OFF);}
 {Controller c(cfg);auto i=healthy();start(c,i);auto o=c.output();assert(o.valve[0]!=o.valve[1] && o.valve[1]!=o.valve[2]);i.boost[0]=i.boost[1]=15;i.now+=5;c.update(i);i.now+=100;assert(closed(c.update(i)));}
 {Controller c(cfg);auto i=healthy();start(c,i);for(int n=0;n<1000;n++){i.now+=5;c.update(i);}assert(closed(c.output()));assert(c.output().event_id==1);}
 for(int fault=0;fault<12;fault++){
  Controller c(cfg);auto i=healthy();start(c,i);
  switch(fault){case 0:i.can_valid=false;break;case 1:i.pressure_valid=false;break;case 2:i.tank=1;break;case 3:i.driver_faults=1;break;case 4:i.driver_faults=8;break;case 5:i.boost[0]=30;break;case 6:i.tcs=true;break;case 7:i.awc=true;break;case 8:i.wmi_fault=true;break;case 9:i.head[0]=200;break;case 10:i.dbw_command=10;break;case 11:i.ecu_protection=true;break;}
  i.now+=5;assert(closed(c.update(i)));
 }
 {auto c0=cfg;c0.auto_shadow=true;Controller c(c0);auto i=healthy();i.rider=i.dbw_actual=i.dbw_command=40;c.setMode(Mode::AUTO);c.update(i);i.rider=i.dbw_actual=i.dbw_command=80;i.now+=50;auto o=c.update(i);assert(o.accepted && o.shadow && closed(o));assert(o.predicted[0]>0);}
 {Controller c(cfg);auto i=healthy();c.setMode(Mode::AUTO);i.rider=i.dbw_command=i.dbw_actual=40;c.update(i);i.rider=i.dbw_command=i.dbw_actual=80;i.now+=50;assert(c.update(i).accepted);}
 {Controller c(cfg);auto i=healthy();c.setMode(Mode::MANUAL);c.update(i);for(int n=0;n<30;n++){i.manual=!i.manual;i.now+=5;c.update(i);}assert(closed(c.output()));assert(c.output().event_id==0);}
 {Controller c(cfg);auto i=healthy();start(c,i);i.now+=30;i.manual=false;c.update(i);i.now+=30;c.update(i);i.now+=150;c.update(i);i.manual=true;i.now+=5;c.update(i);i.now+=30;assert(closed(c.update(i)));assert(c.output().reason==Reason::RECOVERY);}
 {Controller c(cfg);auto i=healthy();i.boost[0]=0;start(c,i);assert(c.output().profile==Profile::LEFT_LAG);}
 puts("PASS: rolling OFF/taper accounting, recovery expiry/rollover, manual, AUTO, shadow, aborts, hold, bounce, handoff and imbalance");
}
