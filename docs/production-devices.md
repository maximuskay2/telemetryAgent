# Production devices + app (John)

How real fridges/freezers and the phone app join TelemetryAgent. Backend
companion: `docs/connections.md` / `docs/proof-run.md` (James).

## Device protocol (frozen shapes)

Base: the API URL from `/connect` (local dev: `http://localhost:8201`).
Auth: `Authorization: Bearer <device key>` — the key shown once when the
device connection is created. Unknown keys get 401.

### POST /api/devices/{id}/readings

One reading. `{id}` is the device id (must match the firmware `DEVICE_ID`).

```json
{
  "appliance_type": "fridge",
  "temperature_c": 3.5,
  "current_a": 1.2,
  "vibration_g": 0.02,
  "door_open": false,
  "ambient_c": 24.0
}
```

`ambient_c` is optional, display only, never evaluated. The response is the
ingest verdict plus the device echo:

```json
{ "accepted": true, "triggered": null, "gate": null,
  "device_id": "fridge-01", "system_id": "coldstore-b" }
```

The first reading flips the device connection `waiting → ok` and emits a
`connection_status` event (the /connect "✓ first reading"). Normal readings
post every 2 s; the hardware lane triggers on the same watcher rules as the
virtual fridge.

### GET /api/devices/{id}/commands

Poll every 5 s. Returns the pending queue (2-minute expiry; empty while the
global pause is on):

```json
{ "commands": [
  { "id": "cmd_1", "action": "defrost", "params": {},
    "expires_at": 1730200120.0 }
] }
```

Actions: `defrost` (no params), `setpoint` (`{target_c}`),
`power_cycle` (`{min_off_s}`), `backup_on` (no params).

### POST /api/devices/{id}/commands/{cmd}/ack

```json
{ "ok": true, "detail": "relay on" }
```

→ `{ "status": "done" }` (`failed` when `ok` is false). Unknown commands
404. Acks after the 2-minute expiry keep `expired`.

### Device-side safety (last line of defence)

The server validates every option first, but the device enforces physics:

- the compressor never restarts before the commanded `min_off_s` — restarts
  are scheduled, never rushed;
- `power_cycle` during an active defrost is refused (`ok: false`);
- unknown actions are refused (`ok: false`);
- already-acked command ids are never executed twice (poll/ack races).

## Simulator (no hardware)

`hardware/sim_device.py` is a stdlib-only software ESP32 with the same
protocol and the same safety rules:

```bash
python3 hardware/sim_device.py --api http://localhost:8201 \
  --device sim-fridge-01 --key <device-key> --fault door_open
```

`--fault door_open` climbs past the hardware lane; without it the node idles
at 3.5 °C. `--max-readings N` bounds a run for tests.

## Firmware (Wokwi + real ESP32)

`hardware/wokwi/` holds the sketch, diagram, and README. In Wokwi:

1. New Project → ESP32 → Arduino; paste `sketch.ino` + `diagram.json`.
2. Libraries: "DHT sensor library" (Adafruit) + "ArduinoJson".
3. Paste `DEVICE_ID` / `DEVICE_KEY` from the /connect device step.
4. Press ▶ — readings every 2 s, command poll every 5 s.

Outputs (active HIGH): GPIO 13 compressor, 12 defrost, 14 backup — LEDs in
Wokwi, relay modules on real hardware. On a real unit inside a real fridge,
`temperature_c` comes from the sensor (one line); everything else is
unchanged. The sketch compiles in Wokwi (human check).

## Phone app

- **Hardware · Choose a fix** — remote commands, the runbook as an on-site
  checklist, technician dispatch with the work order. Unsafe options render
  disabled with their reason and can never be tapped; live status follows
  `option_status` events.
- **Software · PR ready** — summary, "fails → passes, suite green" proof,
  Open PR, and the mitigation countdown (Roll back now / Cancel).
- **Watching** — the quiet channel when nothing needs you.
- **Pause all actions** — the kill switch with a Paused banner; paused →
  nothing runs, including tapped options (409), until resumed.

Pairing: /connect step 8 shows the same QR as Mission Control
(`{"api": "<api-url>"}`); the phone token comes from the pairing flow only
and is never baked into the app.

## Proof run

Devices/app half of the proof run (James owns `docs/proof-run.md`).

### Software half (needs a repo + Railway, ~15 min, human)

1. On main with a clean `check.sh`, run the API on 8201 and web on 3201.
2. /connect → create a software system → logs → paste the forwarder
   one-liner on the target box (or the curl) → "✓ first log".
3. Repo + Test (permissions read ✓ / pull_requests ✓), hosting + Test ping.
4. Teach normal (contact + limits), Confirm + Arm, promise tick, pair phone.
5. Break the target (divide by zero), watch: PR opens, phone card shows
   "fails → passes, suite green", tap Open PR, Cancel stops the rollback.
6. Pause toggle → banner on web + phone within 2 s; resume.

### Appliance half, simulated (~5 min, automated + human taps)

1. API on 8201. /connect → appliance system → device step → note the key.
2. Run the sim: `sim_device.py --api … --device sim-fridge-01 --key …`.
   "✓ first reading" lands on the device step.
3. `--fault door_open`: the hardware lane triggers; the run offers
   Start defrost · Lower setpoint 1 °C · Power-cycle compressor
   (refused before the delay) · Switch to backup + checklist + dispatch.
4. Tap **Start defrost** on the phone → sim acks within 10 s → Done ✓.
   (Automated: `tests/test_devices_e2e.py` does this against 8201.)
5. Tap **Power-cycle compressor** before the delay → refused with the wait;
   after the delay → scheduled restart, never rushed.

### Appliance half, Wokwi (~10 min, human)

1. Paste the sketch + diagram, add both libraries, set `DEVICE_ID/KEY`.
2. Press ▶: readings land, "✓ first reading" on the device step.
3. Hold DOOR: temperature climbs, the hardware lane triggers.
4. Tap a remote option on the phone: the LED answers within 10 s.
