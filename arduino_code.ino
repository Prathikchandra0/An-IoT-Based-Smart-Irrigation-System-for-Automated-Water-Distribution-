/*
 * arduino_code.ino
 * ─────────────────────────────────────────────────────────────────
 * Smart Irrigation System – NodeMCU (ESP8266) Firmware
 *
 * Hardware connections
 * ────────────────────
 *  Soil Moisture Sensor  → NodeMCU A0  (analog input)
 *  DHT11 Data            → NodeMCU D4  (GPIO 2)
 *  Relay (pump) IN       → NodeMCU D1  (GPIO 5) – active-low relay
 *  VCC / GND             → 3.3V & GND rails
 *
 * Required Libraries (install via Arduino Library Manager)
 * ────────────────────────────────────────────────────────
 *  • DHT sensor library  by Adafruit
 *  • Adafruit Unified Sensor
 *  • ArduinoJson         v6.x
 *  • ESP8266WiFi         (bundled with ESP8266 board package)
 *  • ESP8266HTTPClient   (bundled with ESP8266 board package)
 */

#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <ArduinoJson.h>
#include <DHT.h>

// ─────────────────────────────────────────────
// CONFIGURATION  ← edit before flashing
// ─────────────────────────────────────────────
const char* WIFI_SSID      = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD  = "YOUR_WIFI_PASSWORD";
const char* SERVER_URL     = "http://192.168.1.100:5000/sensor-data"; // Flask server IP

// Pin definitions
#define SOIL_MOISTURE_PIN  A0    // Analog pin – soil moisture sensor output
#define DHT_PIN            D4    // DHT11 data pin (GPIO 2)
#define RELAY_PIN          D1    // Relay IN pin  (GPIO 5)

// Sensor type – change to DHT22 if using that variant
#define DHT_TYPE           DHT11

// Timing (milliseconds)
#define READ_INTERVAL_MS   10000   // send data to server every 10 seconds

// ─────────────────────────────────────────────
// GLOBALS
// ─────────────────────────────────────────────
DHT dht(DHT_PIN, DHT_TYPE);
WiFiClient wifiClient;
unsigned long lastReadTime = 0;

// ─────────────────────────────────────────────
// SETUP
// ─────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  Serial.println("\n[BOOT] Smart Irrigation System – NodeMCU");

  // Configure relay pin as output; relay starts OFF (high = relay off for active-low)
  pinMode(RELAY_PIN, OUTPUT);
  digitalWrite(RELAY_PIN, HIGH);   // HIGH → relay de-energised → pump OFF

  // Start DHT sensor
  dht.begin();
  Serial.println("[SENSOR] DHT11 initialised.");

  // Connect to Wi-Fi
  connectWiFi();
}

// ─────────────────────────────────────────────
// LOOP
// ─────────────────────────────────────────────
void loop() {
  // Reconnect if Wi-Fi dropped
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[WIFI] Connection lost – reconnecting…");
    connectWiFi();
  }

  // Throttle readings to READ_INTERVAL_MS
  unsigned long now = millis();
  if (now - lastReadTime >= READ_INTERVAL_MS || lastReadTime == 0) {
    lastReadTime = now;

    // 1. Read sensor values
    int   soilRaw   = readSoilMoisture();
    float temp      = readTemperature();
    float humidity  = readHumidity();

    // Skip if DHT11 read failed
    if (isnan(temp) || isnan(humidity)) {
      Serial.println("[SENSOR] DHT11 read failed – skipping this cycle.");
      return;
    }

    // 2. Print readings to Serial Monitor
    Serial.printf("[DATA]  Soil(raw)=%d  Temp=%.1f°C  Humidity=%.1f%%\n",
                  soilRaw, temp, humidity);

    // 3. Send to Flask backend and get pump command
    String pumpCommand = sendDataToServer(soilRaw, temp, humidity);

    // 4. Actuate relay based on command
    if (pumpCommand == "ON") {
      controlPump(true);
    } else {
      controlPump(false);
    }
  }
}

// ─────────────────────────────────────────────
// Wi-Fi HELPER
// ─────────────────────────────────────────────
void connectWiFi() {
  Serial.printf("[WIFI] Connecting to %s", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\n[WIFI] Connected! IP: %s\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println("\n[WIFI] Failed to connect. Will retry next loop.");
  }
}

