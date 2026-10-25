#include <Arduino.h>
#include <Servo.h>

// NO SPLIT WIRES: controller D9 -> guardian D2.
// Guardian D10 -> relay NO (regenerated, policy-checked commands).
// Guardian D9 -> relay NC (always DOWN). Relay COM -> servo signal.
// Guardian D7 -> 1k resistor -> module S. Grounds must be common.
constexpr uint8_t INPUT_PIN = 2;
constexpr uint8_t NORMAL_OUTPUT_PIN = 10;
constexpr uint8_t FALLBACK_OUTPUT_PIN = 9;
constexpr uint8_t RELAY_PIN = 7;
constexpr int RELAY_ON = HIGH;  // Expected HIGH-trigger module.
constexpr int RELAY_OFF = (RELAY_ON == HIGH) ? LOW : HIGH;
constexpr int CLOSED_US = 1000;
constexpr int OPEN_US = 2000;
constexpr uint32_t TOLERANCE_US = 80;
constexpr uint32_t COMMAND_TIMEOUT_US = 150000;
constexpr uint32_t QUALIFY_CLOSED_MS = 500;
constexpr uint32_t MAX_OPEN_MS = 3500;

Servo normalOutput;
Servo fallbackOutput;
enum State { WAITING, RUNNING, LOCKED_DOWN };
State state = WAITING;
bool qualifying = false;
bool openRequested = false;
uint32_t qualifyingSinceMs = 0;
uint32_t openedAtMs = 0;
uint32_t lockedAtMs = 0;
int forwardedUs = CLOSED_US;

volatile bool haveRise = false;
volatile uint32_t riseUs = 0;
volatile bool haveCommand = false;
volatile uint32_t commandWidthUs = 0;
volatile uint32_t commandAtUs = 0;
volatile bool badPulseSeen = false;

// Return 0 for DOWN, 1 for OPEN, -1 for an unsupported pulse width.
int decodeCommand(uint32_t width) {
  if (width >= uint32_t(CLOSED_US) - TOLERANCE_US &&
      width <= uint32_t(CLOSED_US) + TOLERANCE_US) return 0;
  if (width >= uint32_t(OPEN_US) - TOLERANCE_US &&
      width <= uint32_t(OPEN_US) + TOLERANCE_US) return 1;
  return -1;
}

void onCommandEdge() {
  const uint32_t now = micros();
  if (digitalRead(INPUT_PIN) == HIGH) {
    haveRise = true;
    riseUs = now;
  } else if (haveRise) {
    haveRise = false;
    const uint32_t width = uint32_t(now - riseUs);
    commandWidthUs = width;
    commandAtUs = now;
    haveCommand = true;
    if (decodeCommand(width) < 0) badPulseSeen = true;
  }
}

void forwardCommand(int pulseUs) {
  if (pulseUs != forwardedUs) {
    forwardedUs = pulseUs;
    normalOutput.writeMicroseconds(pulseUs);
  }
}

void lockDown(const char *reason) {
  // Close BOTH guardian outputs, so even a stuck NO contact receives DOWN.
  forwardCommand(CLOSED_US);
  fallbackOutput.writeMicroseconds(CLOSED_US);
  digitalWrite(RELAY_PIN, RELAY_OFF);
  if (state != LOCKED_DOWN) lockedAtMs = millis();
  state = LOCKED_DOWN;
  qualifying = false;
  openRequested = false;
  Serial.print("OVERRIDE BLOCKED / GATE LOCKED DOWN: ");
  Serial.println(reason);
  Serial.println("Controller n, then guardian r, to recover.");
}

void setup() {
  digitalWrite(RELAY_PIN, RELAY_OFF);
  pinMode(RELAY_PIN, OUTPUT);
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, HIGH);
  Serial.begin(115200);
  fallbackOutput.attach(FALLBACK_OUTPUT_PIN, 1000, 2000);
  fallbackOutput.writeMicroseconds(CLOSED_US);
  normalOutput.attach(NORMAL_OUTPUT_PIN, 1000, 2000);
  normalOutput.writeMicroseconds(CLOSED_US);
  pinMode(INPUT_PIN, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(INPUT_PIN), onCommandEdge, CHANGE);
  Serial.println("GUARDIAN: waiting for 500 ms of valid DOWN commands.");
  Serial.println("t = local lockdown; r = request recovery after controller is fixed.");
}

void loop() {
  if (Serial.available()) {
    const char c = Serial.read();
    if (c == 't') lockDown("local manual test");
    if (c == 'r' && state == LOCKED_DOWN) {
      digitalWrite(RELAY_PIN, RELAY_OFF);
      forwardCommand(CLOSED_US);
      state = WAITING;
      qualifying = false;
      Serial.println("Recovery requested: waiting for valid DOWN commands.");
    }
  }

  noInterrupts();
  const bool seen = haveCommand;
  const uint32_t width = commandWidthUs;
  const uint32_t lastAt = commandAtUs;
  const bool bad = badPulseSeen;
  badPulseSeen = false;
  interrupts();
  const uint32_t nowUs = micros();
  const uint32_t nowMs = millis();
  const bool fresh = seen && uint32_t(nowUs - lastAt) < COMMAND_TIMEOUT_US;
  const int request = decodeCommand(width);
  const bool timersOK = normalOutput.attached() && fallbackOutput.attached();

  if (state == WAITING) {
    forwardCommand(CLOSED_US);
    if (!timersOK || !fresh || bad || request != 0) {
      qualifying = false;
    } else if (!qualifying) {
      qualifying = true;
      qualifyingSinceMs = nowMs;
    } else if (uint32_t(nowMs - qualifyingSinceMs) >= QUALIFY_CLOSED_MS) {
      openRequested = false;
      state = RUNNING;
      digitalWrite(RELAY_PIN, RELAY_ON);
      Serial.println("NORMAL: forwarding controller commands. Open limit = 3.5s.");
    }
  } else if (state == RUNNING) {
    if (!timersOK) lockDown("servo timer unavailable");
    else if (!fresh) lockDown("controller command signal missing");
    else if (bad || request < 0) lockDown("unsupported controller command");
    else if (request == 0) {
      openRequested = false;
      forwardCommand(CLOSED_US);
    } else {
      if (!openRequested) {
        openRequested = true;
        openedAtMs = nowMs;
      }
      if (uint32_t(nowMs - openedAtMs) >= MAX_OPEN_MS) {
        lockDown("controller held OPEN longer than 3.5 seconds");
      } else {
        forwardCommand(OPEN_US);
      }
    }
  }
  // LOCKED_DOWN ignores all controller requests until local recovery.
  if (state == LOCKED_DOWN) {
    digitalWrite(LED_BUILTIN, ((uint32_t(nowMs - lockedAtMs) / 200) % 2 == 0) ? HIGH : LOW);
  } else {
    digitalWrite(LED_BUILTIN, state == WAITING ? HIGH : LOW);
  }
}
