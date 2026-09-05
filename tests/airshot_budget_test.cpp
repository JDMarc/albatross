#include "../arduino/teensy41/albatross_controller_teensy41/airshot_budget.h"
#include <assert.h>
#include <stdio.h>
using airshot::RollingBudget;
int main() {
  RollingBudget b;
  b.advance(900,100,true,1000); assert(b.usage()==100);
  b.advance(1100,200,false,1000); assert(b.usage()==100); // no fixed-boundary reset
  b.advance(1850,750,false,1000); assert(b.usage()==50); // partial expiration
  b.advance(1900,50,false,1000); assert(b.usage()==0);
  b.advance(2000,100,true,1000);b.advance(2050,50,true,1000);assert(b.usage()==150);
  b.advance(4050,2000,true,1000);assert(b.usage()==1000); // stalled active tick
  b.advance(5050,1000,false,1000);assert(b.usage()==0);
  RollingBudget wrap;
  wrap.advance(0xfffffff0u,100,true,1000);
  wrap.advance(0x20u,48,false,1000);assert(wrap.usage()==100);
  wrap.advance(0x3d8u,952,false,1000);assert(wrap.usage()==0);
  // Deterministic per-millisecond oracle. Saturation is allowed only to overcount.
  RollingBudget stress; unsigned now=0,seed=123, exact=0;bool history[1000]={};
  for(unsigned t=0;t<30000;t++) {
    seed=1664525u*seed+1013904223u;bool active=(seed>>31)!=0;
    exact-=history[now%1000];history[now%1000]=active;exact+=active;++now;
    stress.advance(now,1,active,1000);
    assert(stress.usage()>=exact && stress.usage()<=1000);
  }
  stress.advance(now+1000,1000,false,1000);assert(stress.usage()==0);
  puts("PASS rolling budget: boundary, partial expiry, active gaps, wrap and capacity stress");
}
