#include <SPI.h>
#include <mcp_can.h>
#include <math.h>

// Target board: Arduino Mega 2560 Rev3
// --- CAN bus wiring/config ---
static constexpr uint8_t CAN_CS_PIN = 10;
static constexpr uint8_t CAN_INT_PIN = 2;
static constexpr uint8_t SPI_SS_PIN = 53; // Mega hardware SS must stay OUTPUT for SPI master mode.
static constexpr uint32_t CAN_BITRATE = CAN_500KBPS;

MCP_CAN CANBUS(CAN_CS_PIN);

// --- CAN IDs (must match master table) ---
namespace CanId {
  constexpr uint16_t ECU_RPM = 0x100;
  constexpr uint16_t ECU_TPS = 0x101;
  constexpr uint16_t ECU_BOOST = 0x102;
  constexpr uint16_t ECU_AFR = 0x103;
  constexpr uint16_t ECU_KNOCK = 0x104;
  constexpr uint16_t ECU_OIL = 0x105;
  constexpr uint16_t ECU_CLT = 0x106;
  constexpr uint16_t ECU_FUEL_LEVEL = 0x107;
  constexpr uint16_t ECU_GEAR = 0x108;
  constexpr uint16_t ECU_LOAD = 0x109;
  constexpr uint16_t ECU_IAT = 0x10A;
  constexpr uint16_t ECU_EGT = 0x10B;
  constexpr uint16_t ECU_BATTERY = 0x10C;
  constexpr uint16_t ECU_FLEX_FUEL = 0x10D;
  constexpr uint16_t ECU_INJECTOR_STATUS = 0x10E;

  constexpr uint16_t ECU_TO_ARD_FLAME_STATUS = 0x110;
  constexpr uint16_t ECU_TO_ARD_WMI_TRIGGER = 0x111;
  constexpr uint16_t ECU_TO_ARD_ENGINE_STATUS = 0x112;
  constexpr uint16_t ARD_TO_ECU_TORQUE_CUT = 0x12A;
  constexpr uint16_t ARD_TO_ECU_TRACTION_SLIP = 0x12B;

  constexpr uint16_t PI_BOOST_TARGET = 0x120;
  constexpr uint16_t PI_MODE_SELECT = 0x121;
  constexpr uint16_t PI_FLAME_MODE = 0x122;
  constexpr uint16_t PI_LIMP_MODE = 0x123;
  constexpr uint16_t PI_TRACTION_LEVEL = 0x124;
  constexpr uint16_t PI_AIR_SHOT_REQUEST = 0x125;
  constexpr uint16_t PI_ENGINE_RUN_SWITCH = 0x127;
  constexpr uint16_t PI_WMI_ENABLE = 0x128;
  constexpr uint16_t PI_FUEL_TYPE_SELECT = 0x129;
  constexpr uint16_t PI_NFC_AUTH = 0x140;

  constexpr uint16_t ARD_AIR_SHOT_STATUS = 0x130;
  constexpr uint16_t ARD_AWC_STATE = 0x131;
  constexpr uint16_t ARD_RGB_LIGHTING = 0x132;
  constexpr uint16_t ARD_TANK_PRESSURE = 0x133;
  constexpr uint16_t ARD_TWIN_TURBO_STATUS = 0x134;
  constexpr uint16_t ARD_WASTEGATE_STATUS = 0x135;
  constexpr uint16_t ARD_GEAR_POSITION = 0x136;
  constexpr uint16_t ARD_WHEEL_SPEED = 0x137;
  constexpr uint16_t ARD_FUEL_LEVEL = 0x138;
  constexpr uint16_t ARD_WMI_STATUS = 0x139;
  constexpr uint16_t ARD_CLUTCH_SLIP_STATUS = 0x13A;
  constexpr uint16_t ARD_LIGHT_STATUS = 0x13B;
  constexpr uint16_t ARD_OIL_PRESSURE_STATUS = 0x13C;
  constexpr uint16_t ARD_FUEL_TYPE_STATUS = 0x13D;
  constexpr uint16_t ARD_TRACTION_STATUS = 0x13E;
  constexpr uint16_t ARD_SERVICE_SENSOR_VOLTAGES = 0x13F;
  constexpr uint16_t ARD_SERVICE_DIGITAL_STATES = 0x145;
  constexpr uint16_t ARD_SERVICE_FIRMWARE_VERSION = 0x146;
  constexpr uint16_t ARD_LIMP_STATUS = 0x147;

  constexpr uint16_t POST_REQUEST = 0x1F0;
  constexpr uint16_t POST_RESPONSE = 0x1F1;
}

enum TractionLevel : uint8_t {
  TC_LOW = 1,
  TC_MED = 2,
  TC_HIGH = 3,
  TC_OFF = 4,
};

enum RideMode : uint8_t {
  MODE_ECO = 1,
  MODE_NORMAL = 2,
  MODE_SPORT = 3,
  MODE_RACE = 4,
  MODE_ALBATROSS = 5,
};

struct Inputs {
  uint16_t rpm = 0;
  uint8_t tps_pct = 0;
  uint16_t boost_psi_x10 = 0;
  uint16_t knock_bits = 0;
  uint16_t iat_c_x10 = 250;
  uint16_t egt_left_c_x10 = 7500;
  uint16_t egt_right_c_x10 = 7500;
  uint16_t oil_pressure_psi_x10 = 0;
  uint16_t oil_temp_c_x10 = 900;
  uint16_t coolant_c_x10 = 900;
  uint16_t battery_mv = 13800;
  uint8_t engine_load_pct = 0;
  uint8_t engine_status = 0;
  uint8_t gear = 0;
  uint8_t fuel_code = 0x02; // default to 93 octane table if unknown
  uint8_t ethanol_pct = 10;
};

struct Commands {
  uint16_t boost_target_psi_x10 = 80; // 8.0 psi safe fallback
  RideMode mode = MODE_NORMAL;
  bool nfc_ok = false;
  bool flame_mode = false;
  bool limp_mode = false;
  uint8_t limp_reason = 0x00;
  bool engine_run_enabled = true;
  uint16_t wmi_trigger_pct_x10 = 0;
  bool wmi_arm = false;
  TractionLevel traction_level = TC_MED;
};

struct Outputs {
  uint8_t air_shot_remaining = 3;
  bool awc_active = false;
  int8_t lean_deg = 0;
  uint16_t tank_psi_x10 = 1450;
  uint16_t turbo1_psi_x10 = 0;
  uint16_t turbo2_psi_x10 = 0;
  uint8_t wg1_duty = 0;
  uint8_t wg2_duty = 0;
  uint8_t fuel_level_pct = 75;
  uint8_t wmi_tank_level_pct = 0;
  uint16_t wmi_commanded_flow_cc_min = 0;
  uint16_t wmi_actual_flow_cc_min = 0;
  bool wmi_fault = false;
  uint8_t clutch_slip_pct = 0;
  uint8_t clutch_slip_severity = 0;
  int16_t traction_slip_pct_x10 = 0;
  uint8_t traction_torque_cut_pct = 0;
  bool traction_active = false;
  bool traction_sensor_fault = false;
};

Inputs g_inputs;
Commands g_commands;
Outputs g_outputs;
static uint32_t g_last_ecu_frame_ms = 0;
static uint32_t g_last_pi_command_ms = 0;
static uint32_t g_airshot_request_until_ms = 0;
static bool g_limp_active = false;
static uint8_t g_limp_reason = 0x00;

