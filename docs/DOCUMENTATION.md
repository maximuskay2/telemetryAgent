# TelemetryAgent — Technical Documentation

How TelemetryAgent works, how to run it, and how its pieces fit together. For *what* we're building and *why*, see the [PRD](PRD.md).

**Contents**
1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [Quick start](#3-quick-start)
4. [Configuration](#4-configuration)
5. [Components](#5-components)
6. [Setup profiles and the gate](#6-setup-profiles-and-the-gate)
7. [Veto window (auto-action)](#7-veto-window-auto-action)
8. [Simulators](#8-simulators)
9. [Web dashboard](#9-web-dashboard)
10. [Mobile app](#10-mobile-app)
11. [API reference](#11-api-reference)
12. [WebSocket events](#12-websocket-events)
13. [Testing](#13-testing)
14. [Deployment](#14-deployment)
15. [Troubleshooting](#15-troubleshooting)
16. [Repository layout](#16-repository-layout)

---

## 1. Overview

TelemetryAgent runs one loop for two kinds of system:

```
CRASH            →  GRAB               →  SUGGEST           →  VERIFY                 →  FIX
shop fails          log watcher           Muse Spark           pytest in sandbox         PR + hot-swap
fridge drifts       sensor watcher        diagnosis            (fail → pass)             alert + work order
                    + the gate            Muse Spark Open      safety rules              + runbook applied
                                          writes the fix                                 (20 s phone veto)
```

**Meta models used**

| Job | Model | Provider |
| :--- | :--- | :--- |
| Diagnosis, classification, document extraction | `muse-spark-1.3` | Meta Model API |
| Patch + test + runbook generation | `meta-models/muse-spark-open` | Baseten (primary) |
| Generation backup | Muse Spark Open (`FIREWORKS_PATCH_MODEL`) | Fireworks |
| Final-attempt escalation | `muse-wonder-1.0` | Meta Model API |
| Building the project | Muse Code | `muse` CLI |

Generation fails over **Baseten → Fireworks → Meta Model API**; providers without a key are skipped. Each streamed step records which model and provider served it.

---

## 2. Architecture

```
                 ┌───────────── demo/shop (port 8002) ─────────────┐
 customers/load ─►  AutoParts Lagos shop  ── writes ──► shop.log    │
                 └──────────────────┬──────────────────────────────┘
                                    │ tail
                       core/watch/log_watcher (process)
                                    │ POST candidate / run
 ┌──────────────────────────────────▼────────────────────────────────────────┐
 │ apps/api/main.py  — FastAPI (port 8001)                                    │
 │                                                                           │
 │  VirtualFridge stream ─► sensor watcher ─┐                                │
 │                                          ▼                                │
 │                 core/setup/gate.py  (suppress | observe | act)            │
 │                                          ▼ act                            │
 │  core/agent/loop.py:  diagnose ─► generate ─► verify ─► (retry ≤3) ─► act │
 │        core/infer/*          core/infer/*    core/verify/*    core/actions│
 │                                          ▼                                │
 │                 core/actions/auto_action.py  (20 s veto window)           │
 │                                                                           │
 │  EventHub ─► WS /api/ws  (AgentStep + SimEvent)                           │
 └──────────────┬───────────────────────────────────────────┬────────────────┘
                ▼                                           ▼
   apps/web (Next.js, port 3000)                 apps/mobile (Flutter, Android)
   dashboard, /shop, /setup                      alarm, countdown, reports
```

**Key design choices**
- **The API is the hub.** Watchers and simulators publish to it; dashboard and phone only read the WebSocket and call the API.
- **The server owns every decision timer.** The phone displays the countdown; if it's offline, the server still acts at the deadline.
- **Untrusted inputs stay data.** Logs, sensor windows and uploaded documents are passed to models as data, schema-validated, and never allowed to change policy.
- **Generated code only runs in a sandbox** and only counts as verified if its test fails on the real original file and passes on the patch.

---

## 3. Quick start

### Prerequisites
- Python 3.9+ and a virtualenv at `venv/`
- Node.js 20.9+ and npm
- Modal account (`modal setup`) **or** Docker Desktop for local verification
- Flutter 3.x + an Android phone (only for the mobile app)

### Install
```bash
git clone https://github.com/maximuskay2/telemetryAgent.git telemetry-agent
cd telemetry-agent

cp .env.example .env              # fill in keys (see Configuration)

python3 -m venv venv
venv/bin/pip install -r requirements.txt
npm install --prefix apps/web

modal setup                       # once; saves ~/.modal.toml
./scripts/build-sandbox-image.sh  # optional: Docker fallback image
```

### Run everything (one command)
```bash
./scripts/demo.sh
```
This starts the API (`:8001`, with the fridge stream), the shop (`:8002`), the dashboard (`:3000`) and the log watcher. Open http://localhost:3000.

For a phone on the same Wi-Fi: `API_HOST=0.0.0.0 ./scripts/demo.sh`, then scan the "Pair phone" QR on the dashboard.

### Trigger incidents
| What | How |
| :--- | :--- |
| Software deadlock | Dashboard **Start traffic**, or `curl -X POST localhost:8001/api/sim/shop/load -H 'Content-Type: application/json' -d '{"shoppers":8,"rate":20,"duration":60}'` |
| Fridge faults | Fault buttons on the fridge tile (door open, condenser fouling, power surge, rapid restart, defrost stuck) |
| Normal-but-scary | Defrost, Restock, Ambient heat, Deploy shop buttons — these should be **ignored** with a reason once the system is armed |
| Full scripted demo | **Play scenario** (Reset to start over) |
| Manual | Paste a log or "Load sample" in the software panel |

A software run takes ~40–130 s (models + sandbox). After it passes, use **apply fix** (or let the veto window expire) and watch the shop error rate drop to 0%.

### Run pieces individually
```bash
set -a; . ./.env; set +a
venv/bin/python -m uvicorn apps.api.main:app --port 8001 --reload
AGENT_API=http://localhost:8001 venv/bin/python -m uvicorn demo.shop.app:app --port 8002
venv/bin/python -m core.watch.log_watcher --file demo/shop/logs/shop.log --api http://localhost:8001 --target inventory
NEXT_PUBLIC_API_URL=http://localhost:8001 npm run dev --prefix apps/web
venv/bin/python demo/shop/load.py --shoppers 8 --rate 30 --duration 60
```

---

## 4. Configuration

All secrets live in `.env` (git-ignored). Never commit keys or paste them into logs.

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `MODEL_API_KEY` (or `META_MODEL_API_KEY`) | — | Meta Model API (Muse Spark, Muse Wonder) |
| `META_DIAGNOSIS_MODEL` | `muse-spark-1.3` | Diagnosis model |
| `META_ESCALATION_MODEL` | `muse-wonder-1.0` | Final-attempt model |
| `BASETEN_API_KEY` | — | Muse Spark Open on Baseten |
| `BASETEN_PATCH_MODEL` | `meta-models/muse-spark-open` | Generation model id |
| `FIREWORKS_API_KEY`, `FIREWORKS_PATCH_MODEL` | — | Optional backup generation |
| `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET` | — | Only to override `~/.modal.toml`. Set **both or neither** |
| `TA_VERIFY` | — | `local` forces Docker verification |
| `DOCKER_BIN`, `TA_SANDBOX_IMAGE` | auto, `telemetry-agent-sandbox` | Docker fallback runner |
| `GITHUB_TOKEN` | — | Fine-grained token: `contents` + `pull_requests` write on the demo repo only |
| `GITHUB_DEMO_REPO`, `GITHUB_BASE_BRANCH` | `owner/repo`, `main` | Where PRs are opened |
| `AUTO_ACTION_SECONDS` | `20` | Veto window length |
| `AUTO_ACTION_ENABLED` | `true` | Kill switch: `false` = every action needs explicit approval |
| `MOBILE_API_TOKEN` | — | Required on approve/disapprove/apply endpoints when set |
| `SHOP_PORT` | `8002` | Demo shop port |
| `INVENTORY_PATH` | `demo/target-service/inventory.py` | Inventory module the shop loads at start |
| `TA_DATA_DIR` | `data/` | Where profiles and uploads are stored |
| `FRIDGE_STREAM`, `FRIDGE_TICK_S` | `0`, `1.0` | Start the fridge at boot; seconds per tick (1 tick = 1 simulated minute) |
| `CORS_ORIGIN_REGEX` | localhost/LAN `:3000` | Allowed dashboard origins (API and shop) |
| `API_HOST`, `API_PORT`, `WEB_PORT` | `127.0.0.1`, `8001`, `3000` | `scripts/demo.sh` |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8001` (set in `apps/web/.env.local`) | Dashboard → API |
| `NEXT_PUBLIC_SHOP_URL` | `http://localhost:8002` | `/shop` page → shop |

---

## 5. Components

### 5.1 Schemas — `core/schemas/`
| File | Contents |
| :--- | :--- |
| `telemetry.py` | `SoftwareTelemetry`, `SensorReading`, `ApplianceTelemetry` (discriminated by `domain`) |
| `diagnosis.py` | `Diagnosis` (`summary`, `likely_cause`, `suggested_actions`, `confidence`, `is_expected`, `expected_reason`) |
| `remediation.py` | `RunRequest`, `GeneratedPatch`, `Runbook`, `ExecutionResult`, `ApplianceResult` |
| `events.py` | `AgentStep`, `SimEvent`, `LogEvent` |
| `profile.py` | `SystemProfile` and its parts (see §6) |

### 5.2 Inference — `core/infer/`
- `meta_client.py`: `diagnose()`, `generate_patch()`, `generate_runbook()` on the Meta Model API (structured JSON output).
- `baseten_client.py`, `fireworks_client.py`: Muse Spark Open generation.
- `analyzer.py`: async wrappers and the failover chain. `errors.py`: readable provider errors (401, 404 model not found, rate limits).

### 5.3 Agent loop — `core/agent/loop.py`
- `run_diagnostic_loop(log_text, max_attempts, on_event, original_code, open_pr, run_id, …)` — software.
- `run_appliance_loop(telemetry, max_attempts, on_event, send_alert, run_id, …)` — appliance.
- Both: diagnose → (stop with `NO_ACTION` if expected) → generate → verify → retry with feedback (≤3; last on Muse Wonder) → act. Every stage emits an `AgentStep` with model, provider and duration.

### 5.4 Verification — `core/verify/`
| File | Role |
| :--- | :--- |
| `sandbox.py` | `verify_patch` / `verify_fix` in a Modal Sandbox (files written via `exec`); falls back to Docker on import/auth errors |
| `local_runner.py` | Docker runner: `--network none`, 512 MB, 1 CPU, pids limit 64 |
| `targets.py` | Allowlisted target files (e.g. `demo/target-service/inventory.py`) — never arbitrary paths |
| `safety_rules.py` | `validate_runbook()`: holding temperature range, compressor restart delay, power-off window, no disabling protection, plus profile limits/forbidden actions |
| `contracts.py` | Structural checks on generated code/tests |

**Fail-to-pass:** the generated test runs against the original file (must fail) and the patch (must pass). If nothing fails on the original, the run ends as "possibly intended, needs human".

### 5.5 Actions — `core/actions/`
- `github_pr.py`: branch, commit the patched file + regression test, open a PR with diagnosis, test output, attempts.
- `notify.py`: SMS/work-order stub (shown on dashboard and phone).
- `auto_action.py`: veto windows (§7).

### 5.6 Watchers — `core/watch/`
| File | Role |
| :--- | :--- |
| `log_watcher.py` | Tails the shop log; forwards WARNING/ERROR lines (≤5/s); on a hit sends `watcher_trigger` + the context window. Flags: `--debounce-minutes` (10), `--before` (30), `--after` (10), `--quiet-seconds` (60: no new run for this long after a run returns, so one burst = one run) |
| `rules.py` | `match_error` (Deadlock / ERROR / Traceback), `RetryClusterTracker` (≥2 retries on one item within 30 s), `fingerprint_for` |
| `sensor_watcher.py` | Per-reading temperature/current rules with streaks and debounce (defaults overridden by the profile) |
| `watcher.py` | Shared helpers: `LogTail`, `send_run`, `post_log`, `publish_sim_event` |

---

## 6. Setup profiles and the gate

### System Profile (`core/schemas/profile.py`)
| Section | Example |
| :--- | :--- |
| Identity | `system_id`, `name`, `kind` (`software`/`appliance`), `appliance_type` |
| Environment | ambient range, climate class, location, hours |
| `normal_ranges` | `temp_c 2–5`, `error_rate 0–0.01` |
| `expected_behaviours` | defrost every 6 h ≤ 20 min, temp ≤ 7 °C; compressor inrush ≤ 4× for ≤ 3 s; `WARN cache cold` at startup |
| `modes` | `defrost`, `deploying`, `maintenance` with what they relax and a max duration |
| `failure_definitions` | `temp_c > 8 for ≥ 600 s except in defrost`; `error_rate > 0.05 for ≥ 30 s` |
| `hard_limits` | `temp_c > 10`; `error_rate > 0.5` — never suppressible |
| `policy` | allowed/forbidden actions, `auto_fix_allowed`, `countdown_s`, alert contacts — **human-only** |
| `baseline` | learned log templates, per-mode sensor bands, metric bands |
| Every value | `provenance`: source doc, page/region, quote, confidence, confirmed by/at |
| Lifecycle | `draft → confirmed → learning → armed`; each edit bumps `version` |

Stored in `data/profiles/<system_id>.json`. Sample inputs and ready profiles: `demo/setup/` (spec sheet PDF, rating plate photo, ops guide, `profiles/shop.json`, `profiles/coldchain.json`).

### Extraction (`core/setup/extract.py`)
PDF text per page; images/scans through the model's vision input (OCR fallback); the model fills the profile schema and must quote every value. Unknown → empty. Conflicts between documents are flagged, not resolved. Policy and hard limits from documents are ignored.

### The gate (`core/setup/gate.py`)
`evaluate(candidate, profile, mode, baseline, metrics)` runs before any run starts. First decisive check wins:

| # | Check | Outcome |
| :--- | :--- | :--- |
| 1 | Hard limit breached | **act** (always) |
| 2 | System not armed | **observe** ("Setup needed") |
| 3 | Matches an expected behaviour within its limits | **suppress** + citation |
| 4 | Current mode explains it (within max duration) | **suppress** |
| 5 | Known in the baseline | **suppress** |
| 6 | Proof of impact (failure definition met) | **act**; otherwise **observe** and re-check in 30 s |

Each decision is broadcast as `gate_decision` with `reason`, `citation` and the list of checks. Suppressed/observed decisions show as grey/amber rows in the stream and never open an incident or alarm.

Related modules: `modes.py` (mode state, overrun detection), `baseline.py` (learning), `context.py` (profile summary for diagnosis), `sensor_watch.py` (profile-aware sensor evaluation), `store.py` (profile persistence/versioning).

---

## 7. Veto window (auto-action)

`core/actions/auto_action.py`

- A window opens only when a run is **eligible**: software `PASS` with fail-to-pass against the real target; appliance runbook passed safety rules and maps to an automatable action (`close_door`, `clean_condenser`, `reset`, …); gate said `act`; profile allows auto-fix.
- `PendingAction` states: `pending → approved | disapproved | auto_applied` (plus failure states). First decision wins under a lock; a decision after the deadline gets **409**.
- Events: `action_pending` (deadline, summary) → `action_tick` (every second) → `action_resolved` (state, by whom).
- On approve or deadline the server calls the same path as the dashboard's apply buttons (`/api/sim/shop/apply-fix`, `/api/sim/fridge/apply-runbook`).
- `AUTO_ACTION_ENABLED=false` turns every window into "approval required". `MOBILE_API_TOKEN` protects decisions.
- Every window is recorded in the run's decision record (`GET /api/runs/{run_id}`).

---

## 8. Simulators

### AutoParts Lagos shop — `demo/shop/`
- `app.py`: FastAPI shop. `GET /products`, `POST /orders` (2–3 SKUs; locks inventory rows through the **active inventory module**), `POST /reload` (hot-swap; only the default buggy file or `.runtime/` patches allowed), `POST /deploy` (deploy mode), `GET /health`. Logs to `demo/shop/logs/shop.log`; publishes `shop_order` and once-per-second `shop_metrics` (orders/min, error rate, p95).
- The bug lives in `demo/target-service/inventory.py` (lock-ordering deadlock). Concurrent orders with overlapping items deadlock; single clicks almost never do.
- `load.py`: concurrent shoppers (`--shoppers --rate --duration`), also started by `POST /api/sim/shop/load`.
- Normal-but-scary: `WARN cache cold` at startup; deploy mode writes a few `retry=1` drain lines while error rate stays < 1%.

### Virtual cold-chain fridge — `core/simulate/fridge_stream.py`
- Ticks inside the API (1 tick = 1 simulated minute). Readings: temperature, current, vibration, door.
- Faults: `door_open`, `condenser_fouling`, `power_surge`, `rapid_restart`, `defrost_stuck`. Actions: `close_door`, `clean_condenser`, `reset`.
- Normal-but-scary: defrost cycle, compressor start inrush, short restocking door-open, hot ambient.
- `snapshot()` is display-only; model input never contains the fault name.

### Scenario — `core/simulate/scenario.py`, `demo/timeline.yaml`
Scripted demo timeline behind **Play scenario**; `POST /api/sim/reset` restores the buggy shop module, the fridge and pending windows.

### Hardware bonus — `hardware/wokwi/`
ESP32 sketch + diagram for Wokwi.com: the same door/temperature signals from virtual firmware.

---

## 9. Web dashboard

`apps/web` (Next.js). Pages:

| Route | Purpose |
| :--- | :--- |
| `/` | Mission Control: top bar (systems, warning→fix, gate counts, models, Play/Reset, pair, token, sound, focus/presenter), left pane (shop topology map + freezer tile), center pane (incident list keyed by run, gate cards, detail drawer, new-incident sheet), right pane (agent trace + veto ring), activity feed |
| `/classic` | The pre-redesign dashboard, kept until the final video is recorded |
| `/incidents/[id]` | Shareable incident report (drawer content; 404 state for unknown/expired runs) |
| `/shop` | The customer storefront; shows products, Buy, live error rate |
| `/setup` | 6-step wizard: connect → teach it normal (upload) → review (quotes, conflicts) → learn baseline → policy → arm |

![Mission Control](screenshots/mission.png)

Mission components live under `apps/web/app/mission/` with shared state in `MissionProvider` (`state.tsx`); typed socket events in `app/types/api.ts`; hooks in `app/hooks/`; kit primitives in `app/ui/`. The old components (`components/ServiceMap.tsx`, `PipelineLane.tsx`, `VirtualFridge.tsx`, `Sparkline.tsx`) still serve `/classic`. The socket auto-reconnects every 2 s. Finished incidents stay listed until Reset.

---

## 10. Mobile app

`apps/mobile` (Flutter, Android first; Riverpod).

- **Pairing:** scan the dashboard's QR (`GET /api/pairing`) → API URL + token stored in secure storage.
- **Live:** WebSocket with auto-reconnect; resyncs open windows from `GET /api/actions` after reconnect. A foreground service keeps it alive while locked.
- **Alarm:** full-screen intent over the lock screen, looping alarm-channel sound, strong vibration escalating in the last 5 s; circular countdown driven by the server deadline. **DISAPPROVE** / **APPROVE NOW** (lock after one tap). Outcome screen.
- **Reports:** feed from `GET /api/runs` with filters; each report has the five steps, diagnosis, fix/runbook, verification, final action, temperature chart (fridge), PR link and the decision record; share as text.
- **Settings:** Test alarm, sound/vibration, permission checklist.
- iOS: best effort (time-sensitive notification + in-app alarm). FCM push for a fully closed app is not built.

Run: `cd apps/mobile && flutter run` (device on the same Wi-Fi; start the demo with `API_HOST=0.0.0.0`).

---

## 11. API reference

Base URL: `http://localhost:8001` (local) or the Railway URL. Bodies are JSON unless noted. Endpoints marked 🔒 require `MOBILE_API_TOKEN` when it is set.

### Core
| Method | Path | Purpose |
| :--- | :--- | :--- |
| GET | `/api/health` | Liveness |
| POST | `/api/logs` | Add a log line to the stream (`message`, `source`, `level`) |
| POST | `/api/diagnose` | Diagnosis only |
| POST | `/api/run` | Software loop (`log_text`, `source`, optional `target: "inventory"`) → `ExecutionResult` |
| POST | `/api/run/appliance` | Appliance loop on a generated window (fault name) |
| POST | `/api/run/appliance/readings` | Appliance loop on supplied `ApplianceTelemetry` |
| POST | `/api/telemetry/appliance` | Ingest a reading from a real/virtual device |
| GET | `/api/samples/deadlock` | Sample crash log |
| WS | `/api/ws` | Live `AgentStep` + `SimEvent` stream |

### Runs and veto windows
| Method | Path | Purpose |
| :--- | :--- | :--- |
| GET | `/api/runs` | Recent runs |
| GET | `/api/runs/{run_id}` | Result, steps, gate decision, decision record |
| GET | `/api/actions` | Open + recent veto windows |
| POST | `/api/actions/{run_id}/approve` 🔒 | Apply now |
| POST | `/api/actions/{run_id}/disapprove` 🔒 | Cancel (409 if too late) |
| GET | `/api/pairing` | Phone pairing payload for the QR |

### Setup and gate
| Method | Path | Purpose |
| :--- | :--- | :--- |
| POST / GET | `/api/systems` | Create / list systems |
| POST | `/api/systems/{id}/documents` | Upload docs (multipart: PDF, PNG/JPG, TXT/MD, or text) → extraction |
| GET / PUT | `/api/systems/{id}/profile` | Read / edit profile |
| POST | `/api/systems/{id}/profile/sample` | Load the bundled sample profile |
| POST | `/api/systems/{id}/profile/confirm` | Human confirmation |
| POST | `/api/systems/{id}/arm` | Arm the system |
| POST / GET | `/api/systems/{id}/mode` | Set / read mode (`mode`, `until`) |
| POST | `/api/systems/{id}/baseline/start` · `/finish` · `/observe` | Baseline learning |
| GET | `/api/systems/{id}/baseline` | Baseline status |
| POST / GET | `/api/systems/{id}/feedback` | "This is normal" (pending) / list |
| POST / DELETE | `/api/systems/{id}/feedback/{fid}`(`/confirm`) | Confirm / discard feedback |
| POST | `/api/incidents/candidate` | Watcher candidate → gate → run or suppress |

### Simulation
| Method | Path | Purpose |
| :--- | :--- | :--- |
| POST | `/api/sim/events` | Publish a `SimEvent` (shop, watcher) |
| GET | `/api/sim/fridge/state` | Fridge snapshot |
| POST | `/api/sim/fridge/fault` · `/action` · `/defrost` · `/restock` · `/ambient` | Fridge controls |
| POST | `/api/sim/fridge/apply-runbook` 🔒 | Apply a verified runbook |
| POST | `/api/sim/shop/load` | Start load (`shoppers` 1–32, `rate`, `duration` 1–300) |
| POST | `/api/sim/shop/deploy` | Shop deploy mode |
| POST | `/api/sim/shop/apply-fix` 🔒 | Hot-swap the verified patch into the shop |
| POST | `/api/sim/scenario/play` · GET `/status` | Scripted scenario |
| POST | `/api/sim/reset` | Reset shop, fridge, windows |

---

## 12. WebSocket events

`WS /api/ws` sends two shapes.

**`AgentStep`** — one per loop stage:
```json
{"run_id":"2729587a","domain":"software","source":"watcher","step":"verify",
 "attempt":1,"status":"PASS","model":"modal","duration_ms":9200,
 "detail":"26 passed in 0.07s","suggestions":[],"message":""}
```
`step`: `diagnose` · `generate` · `verify` · `done`.

**`SimEvent`** — `{"kind": "...", "payload": {...}}`:

| `kind` | Payload highlights |
| :--- | :--- |
| `shop_order` | `order_id`, `status`, `latency_ms`, `items` |
| `shop_metrics` | `orders_per_min`, `error_rate`, `p95_ms` |
| `fridge_reading` | temperature, current, vibration, door, mode |
| `watcher_trigger` | `rule`, `level`, `fingerprint`, `resource`, `matched_lines` |
| `gate_decision` | `decision`, `reason`, `citation`, `checks`, `recheck_in_s` |
| `fix_applied` | what was applied and where |
| `scenario_step` | scenario progress |
| `action_pending` / `action_tick` / `action_resolved` | veto window lifecycle |
| `setup_progress` / `baseline_progress` | wizard progress |

---

## 13. Testing

```bash
venv/bin/python -m unittest discover -s tests       # ≈290 tests, no network
cd apps/mobile && flutter test                       # mobile
npx tsc --noEmit -p apps/web                         # dashboard types
```
Model clients, Modal and HTTP are mocked in unit tests. `tests/test_setup_acceptance.py` runs the shop (S-*) and cold-chain (C-*) acceptance cases with a stubbed model. Live checks need real keys and the running demo.

---

## 14. Deployment

Railway hosts the public demo (`railpack.json`: `uvicorn apps.api.main:app --host 0.0.0.0 --port $PORT`).

| Service | URL |
| :--- | :--- |
| API | https://api-production-0c9a.up.railway.app |
| Web | https://web-production-926b3.up.railway.app |

Set the same environment variables as `.env` on the Railway services (never in the repo). `NEXT_PUBLIC_API_URL` is baked into the web build, so redeploy the web service after changing it. Set `CORS_ORIGIN_REGEX` to allow the web origin.

---

## 15. Troubleshooting

| Symptom | Cause | Fix |
| :--- | :--- | :--- |
| Dashboard shows "disconnected" / nothing works | API not running, or dashboard pointing at the wrong port (another app on `:8000`) | Start the API on `:8001`; `apps/web/.env.local` → `NEXT_PUBLIC_API_URL=http://localhost:8001` |
| `/shop` shows "unreachable", no products | Shop down, or CORS | Start the shop; shop allows `localhost:3000` (override with `CORS_ORIGIN_REGEX`) |
| Modal `AuthError` | Only one of `MODAL_TOKEN_ID` / `MODAL_TOKEN_SECRET` set, overriding `~/.modal.toml` | Unset both (in `.env` and the shell) or set both |
| Verification fails with Docker not found | Docker CLI not on `PATH` | Set `DOCKER_BIN` or add Docker Desktop's `bin` to `PATH`; build the image |
| Baseten 404 "check the model" | Wrong model id | `BASETEN_PATCH_MODEL=meta-models/muse-spark-open` |
| Model steps return 503 | No key loaded | Fill `.env`; `scripts/demo.sh` sources it |
| Fix/verification appear then vanish | Several runs from one burst replacing each other | Fixed: watcher quiet period (`--quiet-seconds 60`) |
| Every order fails with 503 after heavy traffic | Known shop worker-thread leak | Restart the shop (`./scripts/demo.sh` or the shop command) |
| No PR opened | `GITHUB_TOKEN` / `GITHUB_DEMO_REPO` not set | Create the demo repo and a fine-grained token |
| Phone shows no alarm | Permissions or not paired | Settings → permission checklist + Test alarm; `API_HOST=0.0.0.0`; same Wi-Fi |
| Defrost raises an alarm | System not armed or no profile | Run `/setup` (or load the sample profile) and arm |

---

## 16. Repository layout

```text
telemetry-agent/
├── apps/
│   ├── api/main.py               FastAPI hub: runs, sim, setup, gate, actions, WS
│   ├── web/app/                  Next.js: page.tsx (/), shop/, setup/, components/
│   └── mobile/                   Flutter on-call app
├── core/
│   ├── schemas/                  telemetry, diagnosis, remediation, events, profile
│   ├── infer/                    Meta, Baseten, Fireworks clients + failover
│   ├── agent/loop.py             shared loop (software + appliance)
│   ├── verify/                   Modal sandbox, Docker runner, targets, safety rules, contracts
│   ├── actions/                  GitHub PR, notify, auto-action windows
│   ├── watch/                    log watcher, rules, sensor watcher
│   ├── setup/                    extract, gate, modes, baseline, context, store
│   └── simulate/                 appliance windows, fridge stream, scenario
├── demo/
│   ├── shop/                     AutoParts Lagos shop + load generator
│   ├── target-service/           buggy inventory.py (PR target) + tests
│   ├── setup/                    sample spec sheet, rating plate, ops guide, profiles
│   ├── timeline.yaml, script.md  scenario + video script
├── hardware/wokwi/               ESP32 bonus
├── docker/sandbox/               Docker verification image
├── scripts/                      demo.sh, build-sandbox-image.sh
├── samples/                      crash logs
├── tests/                        unit + acceptance tests
├── docs/                         PRD.md, DOCUMENTATION.md
└── *.md                          about, roadmap, simulation/mobile/setup roadmaps
```
