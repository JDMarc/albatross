#include "../arduino/teensy41/albatross_controller_teensy41/fault_manager/policies.h"
#include "../arduino/teensy41/albatross_controller_teensy41/fault_manager/signals.h"
#include <assert.h>
#include <stdio.h>
#include <initializer_list>
using namespace fm;
int main(){
 Manager m;loadPolicies(m);auto id=Id::COOLING;auto& p=m.policies[unsigned(id)];
 p.confirm_ms=100;p.recover_ms=200;p.recovery_configured=true;p.torque=.5f;
 auto tick=[&](uint32_t t,Evidence e){m.begin(t);m.observe(id,e);return m.finish(t);};
 assert(tick(100,Evidence::BAD).torque==1);assert(m.faults[unsigned(id)].state==Life::SUSPECT);
 assert(tick(150,Evidence::GOOD).torque==1); // isolated noise does not mitigate
 tick(200,Evidence::BAD);assert(tick(300,Evidence::BAD).torque==.5f);
 assert(m.faults[unsigned(id)].episodes==1);
 tick(400,Evidence::GOOD);assert(tick(550,Evidence::UNKNOWN).torque==.5f);
 tick(600,Evidence::GOOD);assert(tick(799,Evidence::GOOD).torque==.5f);assert(tick(800,Evidence::GOOD).torque==1);
 tick(900,Evidence::BAD);tick(1000,Evidence::BAD);assert(m.faults[unsigned(id)].episodes==2);
 m.begin(1001);m.observe(Id::AIR_DRIVER,true);m.observe(id,false);assert(m.finish(1001).available&TCS);
 m.begin(1300);m.observe(Id::AIR_DRIVER,false);m.finish(1300);assert(m.faults[unsigned(Id::AIR_DRIVER)].active);
 Manager pi;loadPolicies(pi);pi.begin(1);pi.observe(Id::PI_OFFLINE,true);auto caps=pi.finish(1);
 assert(caps.available==ALL&&caps.torque==1&&caps.ride==Ride::FULL);
 Manager thermal;loadPolicies(thermal);thermal.begin(1);thermal.observe(Id::THERMAL_OFFLINE,true);caps=thermal.finish(1);
 assert(caps.boost==8&&caps.torque==1&&(caps.available&TCS)&&!(caps.available&AIR_AUTO));
 Manager missing;loadPolicies(missing);missing.begin(1);missing.observe(Id::FUEL_DP_CRITICAL,true);caps=missing.finish(1);
 assert(caps.missing_calibration&&caps.torque==0);
 Manager wrap;auto& wp=wrap.policies[0];wp.confirm_ms=20;
 Manager latch;latch.policies[0].clear=Clear::CLEAR_AFTER_KEY_CYCLE;
 latch.begin(1);latch.observe(Id::PI_OFFLINE,true);latch.finish(1);
 latch.begin(2);latch.observe(Id::PI_OFFLINE,false);latch.finish(2);
 assert(latch.faults[0].active&&latch.faults[0].state==Life::LATCHED);
 wrap.begin(0xfffffff0);wrap.observe(Id::PI_OFFLINE,true);wrap.finish(0xfffffff0);
 wrap.begin(10);wrap.observe(Id::PI_OFFLINE,true);wrap.finish(10);assert(wrap.faults[0].active);
 Signal s[2]={{80,10,100,Quality::VALID,true},{90,10,100,Quality::VALID,true}};
 auto estimate=conservativeTemperature(s,2,20);assert(estimate.value==90&&estimate.quality==Quality::ESTIMATED);
 assert(conservativeTemperature(s,2,111).quality==Quality::INVALID);
 Band band;band.trip=10;band.clear=12;band.high=false;
 assert(band.evaluate(11,true,false)==Evidence::GOOD);assert(band.evaluate(11,true,true)==Evidence::BAD);
 assert(band.evaluate(NAN,true,false)==Evidence::UNKNOWN);
 assert(fuelDifferential(s[1],s[0],20,band,false)==Evidence::BAD);
 Rate rate;assert(!isfinite(rate.update(s[0],20)));s[0].value=70;s[0].at=20;
 assert(rate.update(s[0],20)==-1000);assert(rate.update(s[0],21)==-1000);
 assert(!isfinite(rate.update(s[0],121)));
 Response response;assert(response.check(true,Evidence::BAD,0,50,true)==Result::REQUESTED);
 assert(response.check(true,Evidence::BAD,50,50,true)==Result::FAILED);
 assert(response.check(true,Evidence::GOOD,60,50,true)==Result::CONTAINED);
 assert(response.check(true,Evidence::UNKNOWN,70,50,true)==Result::UNAVAILABLE);
 Baseline base;base.observe(10,false,true);assert(base.samples==0);base.observe(10,true,true);base.observe(20,true,false);assert(base.mean==10);
 SubsystemMonitors monitors;loadMonitors(monitors);Manager optional;loadPolicies(optional);
 optional.begin(1);monitors.update(optional,1);assert(optional.finish(1).available==ALL);
 for(bool reverse:{false,true}){
   optional.begin(2);
   optional.observe(Id::COOLING,reverse?Evidence::UNKNOWN:Evidence::GOOD);
   optional.observe(Id::COOLING,reverse?Evidence::GOOD:Evidence::UNKNOWN);
   assert(optional.faults[unsigned(Id::COOLING)].evidence==Evidence::UNKNOWN);
   optional.observe(Id::COOLING,Evidence::BAD);
   optional.observe(Id::COOLING,Evidence::UNKNOWN);
   assert(optional.faults[unsigned(Id::COOLING)].evidence==Evidence::BAD);
 }
 optional.begin(3);
 optional.observe(Id::FUEL_DP_LOW,true);optional.observe(Id::LAMBDA_LEFT,true);optional.observe(Id::LAMBDA_RIGHT,true);
 monitors.update(optional,3);assert(optional.faults[unsigned(Id::FUEL_DP_CRITICAL)].evidence==Evidence::UNKNOWN);
 monitors.fuel_fusion_enabled=true;monitors.update(optional,3);
 assert(optional.faults[unsigned(Id::FUEL_DP_CRITICAL)].evidence==Evidence::BAD);
 // Synthetic fixture values only, never written to commissioning configuration.
 SubsystemMonitors fuel;Manager fuel_manager;
 auto& fuel_rule=fuel.rules[0];fuel_rule.enabled=true;fuel_rule.fault=Id::FUEL_DP_LOW;
 fuel_rule.a=Channel::RAIL;fuel_rule.b=Channel::MAP;fuel_rule.operation=Operation::DIFFERENCE;
 fuel_rule.band={30,35,false};fuel_rule.confirm_ms=100;
 auto& fuel_policy=fuel_manager.policies[unsigned(Id::FUEL_DP_LOW)];
 fuel_policy.remove=AIR_AUTO;fuel_policy.recovery_configured=true;fuel_policy.recover_ms=100;
 fuel.signals[unsigned(Channel::RPM)]={3000,100,1000,Quality::VALID,true};
 fuel.signals[unsigned(Channel::RAIL)]={40,100,1000,Quality::VALID,true};
 fuel.signals[unsigned(Channel::MAP)]={15,100,1000,Quality::VALID,true};
 fuel_manager.begin(100);fuel.update(fuel_manager,100);assert(fuel_manager.finish(100).available&AIR_AUTO);
 fuel_manager.begin(200);fuel.update(fuel_manager,200);assert(!(fuel_manager.finish(200).available&AIR_AUTO));
 fuel_manager.begin(1200);fuel.update(fuel_manager,1200);assert(!(fuel_manager.finish(1200).available&AIR_AUTO));
 for(auto channel:{Channel::RPM,Channel::RAIL,Channel::MAP})fuel.signals[unsigned(channel)].at=1200;
 fuel.signals[unsigned(Channel::RAIL)].value=60;
 fuel_manager.begin(1201);fuel.update(fuel_manager,1201);fuel_manager.finish(1201);
 fuel_manager.begin(1301);fuel.update(fuel_manager,1301);assert(fuel_manager.finish(1301).available&AIR_AUTO);
 puts("PASS fault lifecycle, recurrence, unknown-data hold, latch, capabilities, rollover, substitution, hysteresis, rate, response and disabled monitors");
}