enum LimpReason : uint8_t {
  LIMP_NONE = 0x00,
  LIMP_PI_REQUEST = 0x01,
  LIMP_ENGINE_RUN_OFF = 0x02,
  LIMP_ECU_CAN_STALE = 0x03,
  LIMP_PI_COMMAND_STALE = 0x04,
  LIMP_THERMAL = 0x05,
  LIMP_LOW_OIL_PRESS = 0x06,
  LIMP_BATTERY_VOLTAGE = 0x07,
  LIMP_KNOCK = 0x08,
  LIMP_ECU_SENSOR = 0x09,
  LIMP_NFC_AUTH = 0x0A,
  LIMP_SAFETY_SUPERVISOR = 0x0B,
  LIMP_OVERBOOST = 0x0C,
  LIMP_WMI_FAULT = 0x0D,
  LIMP_CLUTCH_SLIP = 0x0E
};

// --- Hardware pins ---
// Arduino is the boost controller. These pins command the wastegate actuator
// power stages directly; there is no separate boost-control module in between.
// Each actuator channel uses PWM + direction + enable.
static constexpr uint8_t WG1_PWM_PIN = 5;
static constexpr uint8_t WG1_DIR_PIN = 22;
static constexpr uint8_t WG1_EN_PIN = 23;
static constexpr uint8_t WG2_PWM_PIN = 6;
static constexpr uint8_t WG2_DIR_PIN = 24;
static constexpr uint8_t WG2_EN_PIN = 25;
static constexpr uint8_t WMI_PUMP_PIN = 7;     // Water/meth pump relay (active HIGH)
static constexpr uint8_t FLAME_EN_PIN = 8;     // Flame mode interlock output
static constexpr uint8_t AIRSHOT_SOL_PIN = 9;  // Air shot solenoid output
static constexpr uint8_t AIR_COMPRESSOR_RELAY_PIN = 27; // Air tank compressor relay
// Mega 2560 external interrupt-capable pins: 2,3,18,19,20,21
// Do not duplicate these constants elsewhere in this sketch.
static constexpr uint8_t FRONT_WHEEL_HALL_PIN = 3;
static constexpr uint8_t REAR_WHEEL_HALL_PIN = 18;
static constexpr uint8_t NEUTRAL_SWITCH_PIN = 26; // digital input from neutral lamp switch
// Existing bike lamp feeds, conditioned to 5V logic with external pulldowns.
static constexpr uint8_t LEFT_INDICATOR_PIN = 28;
static constexpr uint8_t RIGHT_INDICATOR_PIN = 29;
static constexpr uint8_t HIGH_BEAM_PIN = 30;
static constexpr uint8_t BRAKE_LIGHT_PIN = 31;
static constexpr uint8_t OIL_WARNING_PIN = 32;
static constexpr uint8_t OIL_PRESSURE_SENSOR_PIN = A0;
static constexpr uint8_t WMI_TANK_LEVEL_PIN = A1;
static constexpr uint8_t AIR_TANK_PRESSURE_SENSOR_PIN = A2;
static constexpr uint8_t WMI_FLOW_SENSOR_PIN = 19;
static constexpr uint8_t WMI_PRESSURE_OK_PIN = 33;

static constexpr uint16_t OIL_PRESSURE_SENSOR_MIN_RAW = 102; // 0.5V on a 5V ADC
static constexpr uint16_t OIL_PRESSURE_SENSOR_MAX_RAW = 921; // 4.5V on a 5V ADC
static constexpr uint16_t OIL_PRESSURE_SENSOR_MAX_PSI_X10 = 1000; // 100.0 psi
static constexpr uint16_t AIR_TANK_SENSOR_MIN_RAW = 102; // 0.5V on a 5V ADC
static constexpr uint16_t AIR_TANK_SENSOR_MAX_RAW = 921; // 4.5V on a 5V ADC
static constexpr uint16_t AIR_TANK_SENSOR_MAX_PSI_X10 = 2000; // 200.0 psi sender; tank relay caps below 150 psi
static constexpr float WMI_FLOW_PULSES_PER_LITER = 450.0f;
static constexpr bool WMI_PRESSURE_OK_ACTIVE_LOW = true;
static constexpr float TC_MIN_SPEED_MPS = 4.5f; // ~10 mph; avoids low-speed pulse quantization cuts.
static constexpr float TC_EXIT_HYSTERESIS = 0.025f;
static constexpr uint32_t ECU_CAN_TIMEOUT_MS = 300;
static constexpr uint32_t PI_CAN_TIMEOUT_MS = 1500;
static constexpr uint32_t AIRSHOT_MAX_LATCH_MS = 10000;
static constexpr uint32_t AIRSHOT_WASTEGATE_DECOUPLE_MS = 350;
static constexpr uint16_t AIRSHOT_MIN_TANK_PSI_X10 = 350; // below 35 psi is not a useful transient shot
static constexpr uint16_t AIRSHOT_MIN_DELTA_PSI_X10 = 120; // tank must be at least 12 psi above manifold
static constexpr uint16_t AIRSHOT_TRIGGER_GAP_PSI_X10 = 40; // only fire when requested boost is meaningfully above actual
static constexpr uint16_t AIRSHOT_WASTEGATE_GUARD_PSI_X10 = 30;
static constexpr uint16_t AIRSHOT_COMPRESSOR_ON_PSI_X10 = 1100;
static constexpr uint16_t AIRSHOT_COMPRESSOR_OFF_PSI_X10 = 1450;
static constexpr float AIRSHOT_COMPRESSOR_MAX_SPEED_MPS = 0.45f; // ~1 mph
constexpr uint8_t FIRMWARE_VERSION_MAJOR = 0;
constexpr uint8_t FIRMWARE_VERSION_MINOR = 1;
constexpr uint8_t FIRMWARE_VERSION_PATCH = 0;
constexpr uint16_t FIRMWARE_BUILD = 1;

// Hard safety caps by mode (psi*10); Pi sends the fuel/WMI-aware target.
uint16_t modeBoostCap(uint8_t mode) {
  switch (mode) {
    case MODE_ECO: return 0;
    case MODE_NORMAL: return 0;
    case MODE_SPORT: return 130;    // 13.0 psi
    case MODE_RACE: return 180;     // 18.0 psi
    case MODE_ALBATROSS: return 220;// 22.0 psi
    default: return 80;
  }
}

static inline uint16_t clampU16(uint16_t v, uint16_t lo, uint16_t hi) {
  return (v < lo) ? lo : ((v > hi) ? hi : v);
}

float wmiFuelGain(uint8_t fuel_code) {
  // Relative WMI dependence by fuel knock/cooling headroom.
  // Higher gain => more meth/water needed for same boost/load condition.
  switch (fuel_code) {
    case 0x00: return 1.00f; // 87 pump gas: strongest WMI dependence
    case 0x01: return 0.90f; // 91
    case 0x02: return 0.82f; // 93
    case 0x03: return 0.65f; // 100 race gas
    case 0x04: return 0.48f; // E85 already has strong charge cooling + octane
    case 0x05: return 0.35f; // C16 least dependent on WMI
    default: return 0.82f;
  }
}

