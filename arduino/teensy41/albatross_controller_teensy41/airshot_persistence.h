#pragma once
#include <EEPROM.h>
#include "airshot_config.h"
namespace airshot {
inline uint32_t hashBytes(const uint8_t* bytes,size_t count,uint32_t h=2166136261UL) {
  for(size_t n=0;n<count;n++) h=(h^bytes[n])*16777619UL;
  return h;
}
struct StoredConfig {uint32_t magic,sequence,checksum;Config config;};
static_assert(2*sizeof(StoredConfig)<=4284,"Air Shot calibration exceeds Teensy 4.1 EEPROM");
inline bool storedValid(const StoredConfig& s) {
  return s.magic==0x41535632UL && s.checksum==hashBytes(reinterpret_cast<const uint8_t*>(&s.config),sizeof(Config)) && validConfig(s.config);
}
inline bool loadConfig(Config& config) {
  StoredConfig a{},b{};EEPROM.get(0,a);EEPROM.get(sizeof(StoredConfig),b);
  bool av=storedValid(a),bv=storedValid(b);
  if(!av && !bv)return false;
  config=(bv && (!av || int32_t(b.sequence-a.sequence)>0))?b.config:a.config;
  return true;
}
inline void storeConfig(const Config& config) {
  StoredConfig a{},b{};EEPROM.get(0,a);EEPROM.get(sizeof(StoredConfig),b);
  bool av=storedValid(a),bv=storedValid(b);
  bool newerB=bv && (!av || int32_t(b.sequence-a.sequence)>0);
  uint32_t seq=newerB?b.sequence:(av?a.sequence:0);
  int address=newerB?0:sizeof(StoredConfig);
  StoredConfig s{};s.sequence=seq+1;s.config=config;
  s.checksum=hashBytes(reinterpret_cast<const uint8_t*>(&s.config),sizeof(Config));
  // Invalidate slot first, write payload, mark valid last. Previous slot survives.
  EEPROM.put(address,s);
  uint32_t magic=0x41535632UL;EEPROM.put(address,magic);
}
}
