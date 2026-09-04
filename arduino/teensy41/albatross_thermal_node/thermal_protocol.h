#pragma once
#include <Arduino.h>

namespace ThermalProtocol {
constexpr uint8_t VERSION = 1;
constexpr uint8_t NODE_ID = 5;
constexpr uint32_t CAN_BITRATE = 500000;
constexpr uint16_t HEARTBEAT_ID = 0x160;
constexpr uint16_t VALUE_BASE_ID = 0x161;
constexpr uint16_t STATUS_BASE_ID = 0x169;
constexpr uint16_t CONFIG_ID = 0x16D;
constexpr uint16_t FAULT_BASE_ID = 0x16E;
constexpr uint16_t RAW_BASE_ID = 0x176;
constexpr int16_t INVALID_TEMP = INT16_MIN;
constexpr uint32_t HEARTBEAT_PERIOD_MS = 100;
constexpr uint32_t STATUS_PERIOD_MS = 100;
constexpr uint32_t CONFIG_PERIOD_MS = 2000;
constexpr uint32_t RAW_DIAGNOSTIC_PERIOD_MS = 500;
// CRC32 is generated from config/thermal_system.json by tools/generate_thermal_config.py.
constexpr uint32_t CONFIG_CRC32 = 0x515BC2B5UL;
}