uint8_t computeWastegatePosition(uint16_t target_psi_x10, uint16_t actual_psi_x10, uint8_t tps_pct, bool knock) {
  // Closed-loop boost controller output for electronic wastegate actuators.
  // Returns actuator position request as 0-100% PWM duty.
  const int16_t error = static_cast<int16_t>(target_psi_x10) - static_cast<int16_t>(actual_psi_x10);
  int16_t duty = 0;

  // Basic feed-forward by requested level.
  duty += (target_psi_x10 > 70) ? map(target_psi_x10, 70, 220, 10, 78) : 0;

  // P-term trim.
  duty += error / 2;

  // Throttle gating keeps spool behavior predictable and safe.
  if (tps_pct < 20) duty = 0;
  else if (tps_pct < 40) duty = (duty < 35) ? duty : 35;
  else if (tps_pct < 60) duty = min<int16_t>(duty, 55);

  // Safety trims.
  if (knock) duty -= 20;

  // Clamp to actuator travel limits.
  duty = constrain(duty, 0, 100);
  return static_cast<uint8_t>(duty);
}

void publishFrame(uint16_t id, const uint8_t *data, uint8_t len) {
  CANBUS.sendMsgBuf(id, 0, len, const_cast<uint8_t *>(data));
}

bool elapsedSince(uint32_t last_ms, uint32_t timeout_ms, uint32_t now_ms) {
  return last_ms == 0 || static_cast<uint32_t>(now_ms - last_ms) > timeout_ms;
}

bool isEcuFrame(uint16_t id) {
  return (id >= CanId::ECU_RPM && id <= CanId::ECU_INJECTOR_STATUS) ||
      (id >= CanId::ECU_TO_ARD_FLAME_STATUS && id <= CanId::ECU_TO_ARD_ENGINE_STATUS);
}

bool isPiCommandFrame(uint16_t id) {
  return (id >= CanId::PI_BOOST_TARGET && id <= CanId::PI_FUEL_TYPE_SELECT) || id == CanId::PI_NFC_AUTH;
}

void handleFrame(uint16_t id, uint8_t len, const uint8_t *data) {
  const uint32_t now = millis();
  if (isEcuFrame(id)) {
    g_last_ecu_frame_ms = now;
  } else if (isPiCommandFrame(id)) {
    g_last_pi_command_ms = now;
  }

  switch (id) {
    case CanId::ECU_RPM:
      if (len >= 2) g_inputs.rpm = (uint16_t(data[0]) << 8) | data[1];
      break;
    case CanId::ECU_TPS:
      if (len >= 1) g_inputs.tps_pct = data[0];
      break;
    case CanId::ECU_BOOST:
      if (len >= 2) g_inputs.boost_psi_x10 = (uint16_t(data[0]) << 8) | data[1];
      break;
    case CanId::ECU_KNOCK:
      if (len >= 2) g_inputs.knock_bits = (uint16_t(data[0]) << 8) | data[1];
      else if (len >= 1) g_inputs.knock_bits = data[0];
      break;
    case CanId::ECU_OIL:
      if (len >= 4) {
        g_inputs.oil_pressure_psi_x10 = (uint16_t(data[0]) << 8) | data[1];
        g_inputs.oil_temp_c_x10 = (uint16_t(data[2]) << 8) | data[3];
      }
      break;
    case CanId::ECU_CLT:
      if (len >= 2) g_inputs.coolant_c_x10 = (uint16_t(data[0]) << 8) | data[1];
      break;
    case CanId::ECU_IAT:
      if (len >= 2) g_inputs.iat_c_x10 = (uint16_t(data[0]) << 8) | data[1];
      break;
    case CanId::ECU_EGT:
      if (len >= 4) {
        g_inputs.egt_left_c_x10 = (uint16_t(data[0]) << 8) | data[1];
        g_inputs.egt_right_c_x10 = (uint16_t(data[2]) << 8) | data[3];
      }
      break;
    case CanId::ECU_GEAR:
      if (len >= 1) g_inputs.gear = data[0];
      break;
    case CanId::ECU_FUEL_LEVEL:
      if (len >= 1) g_outputs.fuel_level_pct = constrain(data[0], 0, 100);
      break;
    case CanId::ECU_LOAD:
      if (len >= 1) g_inputs.engine_load_pct = constrain(data[0], 0, 100);
      break;
    case CanId::ECU_BATTERY:
      if (len >= 2) g_inputs.battery_mv = (uint16_t(data[0]) << 8) | data[1];
      break;
    case CanId::ECU_FLEX_FUEL:
      if (len >= 1) g_inputs.ethanol_pct = constrain(data[0], 0, 100);
      break;
    case CanId::PI_BOOST_TARGET:
      if (len >= 2) g_commands.boost_target_psi_x10 = (uint16_t(data[0]) << 8) | data[1];
      break;
    case CanId::PI_MODE_SELECT:
      if (len >= 1) g_commands.mode = static_cast<RideMode>(data[0]);
      break;
    case CanId::PI_NFC_AUTH:
      if (len >= 1) g_commands.nfc_ok = data[0] != 0;
      break;
    case CanId::PI_FLAME_MODE:
      if (len >= 1) g_commands.flame_mode = data[0] != 0;
      break;
    case CanId::PI_LIMP_MODE:
      if (len >= 1) g_commands.limp_mode = data[0] != 0;
      if (len >= 2) g_commands.limp_reason = data[1];
      break;
    case CanId::PI_TRACTION_LEVEL:
      if (len >= 1) g_commands.traction_level = static_cast<TractionLevel>(data[0]);
      break;
    case CanId::PI_AIR_SHOT_REQUEST:
      if (len >= 1 && data[0] != 0) g_airshot_request_until_ms = now + 350;
      break;
    case CanId::PI_ENGINE_RUN_SWITCH:
      if (len >= 1) g_commands.engine_run_enabled = data[0] != 0;
      break;
    case CanId::PI_WMI_ENABLE:
      if (len >= 1) g_commands.wmi_arm = data[0] != 0;
      break;
    case CanId::PI_FUEL_TYPE_SELECT:
      if (len >= 1) g_inputs.fuel_code = data[0];
      break;
    case CanId::ECU_TO_ARD_FLAME_STATUS:
      // Deprecated path kept for backward compatibility; PI frame should be source of truth.
      if (len >= 1) g_commands.flame_mode = data[0] != 0;
      break;
    case CanId::ECU_TO_ARD_WMI_TRIGGER:
      if (len >= 2) g_commands.wmi_trigger_pct_x10 = (uint16_t(data[0]) << 8) | data[1];
      break;
    case CanId::ECU_TO_ARD_ENGINE_STATUS:
      if (len >= 1) g_inputs.engine_status = data[0];
      break;
    case CanId::POST_REQUEST: {
      uint8_t resp[2] = {0xA1, 0x01}; // device=Arduino controller, status=OK
      publishFrame(CanId::POST_RESPONSE, resp, 2);
      break;
    }
    default:
      break;
  }
}


static bool g_airshot_latched = false;
static bool g_airshot_rearm_ready = true;
static uint32_t g_airshot_latched_since_ms = 0;
static uint32_t g_airshot_wastegate_decouple_until_ms = 0;
static volatile uint32_t g_front_pulses = 0;
static volatile uint32_t g_rear_pulses = 0;
static volatile uint32_t g_wmi_flow_pulses = 0;
static float g_front_wheel_mps = 0.0f;
static float g_rear_wheel_mps = 0.0f;

struct WheelConfig {
  float circumference_m;
  uint8_t magnets;
};

static constexpr WheelConfig FRONT_WHEEL = {1.95f, 6};
static constexpr WheelConfig REAR_WHEEL = {1.99f, 6};

