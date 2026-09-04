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

The value frames are grouped broadcasts rather than one frame per sensor. Acquisition runs at each sensor's configured rate; value groups publish at 25 Hz, status/heartbeat at 10 Hz, configuration at 0.5 Hz, and raw commissioning data at 2 Hz. Pi receivers declare the node offline after 750 ms without a valid v1 heartbeat.
