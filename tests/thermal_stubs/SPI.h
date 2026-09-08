#pragma once
#include "Arduino.h"
constexpr int MSBFIRST=1,SPI_MODE1=1;
struct SPISettings{SPISettings(int,int,int){}};
struct FakeSPI {
  uint8_t regs[40][8]={};bool absent[40]={},stuck=false;int reg=-1;bool writing=false;
  void begin(){} void beginTransaction(SPISettings){reg=-1;}void endTransaction(){}
  uint8_t transfer(uint8_t v){
    if(selected_cs<0)return 255;
    if(reg<0){writing=v&128;reg=v&127;return 0;}
    if(absent[selected_cs])return 255;
    if(writing){regs[selected_cs][reg++]=v&~(stuck?0x06:0x26);return 0;}
    return regs[selected_cs][reg++];
  }
};
extern FakeSPI SPI;