// Placeholder wheel-speed to RPM ratios by gear for derived gear detection.
// NOTE: replace these placeholder values with measured real-world ratios.
static constexpr float GEAR_RATIO_FROM_RPM_MPH[] = {
  0.0f,
  280.0f, // 1st
  210.0f, // 2nd
  170.0f, // 3rd
  145.0f, // 4th
  125.0f, // 5th
  110.0f  // 6th
};
// NOTE: These are placeholder rpm:mph ratios for now.
// Replace with measured ratios after real-world validation.

uint8_t readLightingStatus() {
  uint8_t flags = 0;
  if (digitalRead(LEFT_INDICATOR_PIN) == HIGH) flags |= 0x01;
  if (digitalRead(RIGHT_INDICATOR_PIN) == HIGH) flags |= 0x02;
  if (digitalRead(HIGH_BEAM_PIN) == HIGH) flags |= 0x04;
  if (digitalRead(NEUTRAL_SWITCH_PIN) == LOW) flags |= 0x08;
  if (digitalRead(BRAKE_LIGHT_PIN) == HIGH) flags |= 0x10;
  if (digitalRead(OIL_WARNING_PIN) == HIGH) flags |= 0x20;
  return flags;
}

uint16_t readOilPressurePsiX10() {
  const int raw = analogRead(OIL_PRESSURE_SENSOR_PIN);
  const long scaled = map(
      constrain(raw, OIL_PRESSURE_SENSOR_MIN_RAW, OIL_PRESSURE_SENSOR_MAX_RAW),
      OIL_PRESSURE_SENSOR_MIN_RAW,
      OIL_PRESSURE_SENSOR_MAX_RAW,
      0,
      OIL_PRESSURE_SENSOR_MAX_PSI_X10);
  return static_cast<uint16_t>(constrain(scaled, 0, OIL_PRESSURE_SENSOR_MAX_PSI_X10));
}

uint16_t readAirTankPressurePsiX10() {
  const int raw = analogRead(AIR_TANK_PRESSURE_SENSOR_PIN);
  const long scaled = map(
      constrain(raw, AIR_TANK_SENSOR_MIN_RAW, AIR_TANK_SENSOR_MAX_RAW),
      AIR_TANK_SENSOR_MIN_RAW,
      AIR_TANK_SENSOR_MAX_RAW,
      0,
      AIR_TANK_SENSOR_MAX_PSI_X10);
  return static_cast<uint16_t>(constrain(scaled, 0, AIR_TANK_SENSOR_MAX_PSI_X10));
}

uint16_t adcRawToMillivolts(int raw) {
  return static_cast<uint16_t>(constrain(map(constrain(raw, 0, 1023), 0, 1023, 0, 5000), 0, 5000));
}

uint8_t classifyClutchSlipSeverity(float slip_pct) {
  if (slip_pct < 8.0f) return 0;   // nominal
  if (slip_pct < 15.0f) return 1;  // mild
  if (slip_pct < 25.0f) return 2;  // moderate
  return 3;                        // severe
}

uint8_t computeGearFromSpeedRpm(float speed_mph, uint16_t rpm, bool neutral_switch_active) {
  if (neutral_switch_active) return 0; // Neutral
  if (speed_mph < 2.0f || rpm < 1000) return g_inputs.gear;

  float observed = rpm / speed_mph;
  uint8_t best = g_inputs.gear > 0 ? g_inputs.gear : 1;
  float best_err = 1e9f;
  for (uint8_t gear = 1; gear <= 6; ++gear) {
    const float expected = GEAR_RATIO_FROM_RPM_MPH[gear];
    float err = fabsf(observed - expected);
    if (err < best_err) {
      best_err = err;
      best = gear;
    }
  }
  return best;
}

void frontWheelPulseISR() { g_front_pulses++; }
void rearWheelPulseISR() { g_rear_pulses++; }
void wmiFlowPulseISR() { g_wmi_flow_pulses++; }

float tcSlipLimitForLevel(TractionLevel level) {
  switch (level) {
    case TC_LOW: return 0.12f;
    case TC_MED: return 0.09f;
    case TC_HIGH: return 0.06f;
    case TC_OFF: default: return 1.0f;
  }
}

uint8_t torqueCutForSlip(float slip_ratio, float limit) {
  if (limit >= 1.0f || slip_ratio <= limit) return 0;
  const float excess = slip_ratio - limit;
  return static_cast<uint8_t>(constrain(static_cast<int>(excess * 320.0f), 0, 100));
}

void updateWheelSpeeds() {
  static uint32_t last_ms = 0;
  static uint32_t last_front = 0;
  static uint32_t last_rear = 0;
  const uint32_t now = millis();
  if (now - last_ms < 50) return;
  const float dt = (now - last_ms) / 1000.0f;
  noInterrupts();
  const uint32_t f = g_front_pulses;
  const uint32_t r = g_rear_pulses;
  interrupts();
  const uint32_t df = f - last_front;
  const uint32_t dr = r - last_rear;
  last_front = f;
  last_rear = r;
  last_ms = now;
  const float f_rps = (FRONT_WHEEL.magnets > 0 && dt > 0) ? (df / static_cast<float>(FRONT_WHEEL.magnets)) / dt : 0.0f;
  const float r_rps = (REAR_WHEEL.magnets > 0 && dt > 0) ? (dr / static_cast<float>(REAR_WHEEL.magnets)) / dt : 0.0f;
  g_front_wheel_mps = f_rps * FRONT_WHEEL.circumference_m;
  g_rear_wheel_mps = r_rps * REAR_WHEEL.circumference_m;
}

uint8_t readWmiTankLevelPct() {
  const int raw = analogRead(WMI_TANK_LEVEL_PIN);
  const long scaled = map(constrain(raw, 0, 1023), 0, 1023, 0, 100);
  return static_cast<uint8_t>(constrain(scaled, 0, 100));
}

bool readWmiPressureOk() {
  const int level = digitalRead(WMI_PRESSURE_OK_PIN);
  return WMI_PRESSURE_OK_ACTIVE_LOW ? (level == LOW) : (level == HIGH);
}

uint16_t readWmiFlowCcMin() {
  static uint32_t last_ms = 0;
  static uint32_t last_pulses = 0;
  const uint32_t now = millis();

  noInterrupts();
  const uint32_t pulses = g_wmi_flow_pulses;
  interrupts();

  if (last_ms == 0) {
    last_ms = now;
    last_pulses = pulses;
    return g_outputs.wmi_actual_flow_cc_min;
  }

  const uint32_t elapsed_ms = now - last_ms;
  if (elapsed_ms < 100) {
    return g_outputs.wmi_actual_flow_cc_min;
  }

  const uint32_t delta_pulses = pulses - last_pulses;
  last_ms = now;
  last_pulses = pulses;

  if (elapsed_ms == 0 || WMI_FLOW_PULSES_PER_LITER <= 0.0f) {
    return 0;
  }

  const float liters = delta_pulses / WMI_FLOW_PULSES_PER_LITER;
  const float minutes = elapsed_ms / 60000.0f;
  const float cc_min = (minutes > 0.0f) ? (liters * 1000.0f / minutes) : 0.0f;
  return static_cast<uint16_t>(constrain(static_cast<long>(roundf(cc_min)), 0L, 65535L));
}

