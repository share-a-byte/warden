#include <Arduino.h>
#include <Servo.h>

// GATE DEMO: controller D9 -> guardian D2 (NOT directly to relay NO).
// Both boards must use the same CLOSED_US and OPEN_US calibration.
constexpr uint8_t COMMAND_PIN = 9;
constexpr int CLOSED_US = 1000; // Nominal 0 degrees with a 1000..2000 us range.
constexpr int OPEN_US = 2000;   // Nominal 90 degrees. Mount the horn accordingly.
constexpr uint32_t DOWN_TIME_MS = 3000;
constexpr uint32_t UP_TIME_MS = 2000;
Servo requestedGate;
bool forcedOpen = false;
uint32_t cycleStartedMs = 0;
int lastCommandUs = CLOSED_US;

void setup() {
  Serial.begin(115200);
  requestedGate.attach(COMMAND_PIN, 1000, 2000);
  requestedGate.writeMicroseconds(CLOSED_US);
  cycleStartedMs = millis();
  Serial.println("GATE CONTROLLER: automatic down 3s / up 2s.");
  Serial.println("x = simulated override (hold OPEN); n = restore normal cycle.");
}

void loop() {
  const uint32_t now = millis();
  if (Serial.available()) {
    const char c = Serial.read();
    if (c == 'x') {
      forcedOpen = true;
      Serial.println("OVERRIDE: controller continuously requests OPEN.");
    } else if (c == 'n') {
      forcedOpen = false;
      cycleStartedMs = now;
      Serial.println("Normal cycle restored, beginning with gate DOWN.");
    }
  }
  const uint32_t phase = uint32_t(now - cycleStartedMs) % (DOWN_TIME_MS + UP_TIME_MS);
  const int commandUs = (forcedOpen || phase >= DOWN_TIME_MS) ? OPEN_US : CLOSED_US;
  if (commandUs != lastCommandUs) {
    lastCommandUs = commandUs;
    requestedGate.writeMicroseconds(commandUs);
    Serial.println(commandUs == OPEN_US ? "Request: OPEN" : "Request: DOWN");
  }
}
