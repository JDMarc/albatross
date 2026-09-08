#pragma once
#include <stdint.h>
// Generated hardware allocation and driver timing, not earned vehicle calibration.
namespace ThermalHardware {
constexpr uint8_t TC_CS[] = {10,9,8,7};
constexpr uint8_t RTD_CS[] = {2,3,4,5,6,14,15};
constexpr uint8_t RTD_WIRES[] = {2,2,2,2,2,2,2};
constexpr uint8_t ADC_BUS[] = {0,0,0,1,1};
constexpr uint8_t ADC_ADDRESS[] = {72,73,74,72,73};
constexpr uint32_t STALE_MS = 750;
constexpr uint32_t RETRY_MS = 100;
constexpr uint32_t ADC_TIMEOUT_MS = 16;
constexpr uint32_t I2C_HZ = 100000;
constexpr uint32_t RTD_BIAS_MS = 10;
constexpr uint32_t RTD_CONVERSION_MS = 66;
constexpr uint32_t RTD_PERIOD_MS = 100;
constexpr uint32_t RECOVERY_SAMPLES = 2;
constexpr float ADC_LSB_V = 0.000125f;
constexpr float RTD_RREF = 4300.0f;
constexpr float RTD_R0 = 1000.0f;
constexpr float RTD_A = 0.0039083f;
constexpr float RTD_B = -5.775e-07f;
constexpr float RTD_C = -4.183e-12f;
constexpr uint32_t CONFIG_CRC32 = 0x61347078UL;
}
