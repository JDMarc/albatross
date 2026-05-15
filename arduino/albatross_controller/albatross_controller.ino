#include <SPI.h>
#include <mcp_can.h>
#include <math.h>

// Target board: Arduino Mega 2560 Rev3
// --- CAN bus wiring/config ---
static constexpr uint8_t CAN_CS_PIN = 10;
static constexpr uint8_t CAN_INT_PIN = 2;
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
  constexpr uint16_t ECU_FUEL = 0x107;
  constexpr uint16_t ECU_GEAR = 0x108;
  constexpr uint16_t ECU_LOAD = 0x109;
  constexpr uint16_t ECU_IAT = 0x10A;
  constexpr uint16_t ECU_EGT = 0x10B;

  constexpr uint16_t ECU_TO_ARD_FLAME_STATUS = 0x110;
  constexpr uint16_t ECU_TO_ARD_WMI_TRIGGER = 0x111;
  constexpr uint16_t ECU_TO_ARD_ENGINE_STATUS = 0x112;
  constexpr uint16_t ARD_TO_ECU_TORQUE_CUT = 0x125;

  constexpr uint16_t PI_BOOST_TARGET = 0x120;
  constexpr uint16_t PI_MODE_SELECT = 0x121;
  constexpr uint16_t PI_FLAME_MODE = 0x122;
  constexpr uint16_t PI_LIMP_MODE = 0x123;
  constexpr uint16_t PI_TRACTION_LEVEL = 0x124;
  constexpr uint16_t PI_NFC_AUTH = 0x140;

  constexpr uint16_t ARD_AIR_SHOT_STATUS = 0x130;
  constexpr uint16_t ARD_AWC_STATE = 0x131;
  constexpr uint16_t ARD_RGB_LIGHTING = 0x132;
  constexpr uint16_t ARD_TANK_PRESSURE = 0x133;
  constexpr uint16_t ARD_TWIN_TURBO_STATUS = 0x134;
  constexpr uint16_t ARD_WASTEGATE_STATUS = 0x135;
  constexpr uint16_t ARD_WHEEL_SPEED = 0x137;

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
  uint8_t knock_bits = 0;
  uint16_t iat_c_x10 = 250;
  uint16_t egt_left_c_x10 = 7500;
  uint16_t egt_right_c_x10 = 7500;
  uint8_t engine_status = 0;
  uint8_t gear = 0;
};

struct Commands {
  uint16_t boost_target_psi_x10 = 80; // 8.0 psi safe fallback
  RideMode mode = MODE_NORMAL;
  bool nfc_ok = false;
  bool flame_mode = false;
  bool limp_mode = false;
  uint16_t wmi_trigger_pct_x10 = 0;
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
};

Inputs g_inputs;
Commands g_commands;
Outputs g_outputs;

// --- Hardware pins ---
// Two 3-pin electronic wastegate actuators (PWM + DIR + EN each).
static constexpr uint8_t WG1_PWM_PIN = 5;
static constexpr uint8_t WG1_DIR_PIN = 22;
static constexpr uint8_t WG1_EN_PIN = 23;
static constexpr uint8_t WG2_PWM_PIN = 6;
static constexpr uint8_t WG2_DIR_PIN = 24;
static constexpr uint8_t WG2_EN_PIN = 25;
static constexpr uint8_t WMI_PUMP_PIN = 7;     // Water/meth pump relay (active HIGH)
static constexpr uint8_t FLAME_EN_PIN = 8;     // Flame mode interlock output
static constexpr uint8_t AIRSHOT_SOL_PIN = 9;  // Air shot solenoid output
static constexpr uint8_t AIR_COMPRESSOR_RELAY_PIN = 10; // Air tank compressor relay
// Mega 2560 external interrupt-capable pins: 2,3,18,19,20,21
static constexpr uint8_t FRONT_WHEEL_HALL_PIN = 18;
static constexpr uint8_t REAR_WHEEL_HALL_PIN = 19;

// Placeholder base boost caps by mode (psi*10).
uint16_t modeBoostCap(uint8_t mode) {
  switch (mode) {
    case MODE_ECO: return 70;       // 7.0 psi
    case MODE_NORMAL: return 110;   // 11.0 psi
    case MODE_SPORT: return 150;    // 15.0 psi
    case MODE_RACE: return 180;     // 18.0 psi
    case MODE_ALBATROSS: return 210;// 21.0 psi
    default: return 80;
  }
}

static inline uint16_t clampU16(uint16_t v, uint16_t lo, uint16_t hi) {
  return (v < lo) ? lo : ((v > hi) ? hi : v);
}

