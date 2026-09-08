#pragma once
#include "Arduino.h"
#include <vector>
struct TwoWire {
  bool fail=false,short_read=false,busy=false,wrong_config=false;
  uint8_t address=0,reg=0; uint16_t config[128]={};int index=0;
  std::vector<uint8_t> bytes;
  void begin(){} void setClock(uint32_t){}
  void beginTransmission(uint8_t a){address=a;bytes.clear();}
  void write(uint8_t b){bytes.push_back(b);}
  int endTransmission(bool=true){
    if(fail)return 4;
    reg=bytes[0];if(bytes.size()==3)config[address]=(uint16_t(bytes[1])<<8)|bytes[2];return 0;
  }
  int requestFrom(uint8_t,uint8_t){index=0;return short_read?1:2;}
  int read(){
    uint16_t v=config[address];
    if(reg==1){if(busy)v&=0x7fff;if(wrong_config)v^=0x0200;}
    else {int ch=((v>>12)&7)-4;v=(address==73 && ch==2)?26400:13200;}
    return index++==0?v>>8:v&255;
  }
};
extern TwoWire Wire,Wire1;
