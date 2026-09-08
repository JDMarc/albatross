// Reuse synthetic fixtures, never vehicle calibration.
#include <initializer_list>
#define main existing_airshot_tests
#include "airshot_core_test.cpp"
#undef main
#include "../arduino/teensy41/albatross_controller_teensy41/airshot_priming.h"
int main(){
 auto c=fixture();auto i=healthy();i.vdc_valid=true;
 PrimeConfig p;p.commissioned=true;p.tank_rearm_psi=60;p.stable_ms=20;p.fill_timeout_ms=100;
 for(uint32_t start:{1000u,0xfffffff0u}){
   Priming a;i.now=start;i.regulated=0;i.rider=i.dbw_command=i.dbw_actual=0;i.rpm=1000;i.gear=0;
   a.update(p,c,i,Mode::MANUAL,true);assert(a.open&&!a.ready);
   i.now=start+5;i.regulated=60;a.update(p,c,i,Mode::MANUAL,true);assert(!a.ready);
   i.now=start+25;a.update(p,c,i,Mode::MANUAL,true);assert(a.ready&&a.open);
   i.now=start+30;i.regulated=0;a.update(p,c,i,Mode::MANUAL,true);assert(a.fault()&&!a.open);
   i.now=start+200;i.regulated=60;a.update(p,c,i,Mode::AUTO,true);assert(a.fault()&&!a.ready);
   a.update(p,c,i,Mode::OFF,true);assert(!a.open&&!a.fault());
 }
 i=healthy();i.vdc_valid=true;
 {Priming a;i.regulated=0;a.update(p,c,i,Mode::AUTO,true);i.now+=100;a.update(p,c,i,Mode::AUTO,true);assert(a.fault()&&!a.open);}
 i=healthy();i.vdc_valid=true;
 {Priming a;a.update(p,c,i,Mode::AUTO,true);i.now+=20;a.update(p,c,i,Mode::AUTO,true);assert(a.ready);
  i.tank=50;i.now+=5;a.update(p,c,i,Mode::AUTO,true);assert(a.open&&a.ready); // hysteresis hold
  i.tank=39;i.now+=5;a.update(p,c,i,Mode::AUTO,true);assert(!a.open&&!a.ready);
  i.tank=50;i.now+=5;a.update(p,c,i,Mode::AUTO,true);assert(!a.open);}
 i=healthy();i.vdc_valid=true;
 for(int n=0;n<5;n++){
   Priming a;auto x=i;a.update(p,c,x,Mode::AUTO,true);x.now+=20;a.update(p,c,x,Mode::AUTO,true);assert(a.ready);
   bool allow=true;Mode mode=Mode::AUTO;
   if(n==0)x.pressure_valid=false;if(n==1)allow=false;if(n==2)mode=Mode::OFF;
   if(n==3)x.driver_faults=1;if(n==4)x.ecu_protection=true;
   x.now+=5;a.update(p,c,x,mode,allow);assert(!a.open&&!a.ready);
 }
 for(int n=0;n<17;n++){
   auto bad=i;auto cfg=c;auto pc=p;bool permit=true;
   switch(n){case 0:bad.pressure_valid=false;break;case 1:bad.can_valid=false;break;
    case 2:bad.driver_faults=1;break;case 3:bad.dbw_valid=false;break;case 4:bad.tcs=true;break;
    case 5:bad.awc=true;break;case 6:bad.thermal_valid=false;break;case 7:bad.ecu_protection=true;break;
    case 8:bad.regulated=NAN;break;case 9:bad.regulated=101;break;case 10:bad.tank=39;break;
    case 11:bad.tank=50;break;case 12:permit=false;break;case 13:pc.commissioned=false;break;
    case 14:cfg.auto_shadow=true;break;case 15:bad.wmi_fault=true;break;case 16:bad.rpm=0;break;}
   Priming a;a.update(pc,cfg,bad,Mode::AUTO,permit);assert(!a.open&&!a.ready);
 }
 // Metering is physically inhibited until primed, including active-shot abort.
 {Controller ctrl(c);auto x=healthy();x.prime_required=true;x.primed=false;ctrl.setMode(Mode::MANUAL);
  ctrl.update(x);x.manual=true;x.now+=30;ctrl.update(x);x.now+=30;ctrl.update(x);assert(closed(ctrl.output()));
  assert(ctrl.output().reason==Reason::PRIMING);
  x.primed=true;x.manual=false;x.now+=30;ctrl.update(x);x.now+=30;ctrl.update(x);
  x.manual=true;x.now+=30;ctrl.update(x);x.now+=30;ctrl.update(x);assert(!closed(ctrl.output()));
  x.primed=false;x.prime_fault=true;x.now+=5;ctrl.update(x);assert(closed(ctrl.output()));
  assert(ctrl.output().reason==Reason::PRIME_FAULT);}
 puts("PASS priming, no circular low-pressure check, wraparound, timeout latch, OFF reset, inhibits and metering gate");
}
