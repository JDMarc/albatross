#pragma once
#include "manager.h"
namespace fm {
// Reusable five-layer evidence primitives. Missing calibration is NOT healthy evidence.
struct Band {
 float trip=NAN,clear=NAN;bool high=true;
 Evidence evaluate(float value,bool valid,bool active)const{
   if(!valid||!isfinite(value)||!isfinite(trip)||!isfinite(clear))return Evidence::UNKNOWN;
   if((high&&clear>trip)||(!high&&clear<trip))return Evidence::UNKNOWN;
   return (high?value>=(active?clear:trip):value<=(active?clear:trip))?Evidence::BAD:Evidence::GOOD;
 }
};
struct Rate {
 float previous=NAN,last_rate=NAN;uint32_t at=0;bool seen=false;
 float update(const Signal& s,uint32_t now){
   if(!s.valid(now)){seen=false;last_rate=NAN;return NAN;}
   if(seen&&s.at==at)return last_rate; // no new derivative from a repeated sample
   float value=seen?1000*(s.value-previous)/uint32_t(s.at-at):NAN;
   previous=s.value;at=s.at;seen=true;last_rate=value;return value;
 }
};
inline Evidence fuelDifferential(const Signal& rail,const Signal& map,uint32_t now,const Band& band,bool active) {
 return band.evaluate(rail.value-map.value,rail.valid(now)&&map.valid(now),active);
}
struct OilEnvelope {
 float rpm[4]={NAN,NAN,NAN,NAN},minimum[4]={NAN,NAN,NAN,NAN};
 float reference_temp=NAN,temp_slope=NAN;
 float expected(float speed,float temp)const {
   if(!isfinite(speed)||!isfinite(temp)||!isfinite(reference_temp)||!isfinite(temp_slope))return NAN;
   for(unsigned n=0;n<4;n++)if(!isfinite(rpm[n])||!isfinite(minimum[n])||(n&&rpm[n]<=rpm[n-1]))return NAN;
   float value=minimum[3];
   if(speed<=rpm[0])value=minimum[0];
   else for(unsigned n=1;n<4;n++)if(speed<=rpm[n]){value=minimum[n-1]+(minimum[n]-minimum[n-1])*(speed-rpm[n-1])/(rpm[n]-rpm[n-1]);break;}
   return value+temp_slope*(temp-reference_temp);
 }
};
struct Response {
 bool waiting=false;uint32_t since=0;
 Result check(bool requested,Evidence satisfied,uint32_t now,uint32_t deadline,bool configured){
   if(!requested){waiting=false;return Result::NOT_REQUESTED;}
   if(!configured||satisfied==Evidence::UNKNOWN)return Result::UNAVAILABLE;
   if(!waiting){waiting=true;since=now;}
   if(satisfied==Evidence::GOOD){waiting=false;return Result::CONTAINED;}
   return now-since>=deadline?Result::FAILED:Result::REQUESTED;
 }
};
// Only learn in an explicitly approved healthy operating bin. Never edits policy/limits.
struct Baseline {
 float mean=0;uint32_t samples=0;
 void observe(float value,bool authorized,bool healthy){if(!authorized||!healthy||!isfinite(value))return;
   if(samples<1000000)++samples;mean+=(value-mean)/samples;}
 float deviation(float value,uint32_t required)const{return samples>=required&&samples?value-mean:NAN;}
};
inline Evidence corroborate(Evidence a,Evidence b,Evidence c){
 if(a==Evidence::BAD&&b==Evidence::BAD&&c==Evidence::BAD)return Evidence::BAD;
 if(a==Evidence::UNKNOWN||b==Evidence::UNKNOWN||c==Evidence::UNKNOWN)return Evidence::UNKNOWN;
 return Evidence::GOOD;
}
}
