#pragma once
#include <stdint.h>
#include <math.h>

// Zero-based indices in the dedicated thermal node's stable channel map.
namespace primary_thermal {
constexpr uint32_t timeout_ms = 750; // Existing thermal CAN timeout.
inline bool valid(uint8_t index, uint32_t now, bool seen, uint32_t heartbeat,
                  const int16_t* values, const uint8_t* status,
                  const uint32_t* value_rx, const uint32_t* status_rx) {
  return index < 32 && seen && now-heartbeat <= timeout_ms &&
      value_rx[index/4] && now-value_rx[index/4] <= timeout_ms &&
      status_rx[index/8] && now-status_rx[index/8] <= timeout_ms &&
      status[index] == 0 && values[index] != INT16_MIN;
}
}
