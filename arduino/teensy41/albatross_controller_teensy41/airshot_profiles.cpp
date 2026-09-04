#include "airshot_profiles.h"
namespace airshot {
Profile selectProfile(const Config& c,const Inputs& i,bool recovery) {
  if(fabsf(i.boost[0]-i.boost[1])>c.boost_start) return i.boost[0]<i.boost[1]?Profile::LEFT_LAG:Profile::RIGHT_LAG;
  if(recovery) return Profile::RECOVERY;
  if(i.rpm<c.launch_rpm) return Profile::LAUNCH;
  if(i.rpm>c.high_rpm) return Profile::HIGH_RPM;
  return Profile::MID_TRANSIENT;
}
void mix(const Config& c,const Inputs& i,Profile id,float demand,float progress,float* commands) {
  const auto& p=c.profiles[uint8_t(id)];
  float scale=demand*rpmGain(c,i.rpm)*c.gear[i.gear]*c.fuel[i.fuel]*c.ride[i.ride_mode]*(i.vdc_valid?clamp(i.vdc_margin,0,1):1);
  float balance=clamp((i.boost[1]-i.boost[0])/c.boost_full,-c.balance_limit,c.balance_limit);
  for(int n=0;n<4;n++) {
    const auto& v=c.valves[n];
    float base=n<2?p.intake*clamp(1-progress*p.intake_decay,0,1):p.turbine;
    float trim=n>=2?1+(n==2?balance:-balance):1;
    float pressure=sqrtf(v.pressure_reference/i.regulated);
    float out=clamp(base*scale*trim*v.trim*pressure,0,v.maximum);
    commands[n]=out<v.minimum?0:out;
    if((c.stage==2 && n>=2) || (c.stage==3 && n<2)) commands[n]=0;
  }
}
}
