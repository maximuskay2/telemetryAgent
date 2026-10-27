# TelemetryAgent Demo Script (3 minutes)

Target: the Day 8 video. Both incidents side by side; the software one ends in
a real PR on GitHub, the appliance one in an alert and work order. Say
"verified fix" and "abnormal behavior detected early" — never "zero
hallucination" or "predicts failure".

## Pre-flight (before recording)

- From a clean clone with `.env` (`MODEL_API_KEY`, `BASETEN_API_KEY`,
  `MODAL_TOKEN_ID/SECRET`, `GITHUB_TOKEN`): run `./scripts/demo.sh`
  (or `npm run demo` from `apps/web`), open http://localhost:3000.
- Demo-target repo clean; previous `telemetry-agent/fix-*` branches deleted so
  the new PR is obviously the agent's.
- Warm the Modal Sandbox once (cold-start can take tens of seconds); note the
  measured cold-start here: ____s. If the sandbox is slow on take day, narrate
  over the verify step instead of waiting in silence.
- Pre-capture backup footage of a known-good run (Day 7); the edit can cut to
  it if the live take stalls.

## Shots (one command + one click)

### 0:00–0:25 — The problem (dashboard: scenario bar, service map, fridge)

- "Outages take hours to diagnose and fix. TelemetryAgent does it in minutes —
  for software and for physical equipment, with the same reasoning core."
- Point at the world: the service map, the virtual fridge, the two incident
  lanes. Click **Play scenario** — everything after this is autonomous.

### 0:25–1:35 — Software incident (service map + left lane + GitHub)

1. Shop load starts; orders visibly fail on the map and the red deadlock
   cycle appears between the two lock nodes.
2. The log watcher grabs the crash lines — no clicks — and the lane advances:
   - Diagnosis by **Muse Spark** (`muse-spark-1.3`, Meta Model API).
   - Patch + pytest by the open-weight **Muse Spark Open** on **Baseten**
     (note the model/provider tag on the step).
   - Verification: the test fails on the original, passes on the patch —
     run by pytest in a **Modal Sandbox**, never locally.
3. If a retry happens, call it out: "failure output feeds back in; the final
   attempt escalates to **Muse Wonder**."
4. Switch to GitHub: the real PR, with diagnosis, test output, and attempt
   count in the body. "A verified fix, ready to review."
5. Click **Deploy verified fix**: the shop hot-swaps to the patched module
   and the map dots turn green. "Merge and deploy — the outage is over."

### 1:35–2:25 — Appliance incident (fridge + right lane)

1. The scenario opens the fridge door: the door swings, the temperature curve
   climbs past the warn line, and the sensor watcher triggers — "Detected by
   watcher", no other clicks.
2. Same core: Muse Spark classifies the sensor window, Muse Spark Open writes
   the runbook, deterministic safety rules validate it — "no simulator, just
   hard bounds: holding temperature, restart delay, power-off window."
3. Final action: owner SMS alert + technician work order shown in the panel.
   "Abnormal behavior detected early, before stock spoils."
4. Click **Technician applies runbook**: the door closes and the temperature
   curve falls back to ~3.5 °C.

### 2:25–3:00 — Close (architecture diagram or README)

- One diagram: telemetry → Muse Spark → Muse Spark Open → verify → act.
- Callouts: Muse Spark, Muse Spark Open, Muse Wonder, Modal, built with
  **Muse Code**. End on the repo + demo URL.

## Manual variant (button-first take)

Same beats without the scenario player: use the shop page + load generator
for the software incident (`venv/bin/python demo/shop/load.py --shoppers 8
--rate 30 --duration 60`), the fridge **fault buttons** for the appliance
incident, and the per-panel **Inject** buttons to replay either incident as a
manual upload. The lanes, badges, and timers behave identically; only the
"Detected by" source tag differs.

## Backup plan

- If any live step stalls >30s, cut to the pre-captured footage (same panels,
  same steps) and keep the narration identical.
- If Baseten is down, the failover chain (Fireworks → Muse Spark) keeps the
  demo alive; the model tag on the generate step tells the story — point at it.
