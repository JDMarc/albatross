#include <initializer_list>
#include <stdio.h>
#include <assert.h>
#include <string.h>
#include "vdc_fixture.h"
using namespace vdc;
static const char* scenarios[]={
 "normal acceleration","normal corner exit","rear wheelspin upright","rear wheelspin leaned",
 "small intentional wheelie","large wheelie","rapid wheelie","long controlled wheelie",
 "front wheel slows while airborne","wheelie + rear slip simultaneously","wheelie touchdown","crest/bump causing front unload",
 "front WSS failure","rear WSS failure","IMU dropout","IMU drift","APS mismatch","TPS mismatch","DBW motor stuck","DBW motor slow",
 "TCS intervention during boost","AWC intervention during Air Shot","wet-weather context","phone disconnect","internet loss"};
int main(int argc,char** argv){
 setvbuf(stdout,nullptr,_IONBF,0);
 Config cfg=testCalibration();assert(valid(cfg));assert(!valid(Config{}));
 {auto bad=cfg;bad.curves[0][2]=NAN;assert(!valid(bad));}
 CommandWatchdog watchdog;assert(watchdog.accept(1,100));assert(!watchdog.accept(1,110));assert(watchdog.live(150,100));assert(!watchdog.live(201,100));
 bool csv=argc>1&&strcmp(argv[1],"--csv")==0;
 if(csv)puts("scenario,ms,front,rear,pitch,lean,slip,slip_confidence,wheelie_confidence,rider,permitted,tcs,awc,boost,air,state,event,faults");
 for(int test=0;test<25;test++){
  Controller control(cfg);control.settings.curve=1;control.settings.awc=Level::LOW_AID;
  Inputs i;i.front=i.rear=20;i.rpm=5000;i.gear=3;i.boost_request=15;i.accel[2]=cfg.gravity;
  i.front_valid=i.rear_valid=i.imu_valid=i.aps_valid=i.tps_valid=i.dbw_valid=i.engine_valid=true;
  i.aps[0]=3700;i.aps[1]=1300;i.tps[0]=500;i.tps[1]=4500;
  float truth_pitch=0,truth_lean=0;bool saw_slip=false,saw_lift=false,saw_awc=false,saw_touchdown=false,saw_fault=false,saw_air=false;float previous_permitted=0;
  for(int tick=0;tick<700;tick++){
   if(test!=16||tick<100){i.aps[0]=tick<20?500:3700;i.aps[1]=tick<20?4500:1300;}
   i.now=1000+tick*10;float t=(tick-100)*.01f;bool event=t>=0;
   float ax=event&&test!=15?2:0,pr=0,rr=0;
   if(event){
    i.front+=ax*.01f;i.rear+=ax*.01f;
    if(test==1||test==3){rr=t<1?20:0;}
    bool wheelie=test>=4&&test<=10||test==21;
    if(wheelie){pr=t<.6f?(test==6?80:20):0;i.front-=.09f;if(test==10&&t>2&&truth_pitch>0)pr=-15;}
    if((test==5||test==21)&&t>.6&&t<1.4)pr=30;
    if(test==11){pr=t<.1?20:t<.2?-20:0;ax=0;}
    if(test==2||test==3||test==20||(test==9&&t>1)){if(t<2)i.rear+=.15f;}
    if(test==12)i.front_valid=false;if(test==13)i.rear_valid=false;if(test==14)i.imu_valid=false;
    if(test==15)pr=15;
    if(test==16)i.aps[1]=3000;if(test==17)i.tps[1]=3000;
    if(test==22){i.weather_valid=true;i.rain=true;}
    if(test==23||test==24){i.weather_valid=t<.5;i.rain=true;}
   }
   truth_pitch+=pr*.01f;truth_lean+=rr*.01f;
   const float rad=3.14159265f/180;
   i.accel[0]=ax-cfg.gravity*sinf(truth_pitch*rad);i.accel[1]=cfg.gravity*sinf(truth_lean*rad)*cosf(truth_pitch*rad);i.accel[2]=cfg.gravity*cosf(truth_pitch*rad)*cosf(truth_lean*rad);
   i.gyro[1]=pr;i.gyro[0]=rr;
   if(test==15&&event){i.accel[0]=0;i.accel[1]=0;i.accel[2]=cfg.gravity;}
   if(test!=17){float actual=control.out.throttle_target/cfg.throttle_max;if(event&&(test==18||test==19))actual=test==18?0:actual*.2f;i.tps[0]=500+4000*actual;i.tps[1]=4500-4000*actual;}
   const auto& o=control.update(i);
   assert(isfinite(o.permitted)&&o.permitted>=0&&o.permitted<=1);
   assert(o.permitted<=o.rider+.0001f || o.state==State::SELF_TEST);
   if(o.faults){
    assert(!o.air_allowed&&o.boost_target==0);
    const uint32_t dynamics_only=FRONT_WSS|REAR_WSS|IMU_LOST|IMU_IMPLAUSIBLE|IMU_DRIFT;
    if(o.faults&~dynamics_only)assert(!o.dbw_enable&&o.permitted==0);
    else assert(o.permitted<=cfg.degraded_torque);
   }
   if(test==15)assert(fabsf(o.pitch)<cfg.drift_error); // slow pitch drift corrected by trusted gravity
   if(o.tcs_active||o.awc_active)assert(!o.air_allowed);
   if(event){saw_slip|=o.slip_confidence==1;saw_lift|=o.front_airborne;saw_awc|=o.awc_active;saw_touchdown|=o.event==Event::WHEELIE_TOUCHDOWN;saw_fault|=o.faults!=0;saw_air|=o.front_airborne&&o.air_allowed;}
   if(test==10&&o.event==Event::WHEELIE_TOUCHDOWN)assert(o.permitted<=previous_permitted+cfg.touchdown_rise*.01f+.0001f);
   previous_permitted=o.permitted;
   if(csv&&tick%5==0)printf("%s,%u,%.4f,%.4f,%.4f,%.4f,%.4f,%.2f,%.2f,%.4f,%.4f,%.4f,%.4f,%.4f,%d,%u,%u,%u\n",scenarios[test],i.now,i.front,i.rear,o.pitch,o.lean,o.slip,o.slip_confidence,o.wheelie_confidence,o.rider,o.permitted,o.tcs_limit,o.awc_limit,o.boost_target,o.air_allowed,unsigned(o.state),unsigned(o.event),unsigned(o.faults));
  }
  if(test==2||test==3||test==9||test==20)assert(saw_slip);
  if(test>=4&&test<=10||test==21)assert(saw_lift);
  if(test==4||test==7||test==8){assert(!saw_slip);assert(!saw_awc);assert(saw_air);}
  if(test==5||test==6||test==21)assert(saw_awc);
  if(test==10)assert(saw_touchdown);
  if(test>=12&&test<=19&&test!=15)assert(saw_fault);
  if(test==23||test==24)assert(!saw_fault);
  if(!csv)printf("PASS %s\n",scenarios[test]);
 }
}