void updateWmiSensorOutputs(bool wmi_enable) {
  g_outputs.wmi_tank_level_pct = readWmiTankLevelPct();
  g_outputs.wmi_actual_flow_cc_min = readWmiFlowCcMin();

  const bool pressure_ok = readWmiPressureOk();
  const bool commanded = g_outputs.wmi_commanded_flow_cc_min >= 300;
  const bool flow_low = commanded && (uint32_t(g_outputs.wmi_actual_flow_cc_min) * 10UL < uint32_t(g_outputs.wmi_commanded_flow_cc_min) * 6UL);
  const bool tank_empty = wmi_enable && g_outputs.wmi_tank_level_pct < 3;
  const bool pressure_fault = wmi_enable && !pressure_ok;
  g_outputs.wmi_fault = flow_low || tank_empty || pressure_fault;
}


uint16_t modeBoostLimitForAirShot(uint8_t mode) {
  switch (mode) {
    case MODE_RACE: return 180;
    case MODE_ALBATROSS: return 220;
    default: return 0;
  }
}

uint16_t requestedBoostLimitForAirShot() {
  const uint16_t mode_cap = modeBoostLimitForAirShot(g_commands.mode);
  if (mode_cap == 0) return 0;
  return min(g_commands.boost_target_psi_x10, mode_cap);
}

uint8_t calculateShotsRemaining(uint16_t tank_psi_x10) {
  if (tank_psi_x10 < AIRSHOT_MIN_TANK_PSI_X10) return 0;
  if (tank_psi_x10 < 750) return 1;
  if (tank_psi_x10 < 1150) return 2;
  return 3;
}

bool airShotPressureDeltaOk() {
  const uint32_t required_tank_pressure = static_cast<uint32_t>(g_inputs.boost_psi_x10) + AIRSHOT_MIN_DELTA_PSI_X10;
  return g_outputs.tank_psi_x10 >= AIRSHOT_MIN_TANK_PSI_X10 &&
      static_cast<uint32_t>(g_outputs.tank_psi_x10) > required_tank_pressure;
}

bool shouldTriggerAirShot(bool manual_request) {
  const bool mode_ok = (g_commands.mode == MODE_RACE) || (g_commands.mode == MODE_ALBATROSS);
  const uint16_t requested_limit = requestedBoostLimitForAirShot();
  const bool boost_needed = requested_limit > 0 && (g_inputs.boost_psi_x10 + AIRSHOT_TRIGGER_GAP_PSI_X10 < requested_limit);
  const bool base_ok = mode_ok && boost_needed && g_airshot_rearm_ready && !g_airshot_latched &&
      g_inputs.gear >= 2 && calculateShotsRemaining(g_outputs.tank_psi_x10) > 0 && airShotPressureDeltaOk();
  const bool auto_ok = g_inputs.tps_pct > 90 && g_inputs.rpm > 5500;
  const bool manual_ok = manual_request && g_inputs.tps_pct > 70 && g_inputs.rpm > 3000;
  return base_ok && (auto_ok || manual_ok);
}

bool isAirShotRequestActive(uint32_t now) {
  return g_airshot_request_until_ms != 0 && static_cast<int32_t>(g_airshot_request_until_ms - now) >= 0;
}

