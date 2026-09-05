#pragma once
#include "monitors.h"
namespace fm {
enum class Channel:uint8_t {RAIL,MAP,BARO,RPM,OIL_TEMP,OIL_PRESSURE,LAMBDA_L,LAMBDA_R,EGT_L,EGT_R,HEAD_L,HEAD_R,
 WG_CMD_L,WG_CMD_R,WG_POS_L,WG_POS_R,WG_CURRENT_L,WG_CURRENT_R,FAN_CMD,FAN_CURRENT,FAN_RPM,
 WMI_CMD,WMI_PRESSURE,WMI_CURRENT,TANK,REGULATED,PUMP_CMD,PUMP_CURRENT,VOLTAGE,ACCEL_NORM,TURBO_L,TURBO_R,COUNT};
enum class Operation:uint8_t {VALUE,DIFFERENCE,ABS_DIFFERENCE,RATE,OIL_ERROR};
struct Rule {
 Id fault=Id::PI_OFFLINE;Channel a=Channel::RPM,b=Channel::RPM;
 Operation operation=Operation::VALUE;Band band;bool enabled=false,require_running=true;
 uint32_t confirm_ms=0;
};
class SubsystemMonitors {
 public:
 Signal signals[unsigned(Channel::COUNT)];Rule rules[32];OilEnvelope oil;
 bool stationary_verified=false,air_closed_verified=false,wmi_commanded_verified=false;
 bool fuel_fusion_enabled=false;
 Evidence evidence[32];
 void update(Manager& manager,uint32_t now) {
   for(unsigned n=0;n<32;n++) {
     auto& r=rules[n];evidence[n]=Evidence::UNKNOWN;
     if(!r.enabled)continue;
     auto& a=signals[unsigned(r.a)];auto& b=signals[unsigned(r.b)];auto& rpm=signals[unsigned(Channel::RPM)];
     bool good=a.valid(now);
     if(r.fault==Id::AIR_STUCK)good=good&&air_closed_verified;
     if(r.a==Channel::ACCEL_NORM)good=good&&stationary_verified;
     if(r.a==Channel::WMI_PRESSURE)good=good&&wmi_commanded_verified;
     if(r.require_running)good=good&&rpm.valid(now)&&rpm.value>0;
     float value=a.value;
     if(r.operation==Operation::DIFFERENCE||r.operation==Operation::ABS_DIFFERENCE){good=good&&b.valid(now);value-=b.value;if(r.operation==Operation::ABS_DIFFERENCE)value=fabsf(value);}
     if(r.operation==Operation::RATE)value=rates[n].update(a,now);
     if(r.operation==Operation::OIL_ERROR){auto& temp=signals[unsigned(Channel::OIL_TEMP)];good=good&&rpm.valid(now)&&temp.valid(now);value-=oil.expected(rpm.value,temp.value);}
     auto& f=manager.faults[unsigned(r.fault)];
     manager.policies[unsigned(r.fault)].confirm_ms=r.confirm_ms;
     evidence[n]=r.band.evaluate(value,good,f.active);
     manager.observe(r.fault,evidence[n],100,unsigned(r.a),uint32_t(1)<<unsigned(r.b));
   }
   // Fusion adds evidence; it never dismisses low pressure because lambda looks normal.
   auto e=[&](Id id){return manager.faults[unsigned(id)].evidence;};
   Evidence fuel=corroborate(e(Id::FUEL_DP_LOW),e(Id::LAMBDA_LEFT),e(Id::LAMBDA_RIGHT));
   if(fuel_fusion_enabled&&fuel==Evidence::BAD)manager.observe(Id::FUEL_DP_CRITICAL,fuel,100,unsigned(Channel::RAIL),
       (uint32_t(1)<<unsigned(Channel::LAMBDA_L))|(uint32_t(1)<<unsigned(Channel::LAMBDA_R)),1);
 }
 private:Rate rates[32];
};
}
