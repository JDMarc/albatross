#pragma once
#include <FlexCAN_T4.h>
#include "diagnostics.h"
#include "sensor_config.h"

class ThermalCanTransport {
 public:
  void begin();
  void publishHeartbeat(uint8_t sequence);
  void publishValues(const SensorRuntime* sensors, uint32_t now);
  void publishStatus(const SensorRuntime* sensors);
  void publishConfiguration();
  void publishRaw(const SensorRuntime* sensors);
 private:
  FlexCAN_T4<CAN1, RX_SIZE_256, TX_SIZE_16> bus_;
  void send(uint16_t id, const uint8_t* data, uint8_t length);
};