uint8_t computeWastegatePosition(uint16_t target_psi_x10, uint16_t actual_psi_x10, uint8_t tps_pct, bool knock) {
  // Designed for a traditional electronic wastegate actuator.
  // Output is an actuator position request over PWM (0-100%).
  const int16_t error = static_cast<int16_t>(target_psi_x10) - static_cast<int16_t>(actual_psi_x10);
  int16_t duty = 0;

  // Basic feed-forward by requested level.
  duty += (target_psi_x10 > 70) ? map(target_psi_x10, 70, 220, 10, 78) : 0;

  // P-term trim.
  duty += error / 2;

  // Throttle gating keeps spool behavior predictable and safe.
  if (tps_pct < 20) duty = 0;
  else if (tps_pct < 40) duty = min<int16_t>(duty, 35);

  // Safety trims.
  if (knock) duty -= 20;

  // Clamp to actuator travel limits.
  duty = constrain(duty, 0, 100);
  return static_cast<uint8_t>(duty);
}

void publishFrame(uint16_t id, const uint8_t *data, uint8_t len) {
  CANBUS.sendMsgBuf(id, 0, len, const_cast<uint8_t *>(data));
}

void handleFrame(uint16_t id, uint8_t len, const uint8_t *data) {
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
      if (len >= 1) g_inputs.knock_bits = data[0];
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
      break;
    case CanId::PI_TRACTION_LEVEL:
      if (len >= 1) g_commands.traction_level = static_cast<TractionLevel>(data[0]);
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
static volatile uint32_t g_front_pulses = 0;
static volatile uint32_t g_rear_pulses = 0;
static float g_front_wheel_mps = 0.0f;
static float g_rear_wheel_mps = 0.0f;

struct WheelConfig {
  float circumference_m;
  uint8_t magnets;
};

static constexpr WheelConfig FRONT_WHEEL = {1.95f, 6};
static constexpr WheelConfig REAR_WHEEL = {1.99f, 6};

void frontWheelPulseISR() { g_front_pulses++; }
void rearWheelPulseISR() { g_rear_pulses++; }

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
  return static_cast<uint8_t>(constrain(static_cast<int>(excess * 220.0f), 0, 100));
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


uint16_t modeBoostLimitForAirShot(uint8_t mode) {
  switch (mode) {
    case MODE_RACE: return 180;
    case MODE_ALBATROSS: return 210;
    default: return 0;
  }
}

uint8_t calculateShotsRemaining(uint16_t tank_psi_x10) {
  const float psi = tank_psi_x10 / 10.0f;
  if (psi <= 18.0f) return 0;
  if (psi >= 68.0f) return 5;
  const float normalized = (psi - 18.0f) / 50.0f;
  const float curved = logf(1.0f + normalized * 9.0f) / logf(10.0f);
  return static_cast<uint8_t>(constrain(static_cast<int>(roundf(curved * 5.0f)), 0, 5));
}

bool shouldTriggerAirShot() {
  const bool mode_ok = (g_commands.mode == MODE_RACE) || (g_commands.mode == MODE_ALBATROSS);
  return mode_ok && g_airshot_rearm_ready && !g_airshot_latched && g_inputs.tps_pct > 90 && g_inputs.gear >= 2 && g_inputs.rpm > 5500 && calculateShotsRemaining(g_outputs.tank_psi_x10) > 0;
}

void updateControllers() {
  const uint16_t cap = modeBoostCap(g_commands.mode);
  uint16_t target = min(g_commands.boost_target_psi_x10, cap);

  const bool knock = g_inputs.knock_bits != 0;
  const bool hot = (g_inputs.iat_c_x10 > 650) || (g_inputs.egt_left_c_x10 > 9300) || (g_inputs.egt_right_c_x10 > 9300);
  const bool low_auth = !g_commands.nfc_ok;
  const bool sensor_fault = (g_inputs.rpm == 0 && g_inputs.tps_pct > 20);
  const bool limp = g_commands.limp_mode || hot || (knock && g_inputs.boost_psi_x10 > target) || sensor_fault || low_auth;

  if (limp) {
    target = 0;
    g_commands.flame_mode = false;
  } else {
    if (hot) target = (target > 30) ? target - 30 : target;
    if (knock) target = (target > 20) ? target - 20 : target;
  }

  g_outputs.wg1_duty = computeWastegatePosition(target, g_inputs.boost_psi_x10, g_inputs.tps_pct, knock);
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
  const bool wmi_enable = (g_commands.wmi_trigger_pct_x10 > 0) && (g_inputs.tps_pct > 45) && g_commands.nfc_ok;
  digitalWrite(WMI_PUMP_PIN, wmi_enable ? HIGH : LOW);

  const bool flame_enable = g_commands.flame_mode && (g_inputs.rpm > 3000) && g_commands.nfc_ok && !limp;
  digitalWrite(FLAME_EN_PIN, flame_enable ? HIGH : LOW);

  const bool compressor_on = (g_outputs.tank_psi_x10 < 680) && (g_inputs.rpm < 1500) && (g_inputs.tps_pct < 5);
  digitalWrite(AIR_COMPRESSOR_RELAY_PIN, compressor_on ? HIGH : LOW);
  if (g_outputs.tank_psi_x10 >= 700) {
    digitalWrite(AIR_COMPRESSOR_RELAY_PIN, LOW);
  }

  if (g_inputs.tps_pct < 50) {
    g_airshot_rearm_ready = true;
  }

  if (shouldTriggerAirShot()) {
    g_airshot_latched = true;
    g_airshot_rearm_ready = false;
  }

  const uint16_t airshot_limit = modeBoostLimitForAirShot(g_commands.mode);
  if (g_airshot_latched && (g_inputs.boost_psi_x10 >= airshot_limit || limp || airshot_limit == 0)) {
    g_airshot_latched = false;
  }

  digitalWrite(AIRSHOT_SOL_PIN, g_airshot_latched ? HIGH : LOW);

  g_outputs.air_shot_remaining = calculateShotsRemaining(g_outputs.tank_psi_x10);

  updateWheelSpeeds();
  const float base_speed = max(0.1f, g_front_wheel_mps);
  const float slip_ratio = (g_rear_wheel_mps - g_front_wheel_mps) / base_speed;
  const float tc_limit = tcSlipLimitForLevel(g_commands.traction_level);
  const bool tc_active = (g_commands.traction_level != TC_OFF) && (g_inputs.tps_pct > 20) && (g_inputs.gear >= 2) && (slip_ratio > tc_limit);
  const uint8_t torque_cut_pct = tc_active ? torqueCutForSlip(slip_ratio, tc_limit) : 0;
  uint8_t torque_cut_payload[1] = {torque_cut_pct};
  publishFrame(CanId::ARD_TO_ECU_TORQUE_CUT, torque_cut_payload, 1);

  g_outputs.awc_active = tc_active;
  g_outputs.turbo1_psi_x10 = g_inputs.boost_psi_x10;
  g_outputs.turbo2_psi_x10 = g_inputs.boost_psi_x10;
  g_outputs.lean_deg = g_outputs.awc_active ? 8 : 3;
}

void publishStatusFrames() {
  uint8_t airshot[2] = {g_outputs.air_shot_remaining, static_cast<uint8_t>(g_airshot_latched ? 1 : 0)};
  publishFrame(CanId::ARD_AIR_SHOT_STATUS, airshot, 2);

  uint8_t awc[2] = {static_cast<uint8_t>(g_outputs.awc_active ? 1 : 0), static_cast<uint8_t>(g_outputs.lean_deg)};
  publishFrame(CanId::ARD_AWC_STATE, awc, 2);

  uint8_t rgb[3] = {255, 96, 0};
  publishFrame(CanId::ARD_RGB_LIGHTING, rgb, 3);

  uint8_t tank[2] = {uint8_t(g_outputs.tank_psi_x10 >> 8), uint8_t(g_outputs.tank_psi_x10 & 0xFF)};
  publishFrame(CanId::ARD_TANK_PRESSURE, tank, 2);

  uint8_t twin[4] = {
    uint8_t(g_outputs.turbo1_psi_x10 >> 8), uint8_t(g_outputs.turbo1_psi_x10 & 0xFF),
    uint8_t(g_outputs.turbo2_psi_x10 >> 8), uint8_t(g_outputs.turbo2_psi_x10 & 0xFF)
  };
  publishFrame(CanId::ARD_TWIN_TURBO_STATUS, twin, 4);

  uint8_t wg[2] = {g_outputs.wg1_duty, g_outputs.wg2_duty};
  publishFrame(CanId::ARD_WASTEGATE_STATUS, wg, 2);

  uint16_t front_mps_x100 = static_cast<uint16_t>(constrain(static_cast<int>(g_front_wheel_mps * 100.0f), 0, 65535));
  uint16_t rear_mps_x100 = static_cast<uint16_t>(constrain(static_cast<int>(g_rear_wheel_mps * 100.0f), 0, 65535));
  uint8_t wheel[4] = {uint8_t(front_mps_x100 >> 8), uint8_t(front_mps_x100 & 0xFF), uint8_t(rear_mps_x100 >> 8), uint8_t(rear_mps_x100 & 0xFF)};
  publishFrame(CanId::ARD_WHEEL_SPEED, wheel, 4);
}

void setup() {
  pinMode(CAN_INT_PIN, INPUT);
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
  const int front_irq = digitalPinToInterrupt(FRONT_WHEEL_HALL_PIN);
  const int rear_irq = digitalPinToInterrupt(REAR_WHEEL_HALL_PIN);
  if (front_irq >= 0) attachInterrupt(front_irq, frontWheelPulseISR, RISING);
  if (rear_irq >= 0) attachInterrupt(rear_irq, rearWheelPulseISR, RISING);

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
