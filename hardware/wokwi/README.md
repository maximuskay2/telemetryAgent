# Wokwi ESP32 bonus (Sim 7)

A virtual ESP32 door-monitor node that posts real sensor readings to the same
`sensor_watcher` rules engine as the virtual fridge. Video line: "the same
firmware runs on a real ESP32."

## Run it (2 minutes)

1. Open <https://wokwi.com> → New Project → ESP32 → Arduino.
2. Replace `sketch.ino` and `diagram.json` with the files in this directory.
3. Libraries tab → **+** → add **"DHT sensor library"** by Adafruit
   (accept the Adafruit Unified Sensor dependency).
4. Press ▶. The serial monitor shows `POST {...} -> 200` every 2 s.
5. On the dashboard, `wokwi-esp32-01` readings land on the fridge chart.
6. **Hold the red DOOR button**: the modeled temperature climbs past 5 °C and
   the hardware lane triggers — the 15-second clip.

## What is real vs modeled

| Signal | Source |
| :--- | :--- |
| `door_open` | Real: the pushbutton |
| `current_a` | Real: the potentiometer (0–5 A) |
| `temperature_c` | Modeled with the same constants as `fridge_stream.py` (Wokwi's DHT22 can't be cooled) |
| `ambient_c` | Real DHT22 room reading, display only, never evaluated |

On real hardware inside a real fridge, `temperature_c` comes straight from the
sensor (one line in `loop()`); everything else is unchanged.

## API target

`API_URL` at the top of `sketch.ino` defaults to the public Railway API. For a
local API, use your machine's LAN IP (Wokwi cloud cannot reach `localhost`),
or run Wokwi for VS Code with the private gateway.
