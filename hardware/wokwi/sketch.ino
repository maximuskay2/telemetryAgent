// Fridge production node (N-R2): the same firmware runs on a real ESP32.
//
// Reads a real door button + current potentiometer, models fridge temperature
// with the same constants as core/simulate/fridge_stream.py (Wokwi's DHT22
// can't be cooled, so it is reported as ambient_c for display only; on real
// hardware in a real fridge, temperature_c comes straight from the sensor).
//
// Production protocol (same as hardware/sim_device.py):
// - POST {API}/api/devices/{id}/readings with the device key, every 2 s;
// - GET  {API}/api/devices/{id}/commands with the device key, every 5 s;
// - drive COMPRESSOR / DEFROST / BACKUP outputs, then ack each command.
//
// In Wokwi the outputs are LEDs; on real hardware the same GPIO pins drive
// relay modules (active HIGH). The compressor never restarts before the
// commanded min_off_s, and power_cycle during defrost is refused.
//
// Wokwi libraries (Libraries tab, + button): "DHT sensor library" by Adafruit,
// "ArduinoJson" by Benoit Blanchon.

#include <WiFi.h>
#include <HTTPClient.h>
#include <DHT.h>
#include <ArduinoJson.h>

// Public demo API base. For localhost, point at your machine's LAN IP instead
// (Wokwi cloud can't reach localhost; or use Wokwi for VS Code + gateway).
#define API_BASE "https://api-production-0c9a.up.railway.app"
#define WIFI_SSID "Wokwi-GUEST"
#define WIFI_PASS ""

// From the /connect panel: device id + its key (shown once on create).
#define DEVICE_ID "wokwi-esp32-01"
#define DEVICE_KEY "PASTE_DEVICE_KEY_HERE"

#define DHT_PIN 4
#define DHT_TYPE DHT22
#define DOOR_PIN 15   // pushbutton to GND, INPUT_PULLUP: pressed = door open
#define CURRENT_PIN 34 // potentiometer wiper: 0..4095 -> 0..5 A

#define COMPRESSOR_PIN 13 // green LED in Wokwi, compressor relay on hardware
#define DEFROST_PIN 12    // blue LED in Wokwi, defrost relay on hardware
#define BACKUP_PIN 14     // yellow LED in Wokwi, backup relay on hardware

#define BASE_TEMP_C 3.5   // shared with fridge_stream.py
#define DOOR_INGRESS_C 0.7 // ~= 2 ticks of 0.35 per 2 s post
#define DRIFT 0.3
#define DEFROST_MS 600000UL // 10 min, shared with sim_device.py
#define POLL_MS 5000

DHT dht(DHT_PIN, DHT_TYPE);
float fridgeTempC = BASE_TEMP_C;
float setpointC = BASE_TEMP_C;
bool compressorOn = true;
unsigned long compressorOffSince = 0;
unsigned long pendingRestartAt = 0;
unsigned long defrostUntil = 0;
unsigned long lastPoll = 0;

String deviceUrl(const String& path) {
  return String(API_BASE) + "/api/devices/" + DEVICE_ID + path;
}

void addAuth(HTTPClient& http) {
  http.addHeader("Authorization", String("Bearer ") + DEVICE_KEY);
}

float readCurrentA() {
  return analogRead(CURRENT_PIN) / 4095.0 * 5.0;
}

bool readDoorOpen() {
  return digitalRead(DOOR_PIN) == LOW;
}

void setCompressor(bool on) {
  compressorOn = on;
  digitalWrite(COMPRESSOR_PIN, on ? HIGH : LOW);
  if (!on) {
    compressorOffSince = millis();
  }
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
  http.begin(deviceUrl("/readings"));
  addAuth(http);
  http.addHeader("Content-Type", "application/json");
  String body = "{\"appliance_type\":\"fridge\","
    "\"temperature_c\":" + String(fridgeTempC, 2) + ","
    "\"current_a\":" + String(currentA, 3) + ","
    "\"vibration_g\":0.02,"
    "\"door_open\":" + String(doorOpen ? "true" : "false") + ","
    "\"ambient_c\":" + String(ambientC, 1) + "}";
  int code = http.POST(body);
  Serial.printf("POST readings -> %d\n", code);
  http.end();
}

