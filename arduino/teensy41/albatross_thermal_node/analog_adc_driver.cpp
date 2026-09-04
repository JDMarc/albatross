#include "analog_adc_driver.h"

constexpr uint8_t AnalogAdcDriver::CS_PINS[2];

void AnalogAdcDriver::begin() {
  SPI.begin();
  for (uint8_t pin : CS_PINS) { pinMode(pin, OUTPUT); digitalWrite(pin, HIGH); }
}

bool AnalogAdcDriver::read(uint8_t logical_channel, uint16_t& value) {
  if (logical_channel >= 32) return false;
  const uint8_t device = logical_channel / 16;
  const uint8_t channel = logical_channel % 16;
  SPI.beginTransaction(SPISettings(8000000, MSBFIRST, SPI_MODE0));
  digitalWrite(CS_PINS[device], LOW);
  SPI.transfer16(static_cast<uint16_t>(0x1000U | (channel << 7))); // select next ADS7953 channel
  digitalWrite(CS_PINS[device], HIGH);
  delayMicroseconds(2);
  digitalWrite(CS_PINS[device], LOW);
  const uint16_t response = SPI.transfer16(0x0000);
  digitalWrite(CS_PINS[device], HIGH);
  SPI.endTransaction();
  value = response & 0x0FFFU;
  return ((response >> 12) & 0x0FU) == channel;
}
