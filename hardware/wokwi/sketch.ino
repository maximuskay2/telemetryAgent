// Fridge door-monitor node (Sim 7): the same firmware runs on a real ESP32.
//
// Reads a real door button + current potentiometer, models fridge temperature
// with the same constants as core/simulate/fridge_stream.py (Wokwi's DHT22
// can't be cooled, so it is reported as ambient_c for display only; on real
// hardware in a real fridge, temperature_c comes straight from the sensor).
// Posts every 2 s to POST /api/telemetry/appliance.
//
// Wokwi libraries (Libraries tab, + button): "DHT sensor library" by Adafruit.

#include <WiFi.h>
#include <HTTPClient.h>
#include <DHT.h>

// Public demo API. For localhost, point at your machine's LAN IP instead
// (Wokwi cloud can't reach localhost; or use Wokwi for VS Code + gateway).
#define API_URL "https://api-production-0c9a.up.railway.app/api/telemetry/appliance"
#define WIFI_SSID "Wokwi-GUEST"
#define WIFI_PASS ""

#define SOURCE_ID "wokwi-esp32-01"
#define DHT_PIN 4
#define DHT_TYPE DHT22
#define DOOR_PIN 15   // pushbutton to GND, INPUT_PULLUP: pressed = door open
#define CURRENT_PIN 34 // potentiometer wiper: 0..4095 -> 0..5 A

#define BASE_TEMP_C 3.5   // shared with fridge_stream.py
#define DOOR_INGRESS_C 0.7 // ~= 2 ticks of 0.35 per 2 s post
#define DRIFT 0.3

DHT dht(DHT_PIN, DHT_TYPE);
float fridgeTempC = BASE_TEMP_C;

float readCurrentA() {
  return analogRead(CURRENT_PIN) / 4095.0 * 5.0;
}

bool readDoorOpen() {
  return digitalRead(DOOR_PIN) == LOW;
}

void stepThermalModel(bool doorOpen) {
  if (doorOpen) {
    fridgeTempC += DOOR_INGRESS_C;
  } else {
    fridgeTempC += (BASE_TEMP_C - fridgeTempC) * DRIFT;
  }
}

void postReading(bool doorOpen, float currentA, float ambientC) {
  HTTPClient http;
  http.begin(API_URL);
  http.addHeader("Content-Type", "application/json");
  String body = "{\"source_id\":\"" SOURCE_ID "\","
    "\"appliance_type\":\"fridge\","
    "\"temperature_c\":" + String(fridgeTempC, 2) + ","
    "\"current_a\":" + String(currentA, 3) + ","
    "\"vibration_g\":0.02,"
    "\"door_open\":" + String(doorOpen ? "true" : "false") + ","
    "\"ambient_c\":" + String(ambientC, 1) + "}";
  int code = http.POST(body);
  Serial.printf("POST %s -> %d\n", body.c_str(), code);
  http.end();
}

void setup() {
  Serial.begin(115200);
  pinMode(DOOR_PIN, INPUT_PULLUP);
  dht.begin();
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(250);
    Serial.print(".");
  }
  Serial.println(" connected");
}

void loop() {
  bool doorOpen = readDoorOpen();
  float currentA = readCurrentA();
  float ambientC = dht.readTemperature();
  if (isnan(ambientC)) ambientC = 24.0;
  stepThermalModel(doorOpen);
  postReading(doorOpen, currentA, ambientC);
  delay(2000);
}