void ackCommand(const String& id, bool ok, const String& detail) {
  HTTPClient http;
  http.begin(deviceUrl("/commands/" + id + "/ack"));
  addAuth(http);
  http.addHeader("Content-Type", "application/json");
  String body = "{\"ok\":" + String(ok ? "true" : "false") +
    ",\"detail\":\"" + detail + "\"}";
  int code = http.POST(body);
  Serial.printf("ACK %s ok=%d -> %d\n", id.c_str(), ok, code);
  http.end();
}

// Returns ok/detail through the out params (Arduino has no tuples).
void executeCommand(const String& action, JsonObject params, bool& ok, String& detail) {
  unsigned long now = millis();
  if (action == "defrost") {
    setCompressor(false);
    defrostUntil = now + DEFROST_MS;
    pendingRestartAt = defrostUntil;
    digitalWrite(DEFROST_PIN, HIGH);
    ok = true;
    detail = "defrost started";
  } else if (action == "setpoint") {
    setpointC = params["target_c"] | setpointC;
    ok = true;
    detail = "setpoint now " + String(setpointC, 1) + " C";
  } else if (action == "power_cycle") {
    if (now < defrostUntil) {
      ok = false;
      detail = "defrost active - power-cycle refused";
    } else {
      float minOffS = params["min_off_s"] | 0;
      setCompressor(false);
      pendingRestartAt = compressorOffSince + (unsigned long)(minOffS * 1000);
      ok = true;
      detail = "compressor off; restart scheduled";
    }
  } else if (action == "backup_on") {
    digitalWrite(BACKUP_PIN, HIGH);
    ok = true;
    detail = "backup unit on";
  } else {
    ok = false;
    detail = "unknown action " + action;
  }
}

void pollCommands() {
  HTTPClient http;
  http.begin(deviceUrl("/commands"));
  addAuth(http);
  int code = http.GET();
  if (code != 200) {
    Serial.printf("GET commands -> %d\n", code);
    http.end();
    return;
  }
  String payload = http.getString();
  http.end();
  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, payload);
  if (err) {
    Serial.printf("commands JSON error: %s\n", err.c_str());
    return;
  }
  JsonArray commands = doc["commands"];
  for (JsonObject cmd : commands) {
    String id = cmd["id"] | "";
    String action = cmd["action"] | "";
    if (id.isEmpty() || action.isEmpty()) {
      continue;
    }
    JsonObject params = cmd["params"];
    bool ok = false;
    String detail;
    executeCommand(action, params, ok, detail);
    ackCommand(id, ok, detail);
  }
}

void tickRelays() {
  unsigned long now = millis();
  if (digitalRead(DEFROST_PIN) == HIGH && now >= defrostUntil) {
    digitalWrite(DEFROST_PIN, LOW);
  }
  if (!compressorOn && pendingRestartAt != 0 && now >= pendingRestartAt && now >= defrostUntil) {
    pendingRestartAt = 0;
    setCompressor(true);
    Serial.println("compressor restarted");
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(DOOR_PIN, INPUT_PULLUP);
  pinMode(COMPRESSOR_PIN, OUTPUT);
  pinMode(DEFROST_PIN, OUTPUT);
  pinMode(BACKUP_PIN, OUTPUT);
  setCompressor(true);
  digitalWrite(DEFROST_PIN, LOW);
  digitalWrite(BACKUP_PIN, LOW);
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
  if (millis() - lastPoll >= POLL_MS) {
    lastPoll = millis();
    pollCommands();
  }
  tickRelays();
  delay(2000);
}
