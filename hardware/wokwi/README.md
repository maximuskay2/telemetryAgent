# Wokwi ESP32 production node (N-R2)

A virtual ESP32 cold-chain node: it posts sensor readings with its device key,
polls the command queue, drives compressor/defrost/backup outputs, and acks.
Video line: "the same firmware runs on a real ESP32."

## Run it (5 minutes)

1. Open <https://wokwi.com> → New Project → ESP32 → Arduino.
2. Replace `sketch.ino` and `diagram.json` with the files in this directory.
3. Libraries tab → **+** → add **"DHT sensor library"** by Adafruit
   (accept the Adafruit Unified Sensor dependency) and **"ArduinoJson"**
   by Benoit Blanchon.
4. Connect a device in the `/connect` wizard (step 5) and paste the device id
   and key into `DEVICE_ID` / `DEVICE_KEY` at the top of the sketch.
5. Press ▶. The serial monitor shows `POST readings -> 200` every 2 s.
6. On the dashboard, `wokwi-esp32-01` readings land on the fridge chart.
7. **Hold the red DOOR button**: the modeled temperature climbs past 5 °C and
   the hardware lane triggers — the 15-second clip.
8. Tap a remote option on the phone (e.g. **Start defrost**): the blue DEFROST
   LED lights within 10 s and the serial monitor shows the ack.

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

`API_BASE` at the top of `sketch.ino` defaults to the public Railway API. For a
local API, use your machine's LAN IP (Wokwi cloud cannot reach `localhost`),
or run Wokwi for VS Code with the private gateway.

## Outputs

| Wokwi | GPIO | Real hardware |
| :--- | :--- | :--- |
| COMP (green LED) | 13 | Compressor relay, active HIGH |
| DEFROST (blue LED) | 12 | Defrost relay, active HIGH |
| BACKUP (yellow LED) | 14 | Backup-unit relay, active HIGH |

Device-side safety (mirrors `sim_device.py`): the compressor never restarts
before the commanded `min_off_s`, and `power_cycle` during an active defrost
is refused with `ok: false`.