void updateControllers() {
  const uint32_t now = millis();
  g_outputs.tank_psi_x10 = readAirTankPressurePsiX10();
  updateWheelSpeeds();
  const bool ecu_can_stale = elapsedSince(g_last_ecu_frame_ms, ECU_CAN_TIMEOUT_MS, now);
  const bool pi_can_stale = elapsedSince(g_last_pi_command_ms, PI_CAN_TIMEOUT_MS, now);
  const bool control_link_stale = ecu_can_stale || pi_can_stale;
  const uint16_t cap = modeBoostCap(g_commands.mode);
  uint16_t target = min(g_commands.boost_target_psi_x10, cap);

  const bool knock = g_inputs.knock_bits != 0;
  const bool hot =
      (g_inputs.iat_c_x10 > 650) ||
      (g_inputs.egt_left_c_x10 > 9300) ||
      (g_inputs.egt_right_c_x10 > 9300) ||
      (g_inputs.coolant_c_x10 > 1160) ||
      (g_inputs.oil_temp_c_x10 > 1400);
  const bool low_oil_pressure = (g_inputs.rpm > 2200) && (g_inputs.oil_pressure_psi_x10 > 0) && (g_inputs.oil_pressure_psi_x10 < 80);
  const bool voltage_fault = (g_inputs.battery_mv > 0) && (g_inputs.battery_mv < 10500 || g_inputs.battery_mv > 15500);
  const bool low_auth = !g_commands.nfc_ok;
  const bool ecu_sensor_fault = (g_inputs.rpm == 0 && g_inputs.tps_pct > 20);
  uint8_t limp_reason = LIMP_NONE;
  if (!g_commands.engine_run_enabled) limp_reason = LIMP_ENGINE_RUN_OFF;
  else if (g_commands.limp_mode) limp_reason = g_commands.limp_reason != LIMP_NONE ? g_commands.limp_reason : LIMP_PI_REQUEST;
  else if (ecu_can_stale) limp_reason = LIMP_ECU_CAN_STALE;
  else if (pi_can_stale) limp_reason = LIMP_PI_COMMAND_STALE;
  else if (hot) limp_reason = LIMP_THERMAL;
  else if (low_oil_pressure) limp_reason = LIMP_LOW_OIL_PRESS;
  else if (voltage_fault) limp_reason = LIMP_BATTERY_VOLTAGE;
  else if (knock && g_inputs.boost_psi_x10 > target) limp_reason = LIMP_KNOCK;
  else if (ecu_sensor_fault) limp_reason = LIMP_ECU_SENSOR;
  else if (low_auth) limp_reason = LIMP_NFC_AUTH;
  const bool limp = limp_reason != LIMP_NONE;
  g_limp_active = limp;
  g_limp_reason = limp_reason;

  if (limp) {
    target = 0;
    g_commands.flame_mode = false;
    g_airshot_latched = false;
    g_airshot_latched_since_ms = 0;
    g_airshot_wastegate_decouple_until_ms = 0;
  } else {
    if (hot) target = (target > 30) ? target - 30 : target;
    if (knock) target = (target > 20) ? target - 20 : target;
  }

  if (g_inputs.tps_pct < 50) {
    g_airshot_rearm_ready = true;
  }

  const bool manual_airshot_request = isAirShotRequestActive(now);
  if (!manual_airshot_request) {
    g_airshot_request_until_ms = 0;
  }
  if (shouldTriggerAirShot(manual_airshot_request)) {
    g_airshot_latched = true;
    g_airshot_rearm_ready = false;
    g_airshot_latched_since_ms = now;
    g_airshot_wastegate_decouple_until_ms = 0;
    g_airshot_request_until_ms = 0;
  }

  const uint16_t airshot_limit = requestedBoostLimitForAirShot();
  const bool airshot_timed_out = g_airshot_latched_since_ms != 0 && (now - g_airshot_latched_since_ms) >= AIRSHOT_MAX_LATCH_MS;
  const bool intake_pressure_at_or_above_tank = g_inputs.boost_psi_x10 >= g_outputs.tank_psi_x10;
  if (
      g_airshot_latched &&
      (g_inputs.boost_psi_x10 >= airshot_limit || intake_pressure_at_or_above_tank || airshot_timed_out || limp || airshot_limit == 0)
  ) {
    if (!limp && airshot_limit > 0 && (g_inputs.boost_psi_x10 >= airshot_limit || intake_pressure_at_or_above_tank)) {
      g_airshot_wastegate_decouple_until_ms = now + AIRSHOT_WASTEGATE_DECOUPLE_MS;
    }
    g_airshot_latched = false;
    g_airshot_latched_since_ms = 0;
  }

  digitalWrite(AIRSHOT_SOL_PIN, g_airshot_latched ? HIGH : LOW);
  g_outputs.air_shot_remaining = calculateShotsRemaining(g_outputs.tank_psi_x10);

  const bool airshot_decoupling_wastegate =
      target > 0 &&
      !limp &&
      (g_airshot_latched || static_cast<int32_t>(g_airshot_wastegate_decouple_until_ms - now) >= 0) &&
      static_cast<uint32_t>(g_inputs.boost_psi_x10) <= static_cast<uint32_t>(target) + AIRSHOT_WASTEGATE_GUARD_PSI_X10;
  const uint16_t boost_for_wastegate = airshot_decoupling_wastegate ? min(g_inputs.boost_psi_x10, target) : g_inputs.boost_psi_x10;
  g_outputs.wg1_duty = computeWastegatePosition(target, boost_for_wastegate, g_inputs.tps_pct, knock);
  g_outputs.wg2_duty = g_outputs.wg1_duty; // mirrored for twin control output frame.

  const uint8_t wg1_pwm = map(g_outputs.wg1_duty, 0, 100, 0, 255);
  const uint8_t wg2_pwm = map(g_outputs.wg2_duty, 0, 100, 0, 255);
  digitalWrite(WG1_EN_PIN, HIGH);
  digitalWrite(WG2_EN_PIN, HIGH);
  digitalWrite(WG1_DIR_PIN, HIGH);
  digitalWrite(WG2_DIR_PIN, HIGH);
  analogWrite(WG1_PWM_PIN, wg1_pwm);
  analogWrite(WG2_PWM_PIN, wg2_pwm);

  // Ancillary controls handled Arduino-side.
  const bool wmi_conditions =
      g_commands.nfc_ok && !limp && !control_link_stale && g_commands.wmi_arm &&
      g_inputs.rpm > 3300 && g_inputs.tps_pct > 38 && g_inputs.boost_psi_x10 >= 60;
  const bool legacy_trigger = (g_commands.wmi_trigger_pct_x10 > 0) && (g_inputs.tps_pct > 45) && g_commands.nfc_ok && !control_link_stale;
  const bool wmi_enable = wmi_conditions || legacy_trigger;

  const float boost_ratio = constrain(g_inputs.boost_psi_x10 / 220.0f, 0.0f, 1.0f);
  const float target_ratio = constrain(g_commands.boost_target_psi_x10 / 220.0f, 0.0f, 1.0f);
  const float load_ratio = constrain(max(g_inputs.tps_pct, g_inputs.engine_load_pct) / 100.0f, 0.0f, 1.0f);
  const float rpm_ratio = constrain((g_inputs.rpm - 3000) / 9000.0f, 0.0f, 1.0f);
  const float fuel_gain = wmiFuelGain(g_inputs.fuel_code);

  float demand = 0.0f;
  if (wmi_enable) {
    demand = (0.42f * boost_ratio) + (0.24f * target_ratio) + (0.22f * load_ratio) + (0.12f * rpm_ratio);
    demand *= fuel_gain;
    demand = constrain(demand, 0.0f, 1.0f);
  }

  const uint8_t wmi_pwm = static_cast<uint8_t>(roundf(demand * 255.0f));
  analogWrite(WMI_PUMP_PIN, wmi_pwm);

  g_outputs.wmi_commanded_flow_cc_min = static_cast<uint16_t>(roundf(demand * 1400.0f));
  updateWmiSensorOutputs(wmi_enable);

  const bool flame_enable = g_commands.flame_mode && (g_inputs.rpm > 3000) && g_commands.nfc_ok && !limp && !control_link_stale;
  digitalWrite(FLAME_EN_PIN, flame_enable ? HIGH : LOW);

  const float vehicle_speed_mps = max(g_front_wheel_mps, g_rear_wheel_mps);
  const bool bike_stationary = vehicle_speed_mps < AIRSHOT_COMPRESSOR_MAX_SPEED_MPS;
  const bool low_throttle = g_inputs.tps_pct < 5;
  const bool compressor_on =
      bike_stationary &&
      low_throttle &&
      !g_airshot_latched &&
      g_inputs.rpm < 1800 &&
      g_outputs.tank_psi_x10 < AIRSHOT_COMPRESSOR_ON_PSI_X10;
  digitalWrite(AIR_COMPRESSOR_RELAY_PIN, compressor_on ? HIGH : LOW);
  if (g_outputs.tank_psi_x10 >= AIRSHOT_COMPRESSOR_OFF_PSI_X10 || !bike_stationary || !low_throttle || g_airshot_latched) {
    digitalWrite(AIR_COMPRESSOR_RELAY_PIN, LOW);
  }
  static float filtered_slip_ratio = 0.0f;
  static bool tc_latched = false;
  const float front_speed = g_front_wheel_mps;
  const float rear_speed = g_rear_wheel_mps;
  const float base_speed = max(1.0f, front_speed);
  const float raw_slip_ratio = (rear_speed - front_speed) / base_speed;
  filtered_slip_ratio = (filtered_slip_ratio * 0.65f) + (raw_slip_ratio * 0.35f);
  const float vehicle_speed = max(front_speed, rear_speed);
  const bool wheel_speed_ok = vehicle_speed >= TC_MIN_SPEED_MPS;
  const bool wheel_speed_sensor_fault = wheel_speed_ok && ((front_speed < 0.5f && rear_speed > 5.0f) || (rear_speed < 0.5f && front_speed > 5.0f));
  const float tc_limit = tcSlipLimitForLevel(g_commands.traction_level);
  const bool tc_allowed = !wheel_speed_sensor_fault && (g_commands.traction_level != TC_OFF) && (g_inputs.tps_pct > 20) && (g_inputs.gear >= 2) && wheel_speed_ok;
  if (tc_allowed && filtered_slip_ratio > tc_limit) {
    tc_latched = true;
  } else if (!tc_allowed || filtered_slip_ratio < (tc_limit - TC_EXIT_HYSTERESIS)) {
    tc_latched = false;
  }
  const bool tc_active = tc_latched && tc_allowed;
  const uint8_t requested_torque_cut_pct = tc_active ? torqueCutForSlip(filtered_slip_ratio, tc_limit) : 0;
  if (requested_torque_cut_pct > g_outputs.traction_torque_cut_pct) {
    g_outputs.traction_torque_cut_pct = min<uint8_t>(requested_torque_cut_pct, g_outputs.traction_torque_cut_pct + 4);
  } else if (g_outputs.traction_torque_cut_pct > requested_torque_cut_pct) {
    const uint8_t step = min<uint8_t>(8, g_outputs.traction_torque_cut_pct - requested_torque_cut_pct);
    g_outputs.traction_torque_cut_pct -= step;
  }
  g_outputs.traction_slip_pct_x10 = static_cast<int16_t>(constrain(static_cast<int>(roundf(filtered_slip_ratio * 1000.0f)), -1000, 1000));
  g_outputs.traction_active = tc_active || g_outputs.traction_torque_cut_pct > 0;
  g_outputs.traction_sensor_fault = wheel_speed_sensor_fault;
  const uint8_t torque_cut_pct = !g_commands.engine_run_enabled ? 100 : (g_outputs.traction_sensor_fault ? 0 : g_outputs.traction_torque_cut_pct);
  uint8_t torque_cut_payload[1] = {torque_cut_pct};
  publishFrame(CanId::ARD_TO_ECU_TORQUE_CUT, torque_cut_payload, 1);
  uint8_t slip_payload[3] = {
    uint8_t(g_outputs.traction_slip_pct_x10 >> 8),
    uint8_t(g_outputs.traction_slip_pct_x10 & 0xFF),
    static_cast<uint8_t>(g_outputs.traction_sensor_fault ? 0x02 : (g_outputs.traction_active ? 0x01 : 0x00))
  };
  publishFrame(CanId::ARD_TO_ECU_TRACTION_SLIP, slip_payload, 3);

  g_outputs.awc_active = tc_active;
  g_outputs.turbo1_psi_x10 = g_inputs.boost_psi_x10;
  g_outputs.turbo2_psi_x10 = g_inputs.boost_psi_x10;
  g_outputs.lean_deg = g_outputs.awc_active ? 8 : 3;

  const bool neutral_active = (digitalRead(NEUTRAL_SWITCH_PIN) == LOW);
  const float speed_mph = max(g_front_wheel_mps, g_rear_wheel_mps) * 2.236936f;
  g_inputs.gear = computeGearFromSpeedRpm(speed_mph, g_inputs.rpm, neutral_active);

  g_outputs.clutch_slip_pct = 0;
  g_outputs.clutch_slip_severity = 0;
  if (!neutral_active && g_inputs.gear >= 1 && g_inputs.gear <= 6 && speed_mph > 10.0f && g_inputs.rpm > 2500) {
    const float observed = g_inputs.rpm / max(1.0f, speed_mph);
    const float expected = GEAR_RATIO_FROM_RPM_MPH[g_inputs.gear];
    if (expected > 0.0f) {
      const float pct_diff = fabsf(observed - expected) / expected * 100.0f;
      g_outputs.clutch_slip_pct = static_cast<uint8_t>(constrain(static_cast<int>(roundf(pct_diff)), 0, 100));
      g_outputs.clutch_slip_severity = classifyClutchSlipSeverity(pct_diff);
    }
  }
}

