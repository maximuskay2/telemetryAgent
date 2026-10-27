# TelemetryAgent Demo Script (3 minutes)

Target: the Day 8 video. Both incidents side by side; the software one ends in
a real PR on GitHub, the appliance one in an alert and work order. Say
"verified fix" and "abnormal behavior detected early" — never "zero
hallucination" or "predicts failure".

## Pre-flight (before recording)

- API + dashboard running on the public demo URL; `.env` has `MODEL_API_KEY`,
  `BASETEN_API_KEY`, `MODAL_TOKEN_ID/SECRET`, `GITHUB_TOKEN`.
- Demo-target repo clean; previous `telemetry-agent/fix-*` branches deleted so
  the new PR is obviously the agent's.
- Warm the Modal Sandbox once (cold-start can take tens of seconds); note the
  measured cold-start here: ____s. If the sandbox is slow on take day, narrate
  over the verify step instead of waiting in silence.
- Pre-capture backup footage of a known-good run (Day 7); the edit can cut to
  it if the live take stalls.

## Shots

### 0:00–0:25 — The problem (dashboard, both panels idle)

- "Outages take hours to diagnose and fix. TelemetryAgent does it in minutes —
  for software and for physical equipment, with the same reasoning core."
- Point at the two panels: crash-log incident, fridge incident.

### 0:25–1:35 — Software incident (left panel + GitHub)

1. Click **Inject deadlock**. Narrate each streamed step as it lands:
   - Diagnosis by **Muse Spark** (`muse-spark-1.3`, Meta Model API).
   - Patch + pytest by the open-weight **Muse Spark Open** on **Baseten**
     (note the model/provider tag on the step).
   - Verification: the test fails on the original, passes on the patch —
     run by pytest in a **Modal Sandbox**, never locally.
2. If a retry happens, call it out: "failure output feeds back in; the final
   attempt escalates to **Muse Wonder**."
3. Switch to GitHub: the real PR, with diagnosis, test output, and attempt
   count in the body. "A verified fix, ready to review."

### 1:35–2:25 — Appliance incident (right panel)

1. Select fridge + door-open fault, click **Inject fault**.
2. Same core: Muse Spark classifies the sensor window, Muse Spark Open writes
   the runbook, deterministic safety rules validate it — "no simulator, just
   hard bounds: holding temperature, restart delay, power-off window."
3. Final action: owner SMS alert + technician work order shown in the panel.
   "Abnormal behavior detected early, before stock spoils."

### 2:25–3:00 — Close (architecture diagram or README)

- One diagram: telemetry → Muse Spark → Muse Spark Open → verify → act.
- Callouts: Muse Spark, Muse Spark Open, Muse Wonder, Modal, built with
  **Muse Code**. End on the repo + demo URL.

## Autonomous variant (watcher-first take)

Same 3-minute structure, but nobody clicks. From the repo root:

```bash
./demo/live.sh        # API + log watcher + load service
npm run dev           # dashboard in a second terminal
```

1. The load service writes retries, then a deadlock, to
   `demo/target-service/logs/service.log`.
2. The watcher catches the early `WARNING retry` lines and POSTs the context
   window with `target_path=inventory.py`, so verification is fail-to-pass
   against the real file.
3. The dashboard adopts the run live: "Detected by watcher" badge, per-stage
   model tags, and the warning → verified-fix timer.
4. The software incident ends in a real PR whose diff touches `inventory.py`.

For the edit, this take can replace the 0:25–1:35 click-through, or open the
video as the hook ("no one clicked anything") before the narrated replay.

## Backup plan

- If any live step stalls >30s, cut to the pre-captured footage (same panels,
  same steps) and keep the narration identical.
- If Baseten is down, the failover chain (Fireworks → Muse Spark) keeps the
  demo alive; the model tag on the generate step tells the story — point at it.
