#pragma once
#include "manager.h"
namespace fm {
inline void publish(const Manager& m,void (*send)(uint16_t,const uint8_t*,uint8_t)) {
 const auto& c=m.capabilities;
 static uint8_t sequence=0;++sequence;
 uint8_t d[8]={1,uint8_t(c.ride),uint8_t(c.available>>8),uint8_t(c.available),uint8_t(c.actions>>8),uint8_t(c.actions),uint8_t(c.missing_calibration),0};
 d[7]=sequence;send(0x240,d,8);
 auto raw=[](float x)->uint16_t{return isfinite(x)&&x>=0&&x<65535?uint16_t(x):65535;};
 uint16_t boost=raw(c.boost*10),rpm=raw(c.rpm);
 uint8_t limits[8]={1,uint8_t(c.torque*100),uint8_t(boost>>8),uint8_t(boost),uint8_t(rpm>>8),uint8_t(rpm),0,sequence};send(0x241,limits,8);
 uint32_t active=0;
 for(unsigned n=0;n<count;n++)if(m.faults[n].active)active|=uint32_t(1)<<n;
 uint8_t mask[8]={1,uint8_t(active>>24),uint8_t(active>>16),uint8_t(active>>8),uint8_t(active),0,0,sequence};send(0x243,mask,8);
 // One detail per publish avoids flooding the safety bus; the active bitmap is
 // complete each cycle. Pi must not infer normal from an absent detail record.
 static uint8_t cursor=0;const auto& f=m.faults[cursor];
 uint8_t event[8]={1,cursor,uint8_t(f.state),uint8_t(m.policies[cursor].severity),f.confidence,uint8_t(f.result),uint8_t(f.episodes>>8),uint8_t(f.episodes)};
 send(0x242,event,8);cursor=(cursor+1)%count;
}
}