void publishStatusFrames() {
  uint8_t airshot[2] = {g_outputs.air_shot_remaining, static_cast<uint8_t>(g_airshot_latched ? 1 : 0)};
  publishFrame(CanId::ARD_AIR_SHOT_STATUS, airshot, 2);

  uint8_t awc[2] = {static_cast<uint8_t>(g_outputs.awc_active ? 1 : 0), static_cast<uint8_t>(g_outputs.lean_deg)};
  publishFrame(CanId::ARD_AWC_STATE, awc, 2);

  uint8_t rgb[3] = {255, 96, 0};
  publishFrame(CanId::ARD_RGB_LIGHTING, rgb, 3);

  uint8_t lights[1] = {readLightingStatus()};
  publishFrame(CanId::ARD_LIGHT_STATUS, lights, 1);

  const uint16_t oil_pressure = readOilPressurePsiX10();
  uint8_t oilp[2] = {uint8_t(oil_pressure >> 8), uint8_t(oil_pressure & 0xFF)};
  publishFrame(CanId::ARD_OIL_PRESSURE_STATUS, oilp, 2);

  uint8_t fuel_type[1] = {g_inputs.fuel_code};
  publishFrame(CanId::ARD_FUEL_TYPE_STATUS, fuel_type, 1);

  uint8_t tank[2] = {uint8_t(g_outputs.tank_psi_x10 >> 8), uint8_t(g_outputs.tank_psi_x10 & 0xFF)};
  publishFrame(CanId::ARD_TANK_PRESSURE, tank, 2);

  uint8_t twin[4] = {
    uint8_t(g_outputs.turbo1_psi_x10 >> 8), uint8_t(g_outputs.turbo1_psi_x10 & 0xFF),
    uint8_t(g_outputs.turbo2_psi_x10 >> 8), uint8_t(g_outputs.turbo2_psi_x10 & 0xFF)
  };
  publishFrame(CanId::ARD_TWIN_TURBO_STATUS, twin, 4);

  uint8_t wg[2] = {g_outputs.wg1_duty, g_outputs.wg2_duty};
  publishFrame(CanId::ARD_WASTEGATE_STATUS, wg, 2);

  uint8_t gear[1] = {g_inputs.gear};
  publishFrame(CanId::ARD_GEAR_POSITION, gear, 1);

  uint8_t fuel[1] = {g_outputs.fuel_level_pct};
  publishFrame(CanId::ARD_FUEL_LEVEL, fuel, 1);

  uint8_t wmi[6] = {
    uint8_t(g_outputs.wmi_tank_level_pct),
    uint8_t(g_outputs.wmi_commanded_flow_cc_min >> 8), uint8_t(g_outputs.wmi_commanded_flow_cc_min & 0xFF),
    uint8_t(g_outputs.wmi_actual_flow_cc_min >> 8), uint8_t(g_outputs.wmi_actual_flow_cc_min & 0xFF),
    uint8_t(g_outputs.wmi_fault ? 1 : 0)
  };
  publishFrame(CanId::ARD_WMI_STATUS, wmi, 6);

  uint8_t clutch_slip[2] = {g_outputs.clutch_slip_pct, g_outputs.clutch_slip_severity};
  publishFrame(CanId::ARD_CLUTCH_SLIP_STATUS, clutch_slip, 2);

  uint8_t traction_status[4] = {
    uint8_t(g_outputs.traction_slip_pct_x10 >> 8),
    uint8_t(g_outputs.traction_slip_pct_x10 & 0xFF),
    g_outputs.traction_torque_cut_pct,
    static_cast<uint8_t>((g_outputs.traction_active ? 0x01 : 0x00) | (g_outputs.traction_sensor_fault ? 0x02 : 0x00))
  };
  publishFrame(CanId::ARD_TRACTION_STATUS, traction_status, 4);

  uint8_t limp_status[2] = {static_cast<uint8_t>(g_limp_active ? 1 : 0), g_limp_reason};
  publishFrame(CanId::ARD_LIMP_STATUS, limp_status, 2);

  uint16_t front_mps_x100 = static_cast<uint16_t>(constrain(static_cast<int>(g_front_wheel_mps * 100.0f), 0, 65535));
  uint16_t rear_mps_x100 = static_cast<uint16_t>(constrain(static_cast<int>(g_rear_wheel_mps * 100.0f), 0, 65535));
  uint8_t wheel[4] = {uint8_t(front_mps_x100 >> 8), uint8_t(front_mps_x100 & 0xFF), uint8_t(rear_mps_x100 >> 8), uint8_t(rear_mps_x100 & 0xFF)};
  publishFrame(CanId::ARD_WHEEL_SPEED, wheel, 4);

  static uint32_t last_service_ms = 0;
  static uint32_t last_firmware_ms = 0;
  const uint32_t now = millis();
  if (now - last_service_ms >= 250) {
    last_service_ms = now;
    const uint16_t oil_sensor_mv = adcRawToMillivolts(analogRead(OIL_PRESSURE_SENSOR_PIN));
    const uint16_t wmi_tank_mv = adcRawToMillivolts(analogRead(WMI_TANK_LEVEL_PIN));
    const uint16_t air_tank_mv = adcRawToMillivolts(analogRead(AIR_TANK_PRESSURE_SENSOR_PIN));
    uint8_t sensor_voltage[8] = {
      uint8_t(oil_sensor_mv >> 8), uint8_t(oil_sensor_mv & 0xFF),
      uint8_t(wmi_tank_mv >> 8), uint8_t(wmi_tank_mv & 0xFF),
      uint8_t(5000 >> 8), uint8_t(5000 & 0xFF),
      uint8_t(air_tank_mv >> 8), uint8_t(air_tank_mv & 0xFF)
    };
    publishFrame(CanId::ARD_SERVICE_SENSOR_VOLTAGES, sensor_voltage, 8);

    uint8_t input_bits = readLightingStatus();
    if (readWmiPressureOk()) input_bits |= 0x40;
    if (digitalRead(CAN_INT_PIN) == LOW) input_bits |= 0x80;

    uint8_t output_bits = 0;
    if (digitalRead(WG1_EN_PIN) == HIGH) output_bits |= 0x01;
    if (digitalRead(WG2_EN_PIN) == HIGH) output_bits |= 0x02;
    if (digitalRead(WMI_PUMP_PIN) == HIGH) output_bits |= 0x04;
    if (digitalRead(FLAME_EN_PIN) == HIGH) output_bits |= 0x08;
    if (digitalRead(AIRSHOT_SOL_PIN) == HIGH) output_bits |= 0x10;
    if (digitalRead(AIR_COMPRESSOR_RELAY_PIN) == HIGH) output_bits |= 0x20;
    if (digitalRead(WG1_DIR_PIN) == HIGH) output_bits |= 0x40;
    if (digitalRead(WG2_DIR_PIN) == HIGH) output_bits |= 0x80;

    uint8_t command_bits = 0;
    if (g_commands.nfc_ok) command_bits |= 0x01;
    if (g_commands.flame_mode) command_bits |= 0x02;
    if (g_commands.limp_mode) command_bits |= 0x04;
    if (g_commands.engine_run_enabled) command_bits |= 0x08;
    if (g_commands.wmi_arm) command_bits |= 0x10;
    if (isAirShotRequestActive(now)) command_bits |= 0x20;

    uint8_t fault_bits = 0;
    if (elapsedSince(g_last_ecu_frame_ms, ECU_CAN_TIMEOUT_MS, now)) fault_bits |= 0x01;
    if (elapsedSince(g_last_pi_command_ms, PI_CAN_TIMEOUT_MS, now)) fault_bits |= 0x02;
    if (g_outputs.wmi_fault) fault_bits |= 0x04;
    if (g_outputs.traction_sensor_fault) fault_bits |= 0x08;

    uint8_t digital_states[4] = {input_bits, output_bits, command_bits, fault_bits};
    publishFrame(CanId::ARD_SERVICE_DIGITAL_STATES, digital_states, 4);
  }

  if (now - last_firmware_ms >= 2000) {
    last_firmware_ms = now;
    uint8_t firmware[6] = {
      0x01,
      FIRMWARE_VERSION_MAJOR,
      FIRMWARE_VERSION_MINOR,
      FIRMWARE_VERSION_PATCH,
      uint8_t(FIRMWARE_BUILD >> 8),
      uint8_t(FIRMWARE_BUILD & 0xFF)
    };
    publishFrame(CanId::ARD_SERVICE_FIRMWARE_VERSION, firmware, 6);
  }
}

