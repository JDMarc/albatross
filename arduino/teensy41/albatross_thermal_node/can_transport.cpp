#include "can_transport.h"
#include "thermal_protocol.h"
#include <math.h>

static void put16(uint8_t* out, int16_t value) { out[0] = uint8_t(value >> 8); out[1] = uint8_t(value); }

void ThermalCanTransport::begin() { bus_.begin(); bus_.setBaudRate(ThermalProtocol::CAN_BITRATE); bus_.setMaxMB(16); bus_.enableFIFO(); }
void ThermalCanTransport::send(uint16_t id, const uint8_t* data, uint8_t length) { CAN_message_t msg{}; msg.id=id; msg.len=length; memcpy(msg.buf,data,length); bus_.write(msg); }
void ThermalCanTransport::publishHeartbeat(uint8_t sequence) {
  const uint32_t uptime = millis()/1000; uint8_t data[8]={ThermalProtocol::VERSION,ThermalProtocol::NODE_ID,0,uint8_t(uptime>>24),uint8_t(uptime>>16),uint8_t(uptime>>8),uint8_t(uptime),sequence}; send(ThermalProtocol::HEARTBEAT_ID,data,8);
}
void ThermalCanTransport::publishValues(const SensorRuntime* sensors, uint32_t now) {
  for(uint8_t frame=0;frame<8;++frame){ uint8_t data[8]; for(uint8_t i=0;i<4;++i){ const uint8_t index=frame*4+i; int16_t value=ThermalProtocol::INVALID_TEMP; if(sensors[index].status==SensorStatus::VALID && isfinite(sensors[index].filtered_c)) value=static_cast<int16_t>(constrain(lroundf(sensors[index].filtered_c*10.0f),-32767L,32767L)); put16(&data[i*2],value);} send(ThermalProtocol::VALUE_BASE_ID+frame,data,8); }
}
void ThermalCanTransport::publishStatus(const SensorRuntime* sensors) {
  for(uint8_t frame=0;frame<4;++frame){ uint8_t data[4]; for(uint8_t i=0;i<4;++i){const uint8_t a=frame*8+i*2; data[i]=(uint8_t(sensors[a].status)<<4)|uint8_t(sensors[a+1].status);} send(ThermalProtocol::STATUS_BASE_ID+frame,data,4); uint8_t faults=0; for(uint8_t i=0;i<8;++i) if(sensors[frame*8+i].status!=SensorStatus::VALID && sensors[frame*8+i].status!=SensorStatus::NOT_CONFIGURED) faults|=1<<i; send(ThermalProtocol::FAULT_BASE_ID+frame,&faults,1); }
}
void ThermalCanTransport::publishConfiguration(){const uint32_t c=ThermalProtocol::CONFIG_CRC32; uint8_t data[8]={uint8_t(c>>24),uint8_t(c>>16),uint8_t(c>>8),uint8_t(c),1,0,0,32}; send(ThermalProtocol::CONFIG_ID,data,8);}
void ThermalCanTransport::publishRaw(const SensorRuntime* sensors){for(uint8_t frame=0;frame<8;++frame){uint8_t data[8];for(uint8_t i=0;i<4;++i){uint16_t raw=sensors[frame*4+i].raw;data[i*2]=uint8_t(raw>>8);data[i*2+1]=uint8_t(raw);}send(ThermalProtocol::RAW_BASE_ID+frame,data,8);}}
