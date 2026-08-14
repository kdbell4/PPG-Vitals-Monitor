#include <Arduino.h>
#include <iostream>

// Phase 1 — breadboard analog front end validation.
// Goal: sample the filtered/amplified photodiode signal and stream it to
// Serial so it can be viewed on the Arduino IDE Serial Plotter (or
// PlatformIO's `pio device monitor`) to confirm a clean pulse waveform
// before committing anything to a PCB.

// Change this to whichever Teensy 4.0 analog pin the filter/gain stage
// output is wired to (A0-A9 broken out on the board).
constexpr uint8_t PPG_SIGNAL_PIN = A0;

// Sample rate for the pulse waveform. A resting heart rate tops out around
// 3 Hz; 250 Hz gives plenty of headroom for waveform shape (rise time,
// dicrotic notch) without flooding Serial.
constexpr uint32_t SAMPLE_RATE_HZ = 250;
constexpr uint32_t SAMPLE_PERIOD_US = 1000000UL / SAMPLE_RATE_HZ;

elapsedMicros sinceLastSample;

// Digital pin the breadboard LED's resistor leg is wired to.
// Change this to match your wiring.
constexpr uint8_t BREADBOARD_LED_PIN = 14;

void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
  pinMode(BREADBOARD_LED_PIN, OUTPUT);
  digitalWrite(BREADBOARD_LED_PIN, HIGH);
  pinMode(14, INPUT);

  Serial.begin(115200);
}

void loop() {
  if (sinceLastSample >= SAMPLE_PERIOD_US) {
    // Subtract rather than reset to 0 so timing doesn't drift if loop()
    // takes a little longer than SAMPLE_PERIOD_US on some iterations.
    sinceLastSample -= SAMPLE_PERIOD_US;

    int sample = analogRead(PPG_SIGNAL_PIN);
    Serial.println(sample);
  }
}