void setup() {
  pinMode(CAN_INT_PIN, INPUT_PULLUP);
  pinMode(CAN_CS_PIN, OUTPUT);
  pinMode(SPI_SS_PIN, OUTPUT);
  pinMode(WG1_PWM_PIN, OUTPUT);
  pinMode(WG1_DIR_PIN, OUTPUT);
  pinMode(WG1_EN_PIN, OUTPUT);
  pinMode(WG2_PWM_PIN, OUTPUT);
  pinMode(WG2_DIR_PIN, OUTPUT);
  pinMode(WG2_EN_PIN, OUTPUT);
  pinMode(WMI_PUMP_PIN, OUTPUT);
  pinMode(FLAME_EN_PIN, OUTPUT);
  pinMode(AIRSHOT_SOL_PIN, OUTPUT);
  pinMode(AIR_COMPRESSOR_RELAY_PIN, OUTPUT);
  pinMode(FRONT_WHEEL_HALL_PIN, INPUT_PULLUP);
  pinMode(REAR_WHEEL_HALL_PIN, INPUT_PULLUP);
  pinMode(NEUTRAL_SWITCH_PIN, INPUT_PULLUP);
  pinMode(LEFT_INDICATOR_PIN, INPUT);
  pinMode(RIGHT_INDICATOR_PIN, INPUT);
  pinMode(HIGH_BEAM_PIN, INPUT);
  pinMode(BRAKE_LIGHT_PIN, INPUT);
  pinMode(OIL_WARNING_PIN, INPUT);
  pinMode(OIL_PRESSURE_SENSOR_PIN, INPUT);
  pinMode(WMI_TANK_LEVEL_PIN, INPUT);
  pinMode(AIR_TANK_PRESSURE_SENSOR_PIN, INPUT);
  pinMode(WMI_FLOW_SENSOR_PIN, INPUT_PULLUP);
  pinMode(WMI_PRESSURE_OK_PIN, INPUT_PULLUP);
  const int front_irq = digitalPinToInterrupt(FRONT_WHEEL_HALL_PIN);
  const int rear_irq = digitalPinToInterrupt(REAR_WHEEL_HALL_PIN);
  const int wmi_irq = digitalPinToInterrupt(WMI_FLOW_SENSOR_PIN);
  if (front_irq >= 0) attachInterrupt(front_irq, frontWheelPulseISR, RISING);
  if (rear_irq >= 0) attachInterrupt(rear_irq, rearWheelPulseISR, RISING);
  if (wmi_irq >= 0) attachInterrupt(wmi_irq, wmiFlowPulseISR, RISING);

  digitalWrite(CAN_CS_PIN, HIGH);
  digitalWrite(SPI_SS_PIN, HIGH);
  digitalWrite(WG1_EN_PIN, LOW);
  digitalWrite(WG2_EN_PIN, LOW);
  digitalWrite(WMI_PUMP_PIN, LOW);
  digitalWrite(FLAME_EN_PIN, LOW);
  digitalWrite(AIRSHOT_SOL_PIN, LOW);
  digitalWrite(AIR_COMPRESSOR_RELAY_PIN, LOW);

  while (CAN_OK != CANBUS.begin(MCP_ANY, CAN_BITRATE, MCP_8MHZ)) {
    delay(100);
  }
  CANBUS.setMode(MCP_NORMAL);
}

void loop() {
  if (digitalRead(CAN_INT_PIN) == LOW) {
    unsigned long rxId = 0;
    uint8_t len = 0;
    uint8_t buf[8] = {0};
    if (CAN_OK == CANBUS.readMsgBuf(&rxId, &len, buf)) {
      handleFrame(static_cast<uint16_t>(rxId), len, buf);
    }
  }

  static uint32_t lastControlMs = 0;
  static uint32_t lastPublishMs = 0;
  const uint32_t now = millis();

  if (now - lastControlMs >= 10) { // 100 Hz control update
    lastControlMs = now;
    updateControllers();
  }

  if (now - lastPublishMs >= 50) { // 20 Hz status broadcast
    lastPublishMs = now;
    publishStatusFrames();
  }
}
