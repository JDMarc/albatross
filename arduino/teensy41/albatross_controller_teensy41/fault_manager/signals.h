#pragma once
#include "types.h"
namespace fm {
// Explicit provenance: never write an estimate into the measured input slot.
struct Estimate {float value=NAN;Quality quality=Quality::INVALID;uint32_t contributors=0;};
inline Estimate conservativeTemperature(const Signal* candidates,unsigned count,uint32_t now) {
 Estimate out;
 for(unsigned n=0;n<count&&n<32;n++)if(candidates[n].valid(now)) {
   if(!isfinite(out.value)||candidates[n].value>out.value)out.value=candidates[n].value;
   out.contributors|=uint32_t(1)<<n;
 }
 if(out.contributors)out.quality=Quality::ESTIMATED;
 return out;
}
}