// ─────────────────────────────────────────────
// SENSOR READERS
// ─────────────────────────────────────────────
/**
 * Read raw ADC value from the soil moisture sensor (0–1023).
 * Higher value = drier soil (less capacitance / more resistance).
 */
int readSoilMoisture() {
  int raw = analogRead(SOIL_MOISTURE_PIN);
  Serial.printf("[SENSOR] Soil moisture raw ADC: %d\n", raw);
  return raw;
}

/**
 * Read temperature from DHT11 in degrees Celsius.
 * Returns NAN on failure – always check before use.
 */
float readTemperature() {
  float t = dht.readTemperature();   // Celsius
  if (isnan(t)) {
    Serial.println("[SENSOR] Error reading temperature from DHT11.");
  }
  return t;
}

/**
 * Read relative humidity (%) from DHT11.
 * Returns NAN on failure.
 */
float readHumidity() {
  float h = dht.readHumidity();
  if (isnan(h)) {
    Serial.println("[SENSOR] Error reading humidity from DHT11.");
  }
  return h;
}

// ─────────────────────────────────────────────
// HTTP: POST sensor data → receive pump command
// ─────────────────────────────────────────────
/**
 * Build a JSON payload, POST it to SERVER_URL, parse the response,
 * and return "ON" or "OFF" as the pump command string.
 *
 * Payload format:
 *   { "soil_moisture_raw": 650, "temperature": 28.5, "humidity": 65.0 }
 *
 * Expected response:
 *   { "pump_command": "ON", "reason": "...", "moisture_pct": 35.2 }
 */
String sendDataToServer(int soilRaw, float temp, float humidity) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[HTTP] No Wi-Fi – skipping POST.");
    return "OFF";   // safe default: leave pump off
  }

  HTTPClient http;
  http.begin(wifiClient, SERVER_URL);
  http.addHeader("Content-Type", "application/json");

  // Serialise JSON payload
  StaticJsonDocument<128> payload;
  payload["soil_moisture_raw"] = soilRaw;
  payload["temperature"]       = temp;
  payload["humidity"]          = humidity;

  String jsonBody;
  serializeJson(payload, jsonBody);
  Serial.printf("[HTTP] Sending: %s\n", jsonBody.c_str());

  int httpCode = http.POST(jsonBody);
  String pumpCommand = "OFF";   // default to safe state

  if (httpCode == 200) {
    String responseBody = http.getString();
    Serial.printf("[HTTP] Response (%d): %s\n", httpCode, responseBody.c_str());

    // Parse JSON response
    StaticJsonDocument<256> response;
    DeserializationError err = deserializeJson(response, responseBody);
    if (!err) {
      pumpCommand = response["pump_command"].as<String>();
      float moistPct = response["moisture_pct"].as<float>();
      String reason  = response["reason"].as<String>();

      Serial.printf("[DECISION] Pump=%s | Moisture=%.1f%% | Reason: %s\n",
                    pumpCommand.c_str(), moistPct, reason.c_str());
    } else {
      Serial.printf("[HTTP] JSON parse error: %s\n", err.c_str());
    }
  } else {
    Serial.printf("[HTTP] POST failed, HTTP code: %d\n", httpCode);
  }

  http.end();
  return pumpCommand;
}

// ─────────────────────────────────────────────
// ACTUATOR: Relay / Water Pump
// ─────────────────────────────────────────────
/**
 * Control the relay module.
 *
 * Most relay modules are ACTIVE-LOW:
 *   digitalWrite(RELAY_PIN, LOW)  → relay energised → pump ON
 *   digitalWrite(RELAY_PIN, HIGH) → relay de-energised → pump OFF
 *
 * Swap LOW/HIGH if your relay is active-high.
 */
void controlPump(bool pumpOn) {
  if (pumpOn) {
    digitalWrite(RELAY_PIN, LOW);    // energise relay → pump ON
    Serial.println("[PUMP] Water pump turned ON.");
  } else {
    digitalWrite(RELAY_PIN, HIGH);   // de-energise relay → pump OFF
    Serial.println("[PUMP] Water pump turned OFF.");
  }
}
