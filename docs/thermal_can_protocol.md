# Thermal CAN protocol v1

All frames use standard 11-bit identifiers, 500 kbit/s, and network byte order. Temperatures are signed 16-bit tenths of °C; `-32768` is reserved invalid and status remains authoritative.

| ID | Payload |
|---|---|
| `0x160` | version u8, node u8, flags u8, uptime u32, sequence u8 |
| `0x161..0x168` | four consecutive signed temperature values; channels 1..32 |
| `0x169..0x16C` | eight consecutive 4-bit statuses packed into four bytes |
| `0x16D` | configuration CRC32, semantic version bytes, channel count |
| `0x16E..0x171` | redundant one-bit fault summary for eight channels |
| `0x176..0x17D` | four raw ADC/front-end diagnostic values for commissioning |

Status values: `0 VALID`, `1 OPEN_CIRCUIT`, `2 SHORT_TO_GROUND`, `3 SHORT_TO_SUPPLY`, `4 OUT_OF_RANGE`, `5 IMPLAUSIBLE_RATE`, `6 STALE`, `7 FRONT_END_FAULT`, `8 NOT_CONFIGURED`.

The value frames are grouped broadcasts rather than one frame per sensor. Acquisition is asynchronous and conversion-ready gated; configured rates are requests, not guaranteed throughput. value groups publish at 25 Hz, status/heartbeat at 10 Hz, configuration at 0.5 Hz, and raw commissioning data at 2 Hz. Pi receivers declare the node offline after 750 ms without a valid v1 heartbeat.


## Thermal configuration 2.0.0 / breakout wiring

CAN IDs and protocol version 1 remain unchanged. The configuration frame carries
semantic bytes 2,0,0 and 32 stable IDs. CRC32 is calculated over UTF-8 canonical
JSON (sort_keys=True, separators=(',', ':')), not whitespace-sensitive file
bytes. A legacy firmware/config CRC is intentionally incompatible.

Raw diagnostic words are technology-specific: ADS1115 signed 16-bit counts
(0.125 mV/count at +/-4.096 V), MAX31865 unsigned 15-bit resistance ratio
(R = raw * 4300 / 32768 ohms), or MAX31856 signed tenths Celsius.
These are not all 12-bit ADC counts. Status is authoritative; never infer
validity from a raw value alone. Excitation N4.A2 is local to acquisition,
not an additional temperature ID. Invalid/stale temperatures use the existing
-32768 sentinel; cached measurements cannot renew the acquisition timestamp.
