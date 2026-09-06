#include <cassert>
#include <cstdio>
#include "../arduino/bench/dbw_bench/bench_core.h"
// SYNTHETIC TEST CONSTANTS ONLY. Never an actuator commissioning profile.
bench::Config fixture(){
 bench::Config c;c.verified=true;c.lease_ms=100;c.feedback_ms=150;c.arm_ms=500;c.run_ms=400;c.tracking_ms=100;
 c.max_pct=30;c.hard_actual_pct=35;c.rise_pct_s=100;c.current_a=2;c.pair_error_pct=5;c.tracking_pct=10;c.start_pct=3;
 c.rail_low=50;c.rail_high=4050;c.tps_closed[0]=100;c.tps_open[0]=3900;c.tps_closed[1]=3900;c.tps_open[1]=100;return c;
}
void feedback(bench::Core& b,uint32_t now,float pct=0){
 for(int n=0;n<4;n++){b.f.at[n]=now;b.f.seen[n]=true;}
 b.f.tps[0]=100+pct*38;b.f.tps[1]=3900-pct*38;b.f.current=.1;b.f.status_bad=b.f.channel_bad=false;
}
void arm(bench::Core& b){feedback(b,1);b.tick(1,true,false);assert(b.arm(b.epoch));}
void start(bench::Core& b){arm(b);feedback(b,2);b.tick(2,true,true);assert(b.hold(b.epoch,1,200));b.tick(3,true,true);assert(b.permit);}
int main(){
 assert(!bench::valid(bench::Config{}));assert(bench::valid(fixture()));
 bench::Core invalid(bench::Config{});invalid.tick(1,true,false);assert(!invalid.arm(1)&&!invalid.permit);
 bench::Core b(fixture());start(b);assert(b.command<=.2f);assert(!b.hold(b.epoch,1,200));assert(!b.hold(b.epoch,2,301));
 b.tick(103,true,true);assert(!b.permit&&b.state==bench::IDLE);assert(!b.hold(1,3,200));
 bench::Core released(fixture());start(released);released.tick(4,true,false);assert(!released.permit&&released.reason==bench::RELEASED);
 bench::Core key(fixture());start(key);key.tick(4,false,true);assert(!key.permit&&key.reason==bench::KEY_OFF);
 bench::Core stale(fixture());start(stale);stale.tick(154,true,true);assert(stale.state==bench::FAULT&&!stale.permit);
 bench::Core current(fixture());start(current);current.f.current=3;current.tick(4,true,true);assert(current.reason==bench::CURRENT);current.stop();assert(current.state==bench::FAULT);
 bench::Core tps(fixture());start(tps);tps.f.tps[1]=2000;tps.tick(4,true,true);assert(tps.reason==bench::TPS);
 bench::Core driver(fixture());start(driver);driver.f.channel_bad=true;driver.tick(4,true,true);assert(driver.reason==bench::DRIVER);
 bench::Core tracking(fixture());start(tracking);
 for(uint32_t t=10;t<350&&tracking.state==bench::ACTIVE;t+=10){feedback(tracking,t);tracking.tick(t,true,true);tracking.hold(tracking.epoch,t,200);}
 assert(tracking.state==bench::FAULT&&tracking.reason==bench::TRACKING);
 bench::Core duration(fixture());start(duration);
 for(uint32_t t=10;t<=410;t+=10){feedback(duration,t,duration.command);duration.tick(t,true,true);duration.hold(duration.epoch,t,200);}
 assert(!duration.permit&&duration.reason==bench::RUN_ENDED);
 bench::Core expiry(fixture());arm(expiry);
 for(uint32_t t=10;t<=510;t+=10){feedback(expiry,t);expiry.tick(t,true,false);}
 assert(expiry.reason==bench::ARM_EXPIRED);
 bench::Core held(fixture());feedback(held,1);held.tick(1,true,true);assert(!held.arm(1));
 bench::Core wrap(fixture());feedback(wrap,0xfffffff0);wrap.tick(0xfffffff0,true,false);assert(wrap.arm(1));
 feedback(wrap,0xfffffff1);wrap.tick(0xfffffff1,true,true);assert(wrap.hold(1,1,100));feedback(wrap,5);wrap.tick(5,true,true);assert(wrap.permit);
 puts("PASS bench core: interlocks, bounds, duplicate rejection, lease, stale feedback, latched faults, tracking, duration, rollover");
}
