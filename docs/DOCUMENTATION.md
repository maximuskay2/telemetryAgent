# TelemetryAgent — Technical Documentation

What we built, how it works, and how the pieces fit together. For *why*
we built it, see the [PRD](PRD.md). For step-by-step use (demo, deploy,
connect a customer), see [USAGE.md](USAGE.md).

**TelemetryAgent** is an AI on-call engineer. It watches software and
physical equipment, decides what is normal vs a real failure, writes a
fix, **proves** that fix in a sandbox, and asks a human before it acts.

It was built for the [Meta Global AI Developer Hackathon](https://cerebralvalley.ai/e/meta-ai-developer-hackathon/details)
(Indie track, Oct 27 – Nov 4 2026) by **Akingbade Kayode**
(Maximusinfotech Services) with Muse Code contributors **James**
(backend core), **John** (web / app / look), **Jude** (usage, allowance,
Rust/PHP), and **Janet** (tester).

The product is **free for now**. There is no checkout, no price, no
Stripe. Hosted customers get a fair-use allowance; we track what each
organization costs so we can price it later.

**Public site**

| Service | URL |
| :--- | :--- |
| Web | https://web-production-926b3.up.railway.app |
| API | https://api-production-0c9a.up.railway.app |
| Proof app (example customer) | https://proof-app-production-a916.up.railway.app |

Repo: [`maximuskay2/telemetryAgent`](https://github.com/maximuskay2/telemetryAgent).
Railway **web** and **api** deploy from `main` (web root `apps/web`).

---

## What a visitor sees

Home (`/welcome`) has **two doors**. Mission Control does not open until
a walkthrough finishes. There is no “Skip to Mission Control”.

| Door | Who | What happens |
| :--- | :--- | :--- |
| **Try the live demo** | Anyone, no account | `/start` → guided setup of AutoParts Lagos + the freezer → Mission Control |
| **Connect your production** | Signed-in account | `/signin` → `/connect` → your logs, repo, hosting, devices |

Menu pages (not on the home hero):

- **How to** — `/guide`
- **Support** — `/support` (`support@maxit.com.ng`, `0803 695 4577`)

**Advanced setup** (`/setup`) is only a link *inside* a walkthrough:
demo **Read the manuals**, or production **Teach**. It is not a home
shortcut.

After sign-in, the account chrome is Connect · Members · Devices ·
Usage. The live demo stays one click away.

**Brand.** Light mode is the default; dark is available. Primary blue is
Meta blue `#0866FF`. Attribution is “Built with Muse Spark” / “Built on
Meta’s Muse models” — never Meta or Facebook logos, never “by Meta”.
The mark is Jude’s **pulse-to-check** logo (`apps/web/app/components/Logo.tsx`,
`apps/web/public/logo.svg`, favicon + apple-touch icon). Headers, Home,
sign-in, and the browser tab use it in local and on the public site.

---

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
10. [Hosted product (accounts)](#10-hosted-product-accounts)
11. [Languages](#11-languages)
12. [Mobile app](#12-mobile-app)
13. [API reference](#13-api-reference)
14. [WebSocket events](#14-websocket-events)
15. [Testing](#15-testing)
16. [Deployment](#16-deployment)
17. [Troubleshooting](#17-troubleshooting)
18. [Repository layout](#18-repository-layout)
19. [Production route](#19-production-route-real-integrations)
20. [Team and support](#20-team-and-support)

---

## 1. Overview

TelemetryAgent runs one loop for two kinds of system:

```
CRASH            →  GRAB               →  SUGGEST           →  VERIFY                 →  FIX
shop fails          log watcher           Muse Spark           sandbox (fail → pass)    PR + hot-swap
fridge drifts       sensor watcher        diagnosis            safety rules             alert + work order
                    + the gate            Muse Spark Open                                (20 s phone veto)
                                          writes the fix
```

Two routes share that loop. Anyone can follow them from this file and
[USAGE.md](USAGE.md) — no team member required.

| | **Demo** (simulation) | **Production** |
| :--- | :--- | :--- |
| Account | None | Sign in (Clerk on hosted; access code on self-hosted) |
| Entry | Home → **Try the live demo** → `/start` | Home → **Connect your production** → `/signin` → `/connect` |
| Systems | Bundled AutoParts Lagos + virtual freezer | Customer logs/Sentry, GitHub repo, Railway/webhook, devices |
| Fridge | API virtual fridge + Mission Control buttons | Device protocol: Wokwi or `sim_device.py` ([USAGE § E](USAGE.md#e-wokwi--the-esp32-without-hardware)) |
| Mission Control | After guided setup only (no skip) | After Teach → Confirm + Arm |
| Local | `./scripts/demo.sh` → http://localhost:3000/welcome | Same process, then `/connect` |
| Public | https://web-production-926b3.up.railway.app/welcome | Same host, Sign in |

**Meta models used**

| Job | Model | Provider |
| :--- | :--- | :--- |
| Diagnosis, classification, document extraction | `muse-spark-1.3` | Meta Model API |
| Patch + test + runbook generation | `meta-models/muse-spark-open-1026` | Baseten (primary) |
| Generation backup | Muse Spark Open (`FIREWORKS_PATCH_MODEL`) | Fireworks |
| Final-attempt escalation | `muse-wonder-1.0` | Meta Model API |
| Building the project | Muse Code | `muse` CLI |

Generation fails over **Baseten → Fireworks → Meta Model API**;
providers without a key are skipped. Each streamed step records which
model and provider served it.

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
 │  production ingest (forwarder / Sentry) ─┤                                │
 │                                          ▼                                │
 │                 core/setup/gate.py  (suppress | observe | act)            │
 │                 core/usage/allowance.py  (hosted: fair-use before spend)  │
 │                                          ▼ act                            │
 │  core/agent/loop.py  /  core/repo_fix/   diagnose → generate → verify     │
 │                                          ▼                                │
 │                 core/actions/auto_action.py  (20 s veto window)           │
 │                                                                           │
 │  EventHub ─► WS /api/ws  (AgentStep + SimEvent)                           │
 │  Hosted: Clerk JWT + Postgres orgs (core/commerce)                        │
 │  Self-hosted: JSON under TA_DATA_DIR + optional CONNECT_ACCESS_CODE       │
 └──────────────┬───────────────────────────────────────────┬────────────────┘
                ▼                                           ▼
   apps/web (Next.js, port 3000)                 apps/mobile (Flutter)
   two doors, How to, Support,                   alarm, countdown, reports
   Mission Control, account pages
```

**Key design choices**
- **The API is the hub.** Watchers and simulators publish to it;
  dashboard and phone only read the WebSocket and call the API.
- **The server owns every decision timer.** The phone displays the
  countdown; if it's offline, the server still acts at the deadline.
- **Untrusted inputs stay data.** Logs, sensor windows and uploaded
  documents are passed to models as data, schema-validated, and never
  allowed to change policy.
- **Generated code only runs in a sandbox** and only counts as verified
  if its test fails on the real original file and passes on the patch.
- **Demo never depends on accounts.** Hosted orgs need Clerk + Postgres.
  The simulation route still runs from files when `DATABASE_URL` is unset.

---

## 3. Quick start

### Prerequisites
- Python 3.9+ and a virtualenv at `venv/`
- Node.js 20.9+ and npm
- Modal account (`modal setup`) **or** Docker Desktop for local verification
- Flutter 3.x + an Android phone (only for the mobile app)
- Model keys: `MODEL_API_KEY` (required), `BASETEN_API_KEY` (recommended),
  `FIREWORKS_API_KEY` (optional) — where to get each: [USAGE.md § A.1](USAGE.md#a1-prerequisites)

### Install
```bash
git clone https://github.com/maximuskay2/telemetryAgent.git telemetry-agent
cd telemetry-agent

cp .env.example .env              # fill in keys (see Configuration)

python3 -m venv venv
venv/bin/pip install -r requirements.txt
npm install                       # repo root: npm workspaces install apps/web

modal setup                       # once; saves ~/.modal.toml
./scripts/build-sandbox-image.sh  # optional: Docker fallback image
```

### Run everything (one command)
```bash
./scripts/demo.sh
```
This starts the API (`:8001`, with the fridge stream), the shop (`:8002`),
the dashboard (`:3000`) and the log watcher. Open http://localhost:3000 —
you land on `/welcome`. Use **Try the live demo**. Do not expect a skip
link into Mission Control.

For a phone on the same Wi-Fi: `API_HOST=0.0.0.0 ./scripts/demo.sh`, then
scan the "Pair phone" QR on the dashboard (after the walkthrough).

### Trigger incidents
| What | How |
| :--- | :--- |
| Software deadlock | Dashboard **Start traffic**, or `curl -X POST localhost:8001/api/sim/shop/load -H 'Content-Type: application/json' -d '{"shoppers":8,"rate":20,"duration":60}'` |
| Fridge faults | Fault buttons on the fridge tile (door open, condenser fouling, power surge, rapid restart, defrost stuck) |
| Normal-but-scary | Defrost, Restock, Ambient heat, Deploy shop buttons — these should be **ignored** with a reason once the system is armed |
| Full scripted demo | **Play scenario** (Reset to start over) |
| Manual | Paste a log or "Load sample" in the software panel |

A software run takes ~40–130 s (models + sandbox). After it passes, use
**apply fix** (or let the veto window expire) and watch the shop error
rate drop to 0%.

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

All secrets live in `.env` (git-ignored). Never commit keys or paste them
into logs. Agents never write `.env`.

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `MODEL_API_KEY` (or `META_MODEL_API_KEY`) | — | Meta Model API (Muse Spark, Muse Wonder) |
| `META_DIAGNOSIS_MODEL` | `muse-spark-1.3` | Diagnosis model |
| `META_ESCALATION_MODEL` | `muse-wonder-1.0` | Final-attempt model |
| `BASETEN_API_KEY` | — | Muse Spark Open on Baseten |
| `BASETEN_PATCH_MODEL` | `meta-models/muse-spark-open-1026` | Generation model id |
| `FIREWORKS_API_KEY`, `FIREWORKS_PATCH_MODEL` | — | Optional backup generation |
| `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET` | — | Only to override `~/.modal.toml`. Set **both or neither** |
| `TA_VERIFY` | — | `local` forces Docker verification |
| `DOCKER_BIN`, `TA_SANDBOX_IMAGE` | auto, `telemetry-agent-sandbox` | Docker fallback runner |
| `GITHUB_TOKEN` | — | Fine-grained token: `contents` + `pull_requests` write. Used for demo PRs; production repos use the token stored on each GitHub connection |
| `GITHUB_DEMO_REPO`, `GITHUB_BASE_BRANCH` | `owner/repo`, `main` | Where demo PRs are opened |
| `AUTO_ACTION_SECONDS` | `20` | Veto window length |
| `AUTO_ACTION_ENABLED` | `true` | Kill switch: `false` = every action needs explicit approval |
| `MOBILE_API_TOKEN` | — | Self-hosted: required on approve/disapprove/apply when set |
| `SHOP_PORT` | `8002` | Demo shop port |
| `INVENTORY_PATH` | `demo/target-service/inventory.py` | Inventory module the shop loads at start |
| `TA_DATA_DIR` | `data/` | File-store profiles, uploads, connections (mode `0600`), audit, pause — mount a volume in production |
| `FRIDGE_STREAM`, `FRIDGE_TICK_S` | `0`, `1.0` | Start the fridge at boot; seconds per tick (1 tick = 1 simulated minute) |
| `CORS_ORIGIN_REGEX` | localhost/LAN `:3000` | Allowed dashboard origins (API and shop) |
| `API_HOST`, `API_PORT`, `WEB_PORT` | `127.0.0.1`, `8001`, `3000` | `scripts/demo.sh` |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8001` (set in `apps/web/.env.local`) | Dashboard → API |
| `NEXT_PUBLIC_SHOP_URL` | `http://localhost:8002` | `/shop` page → shop |
| `PRODUCTION_CONNECT_ENABLED` | `1` | `0` switches `/connect` off: every connection route answers 403 |
| `CONNECT_ACCESS_CODE` | — | Self-hosted only: connection routes need header `X-Connect-Code`. Signed-in hosted users skip this door |
| `RAILWAY_TOKEN` | — | Optional local copy; production rollback uses the token stored on each Railway connection |
| `TA_FIXTURE_KEYS` | — | `1` accepts the `ta_live_fixture` key (automated tests only) |
| `DATABASE_URL` | — | Set = hosted Postgres orgs; unset = self-hosted file store (demo still works) |
| `CLERK_JWKS_URL`, `CLERK_SECRET_KEY`, `CLERK_API_URL` | — | Hosted sign-in. Web also needs `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` |
| `COMMERCE_MASTER_KEY` | — | Fernet key wrapping per-org data keys (hosted secrets at rest) |
| `COMMERCE_ADMIN_EMAILS` | — | Who may call `GET /api/admin/costs` |
| `TA_AUTH_TEST_ISSUER` | — | HS256 secret for local test JWTs — **never deploy** |
| `TA_FREE_SYSTEMS` | `3` | Hosted fair-use: systems per org |
| `TA_FREE_DEVICES` | `5` | Hosted fair-use: paired phones per org |
| `TA_FREE_FIX_RUNS_PER_MONTH` | `30` | Hosted fair-use: fix runs / UTC month |
| `TA_FREE_MONTHLY_COST_USD` | `25` | Hosted fair-use: estimated provider cost / month |

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
- `run_diagnostic_loop(log_text, max_attempts, on_event, original_code, open_pr, run_id, …)` — software (demo + simple runs).
- `run_appliance_loop(telemetry, max_attempts, on_event, send_alert, run_id, …)` — appliance.
- Both: diagnose → (stop with `NO_ACTION` if expected) → generate → verify → retry with feedback (≤3; last on Muse Wonder) → act. Every stage emits an `AgentStep` with model, provider and duration.

Production software fixes use `core/repo_fix/` (locate → snapshot →
sandbox → repro fail-to-pass → PR) with one **language adapter** per
language (§11).

### 5.4 Verification — `core/verify/`
| File | Role |
| :--- | :--- |
| `sandbox.py` | `verify_patch` / `verify_fix` in a Modal Sandbox (files written via `exec`); falls back to Docker on import/auth errors |
| `local_runner.py` | Docker runner: `--network none`, 512 MB, 1 CPU, pids limit 64 |
| `targets.py` | Allowlisted target files (e.g. `demo/target-service/inventory.py`) — never arbitrary paths |
| `safety_rules.py` | `validate_runbook()`: holding temperature range, compressor restart delay, power-off window, no disabling protection, plus profile limits/forbidden actions |
| `contracts.py` | Structural checks on generated code/tests |
| `repo_sandbox.py` | Customer-repo sandbox (one image per language) |

**Fail-to-pass:** the generated test runs against the original file
(must fail) and the patch (must pass). If nothing fails on the original,
the run ends as "possibly intended, needs human".

### 5.5 Actions — `core/actions/`
- `github_pr.py`: branch, commit the patched file + regression test, open a PR with diagnosis, test output, attempts.
- `notify.py`: SMS/work-order stub (shown on dashboard and phone).
- `auto_action.py`: veto windows (§7).
- `mitigate.py`: production rollback / restart proposals (expire unless a human approves).

### 5.6 Watchers — `core/watch/`
| File | Role |
| :--- | :--- |
| `log_watcher.py` | Tails the shop log; forwards WARNING/ERROR lines (≤5/s); on a hit sends `watcher_trigger` + the context window. Flags: `--debounce-minutes` (10), `--before` (30), `--after` (10), `--quiet-seconds` (60: no new run for this long after a run returns, so one burst = one run) |
| `rules.py` | `match_error` (Deadlock / ERROR / Traceback), `RetryClusterTracker` (≥2 retries on one item within 30 s), `fingerprint_for` |
| `sensor_watcher.py` | Per-reading temperature/current rules with streaks and debounce (defaults overridden by the profile) |
| `watcher.py` | Shared helpers: `LogTail`, `send_run`, `post_log`, `publish_sim_event` |

### 5.7 Commerce and usage
- `core/commerce/`: Postgres orgs, memberships, encrypted secrets, Clerk JWT / device-token auth (`auth.py`, `repo.py`, `db.py`).
- `core/usage/`: per-org usage events, free allowance, provider-credit alerts (Jude).
- `apps/api/routes/commerce.py`: `/api/orgs`, members, invites, devices, usage.

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

Stored in `data/profiles/<system_id>.json` (self-hosted) or the org’s
Postgres rows (hosted). Sample inputs and ready profiles: `demo/setup/`
(spec sheet PDF, rating plate photo, ops guide, `profiles/shop.json`,
`profiles/coldchain.json`).

### Extraction (`core/setup/extract.py`)
PDF text per page; images/scans through the model's vision input (OCR
fallback); the model fills the profile schema and must quote every
value. Unknown → empty. Conflicts between documents are flagged, not
resolved. Policy and hard limits from documents are ignored.

### The gate (`core/setup/gate.py`)
`evaluate(candidate, profile, mode, baseline, metrics)` runs before any
run starts. First decisive check wins:

| # | Check | Outcome |
| :--- | :--- | :--- |
| 1 | Hard limit breached | **act** (always) |
| 2 | System not armed | **observe** ("Setup needed") |
| 3 | Matches an expected behaviour within its limits | **suppress** + citation |
| 4 | Current mode explains it (within max duration) | **suppress** |
| 5 | Known in the baseline | **suppress** |
| 6 | Proof of impact (failure definition met) | **act**; otherwise **observe** and re-check in 30 s |

Each decision is broadcast as `gate_decision` with `reason`, `citation`
and the list of checks. Suppressed/observed decisions show as grey/amber
rows in the stream and never open an incident or alarm.

On hosted orgs, a **free-allowance** check runs before a spending fix
run. Monitoring and alerts keep working when the allowance is hit; only
generation + sandbox spend stops. The gate record then says
`free allowance reached: …`.

Related modules: `modes.py` (mode state, overrun detection),
`baseline.py` (learning), `context.py` (profile summary for diagnosis),
`sensor_watch.py` (profile-aware sensor evaluation), `store.py` (profile
persistence/versioning).

---

## 7. Veto window (auto-action)

`core/actions/auto_action.py`

- A window opens only when a run is **eligible**: software `PASS` with
  fail-to-pass against the real target; appliance runbook passed safety
  rules and maps to an automatable action (`close_door`, `clean_condenser`,
  `reset`, …); gate said `act`; profile allows auto-fix.
- `PendingAction` states: `pending → approved | disapproved | auto_applied`
  (plus failure states). First decision wins under a lock; a decision
  after the deadline gets **409**.
- Events: `action_pending` (deadline, summary) → `action_tick` (every
  second) → `action_resolved` (state, by whom).
- On approve or deadline the server calls the same path as the
  dashboard's apply buttons (`/api/sim/shop/apply-fix`,
  `/api/sim/fridge/apply-runbook`).
- `AUTO_ACTION_ENABLED=false` turns every window into "approval
  required". Self-hosted `MOBILE_API_TOKEN` protects decisions; hosted
  phones use per-user device tokens and org roles.
- Every window is recorded in the run's decision record
  (`GET /api/runs/{run_id}`).
- **Production mitigations differ:** a rollback/restart proposed for a
  customer system (`core/actions/mitigate.py`) opens the same kind of
  window but **expires** at the deadline unless a human approves —
  nothing runs by itself. Only the demo fixes above apply at the deadline.

---

## 8. Simulators

### AutoParts Lagos shop — `demo/shop/`
- `app.py`: FastAPI shop. `GET /products`, `POST /orders` (2–3 SKUs;
  locks inventory rows through the **active inventory module**),
  `POST /reload` (hot-swap; only the default buggy file or `.runtime/`
  patches allowed), `POST /deploy` (deploy mode), `GET /health`. Logs to
  `demo/shop/logs/shop.log`; publishes `shop_order` and once-per-second
  `shop_metrics` (orders/min, error rate, p95).
- The bug lives in `demo/target-service/inventory.py` (lock-ordering
  deadlock). Concurrent orders with overlapping items deadlock; single
  clicks almost never do.
- `load.py`: concurrent shoppers (`--shoppers --rate --duration`), also
  started by `POST /api/sim/shop/load`.
- Normal-but-scary: `WARN cache cold` at startup; deploy mode writes a
  few `retry=1` drain lines while error rate stays < 1%.

### Virtual cold-chain fridge — `core/simulate/fridge_stream.py`
- Ticks inside the API (1 tick = 1 simulated minute). Readings:
  temperature, current, vibration, door.
- Faults: `door_open`, `condenser_fouling`, `power_surge`,
  `rapid_restart`, `defrost_stuck`. Actions: `close_door`,
  `clean_condenser`, `reset`.
- Normal-but-scary: defrost cycle, compressor start inrush, short
  restocking door-open, hot ambient.
- `snapshot()` is display-only; model input never contains the fault name.

### Scenario — `core/simulate/scenario.py`, `demo/timeline.yaml`
Scripted demo timeline behind **Play scenario**; `POST /api/sim/reset`
restores the buggy shop module, the fridge and pending windows.

### Hardware — `hardware/`

This is the **production appliance** path. The **demo** freezer is the
virtual stream above — testers on the live demo do not need Wokwi.

- `wokwi/`: ESP32 sketch + `diagram.json` for [wokwi.com](https://wokwi.com)
  (board: ESP32 DevKit). Same protocol as a real chip: POST readings
  every 2 s, GET commands every 5 s, drive compressor/defrost/backup,
  ack. Default `API_BASE` is the public Railway API. Wokwi cloud cannot
  reach `localhost`. Judge/tester steps: [USAGE.md § E](USAGE.md#e-wokwi--the-esp32-without-hardware).
- `sim_device.py`: the same protocol in Python (used by tests and as
  the no-browser fallback):
  `python3 hardware/sim_device.py --api URL --device ID --key KEY --fault door_open`.

---

## 9. Web dashboard

`apps/web` (Next.js). Light is the default; a Light / Dark control is
remembered. First visit to `/` goes to `/welcome` unless the browser
already finished a walkthrough (`localStorage` onboarded flag) or the
URL is `/?tour=1`.

| Route | Auth | Purpose |
| :--- | :--- | :--- |
| `/welcome` | public | Landing: two doors, no skip |
| `/guide` | public | How to (demo path + production path) |
| `/support` | public | Email + phone |
| `/start`, `/start/setup` | public | Demo onboarding, then guided setup that arms shop + freezer |
| `/signin` | public | Clerk (or local test JWT). After sign-in, default next is `/connect` |
| `/invite/[token]` | sign-in to accept | Join an organization |
| `/connect` | signed-in | Production wizard. Software: System → Logs → Repo → Hosting → Teach → Promise → Pair → Start. Appliance: System → Device → Teach → … `/connect?system=<id>` is Test / Rotate / Disconnect |
| `/members` | signed-in | Invite, remove, transfer ownership, delete org |
| `/devices` | signed-in | Pair phones (10-minute code), revoke |
| `/usage` | signed-in | This month vs the free allowance (no prices) |
| `/` | after walkthrough | Mission Control: systems, shop map, freezer, incidents, agent trace, veto ring |
| `/mission` | — | Redirects to `/` (old links) |
| `/setup` | from walkthrough | Advanced: upload docs → review quotes → learn baseline → policy → arm |
| `/shop` | public | Demo storefront |
| `/incidents/[id]` | public | Shareable incident report |
| `/classic` | — | Pre-redesign dashboard (kept for the video) |
| `/kit` | — | UI primitives gallery (development) |

![Mission Control](screenshots/mission.png)

Mission components live under `apps/web/app/mission/` with shared state
in `MissionProvider` (`state.tsx`). Account chrome and `RequireAuth` live
under `apps/web/app/commerce/`. Production pages never wrap the demo.
`FirstVisitGate` sends unfinished first visits to `/welcome`.

---

## 10. Hosted product (accounts)

**Self-hosted** (no `DATABASE_URL`): one team, file store under
`TA_DATA_DIR`. Optional `CONNECT_ACCESS_CODE` on connection routes.
`MOBILE_API_TOKEN` for the phone. This is how the local demo and a
private Railway instance can run.

**Hosted** (`DATABASE_URL` + Clerk): many organizations, each with its
own users, systems, tokens and usage.

| Role | Can |
| :--- | :--- |
| `owner` | Everything, including delete org and transfer |
| `admin` | Connect, arm, approve, invite, revoke phones |
| `member` | View and approve |
| `viewer` | Read only |

Signing in creates an organization with that user as `owner`. Invites
are accepted at `/invite/<token>`. Removing a member stops their web
session and phone token immediately.

**Free allowance** (overridable; Jude’s `core/usage/allowance.py`):

| Limit | Default |
| :--- | :--- |
| Systems | 3 |
| Paired phones | 5 |
| Fix runs / UTC month | 30 |
| Estimated provider cost / month | $25 |

Abuse guards: 10 000 ingest lines / minute and 10 fix runs / hour per
org. When the allowance is hit, alerts still fire; spending fix runs
are blocked with a cited gate reason.

Secrets you paste (GitHub, Railway, webhook) are stored server-side and
never returned — the list shows a hint only. Hosted secrets are
envelope-encrypted (`COMMERCE_MASTER_KEY`).

---

## 11. Languages

The production repo-fix pipeline is not Python-only. Adapters live in
`core/repo_fix/lang/` and register themselves (`ADAPTER` / `ADAPTERS`).

| Language | Adapter | Detect | Suite |
| :--- | :--- | :--- | :--- |
| Python | `python.py` | `requirements.txt` / `pyproject.toml` | `python -m pytest` |
| JavaScript / TypeScript | `javascript.py` | `package.json` (`tsconfig.json` → TypeScript) | Jest / Vitest / Mocha |
| Java / Kotlin | `java.py` | `pom.xml` / `build.gradle` (`.kt` → Kotlin) | Maven / Gradle |
| Go | `go.py` | `go.mod` | `go test ./...` |
| Rust | `rust.py` (Jude) | `Cargo.toml` | `cargo test` |
| PHP | `php.py` (Jude) | `composer.json` | PHPUnit / Pest |

The crash trace picks the adapter; `detect(paths)` must also match the
repo. Unknown language: recorded and alerted, **no fix run**, gate says
`auto-fix not supported for <language> yet`. Unprovable cases become
**draft** PRs with diagnosis only. One open PR per error fingerprint;
repeats comment.

Go is the least reliable today (drafts more often). Java / Kotlin
sandboxes are slower (~150–200 s) than most others (~20–40 s).

---

## 12. Mobile app

`apps/mobile` (Flutter, Android first; Riverpod).

- **Pairing:** scan the dashboard's QR (`GET /api/pairing`) → API URL +
  token stored in secure storage. Hosted: pair from `/devices` with a
  10-minute code, then claim (`POST /api/devices/claim`).
- **Live:** WebSocket with auto-reconnect; resyncs open windows from
  `GET /api/actions` after reconnect. A foreground service keeps it
  alive while locked.
- **Alarm:** full-screen intent over the lock screen, looping
  alarm-channel sound, strong vibration escalating in the last 5 s;
  circular countdown driven by the server deadline. **DISAPPROVE** /
  **APPROVE NOW** (lock after one tap). Outcome screen.
- **Reports:** feed from `GET /api/runs` with filters; each report has
  the five steps, diagnosis, fix/runbook, verification, final action,
  temperature chart (fridge), PR link and the decision record; share as
  text.
- **Production incidents:** a "Software · PR ready" card (open the PR,
  or **Roll back now** when hosting is connected) and cold-chain
  "Choose a fix" cards; a Pause-all toggle that round-trips to the
  server.
- **Settings:** Test alarm, sound/vibration, permission checklist.
- iOS: best effort (time-sensitive notification + in-app alarm). FCM
  push for a fully closed app is not built.

**Download (users):** Android APK — `/downloads/telemetry-agent.apk` on
the site (also [public web](https://web-production-926b3.up.railway.app/downloads/telemetry-agent.apk))
or **How to → Download APK** (`/guide#phone`). Pair to the **demo**
(Mission Control **Pair** QR) or to **production** (**Devices** pairing
code). Rebuild with `./scripts/build-apk.sh`.

**From source:** `cd apps/mobile && flutter run` (device on the same
Wi-Fi; start the demo with `API_HOST=0.0.0.0`).

---

## 13. API reference

Base URL: `http://localhost:8001` (local) or the Railway URL. Bodies are
JSON unless noted. Endpoints marked 🔒 require `MOBILE_API_TOKEN` when
it is set (self-hosted). Hosted org routes need a session JWT
(`Authorization: Bearer`) and, where noted, `X-Org-Id`.

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
| POST | `/api/systems/{id}/arm` · `/disarm` | Arm / disarm ("Stop watching") |
| DELETE | `/api/systems/{id}` | Delete a system |
| POST / GET | `/api/systems/{id}/mode` | Set / read mode (`mode`, `until`) |
| POST | `/api/systems/{id}/baseline/start` · `/finish` · `/observe` | Baseline learning |
| GET | `/api/systems/{id}/baseline` | Baseline status |
| POST / GET | `/api/systems/{id}/feedback` | "This is normal" (pending) / list |
| POST / DELETE | `/api/systems/{id}/feedback/{fid}`(`/confirm`) | Confirm / discard feedback |
| POST | `/api/incidents/candidate` | Watcher candidate → gate → run or suppress |
| GET | `/api/gate/decisions` | Recent gate decisions |
| POST / GET | `/api/demo/bootstrap` · `/api/demo/status` | Create / read the demo shop + freezer (guided setup) |
| POST | `/api/demo/{id}/documents` · `/learn` | Guided-setup documents and learning |

### Production connections
Connection keys are `ta_live_*`, shown once on create. Secrets you paste
are stored server-side and never returned.

| Method | Path | Purpose |
| :--- | :--- | :--- |
| GET | `/api/connections/enabled` | `{enabled, code_required}` |
| POST | `/api/connections/code` | Check an access code (`X-Connect-Code`) → 200 or 401 |
| POST | `/api/connections` | Create (`system_id`, `kind`: `logs`·`sentry`·`github`·`railway`·`webhook`·`device`, `config`, `secret`) → connection + one-time key |
| GET | `/api/connections?system_id=` | List (hints only) |
| POST | `/api/connections/{id}/test` | Live check for `github`, `railway`, `webhook` |
| DELETE | `/api/connections/{id}` | Disconnect; the key fails immediately |
| POST | `/api/ingest/logs` | Log lines, `Authorization: Bearer ta_live_…` |
| POST | `/api/ingest/sentry/{key}` | Sentry issue-alert webhook |
| GET | `/forwarder.py` | The log forwarder script, served by the API |
| GET / POST | `/api/actions/pause` (POST 🔒) | Read / set Pause-all |
| GET | `/api/incidents/{run_id}/options` | Fix options (open PR, rollback, restart, cold-chain) |
| POST | `/api/incidents/{run_id}/options/{option_id}/execute` 🔒 | Run one option |
| GET | `/api/devices/{device_id}/commands` | Device polls its queue (device key) |
| POST | `/api/devices/{device_id}/commands/{command_id}/ack` | Device acknowledges a command |
| POST | `/api/devices/{device_id}/readings` | Device reading (device key) |

### Organizations (hosted)
| Method | Path | Purpose |
| :--- | :--- | :--- |
| POST / GET | `/api/orgs` | Create / list orgs for the signed-in user |
| GET / DELETE | `/api/orgs/{id}` | Read / delete (owner; grace period) |
| GET | `/api/orgs/{id}/members` | List members |
| POST | `/api/orgs/{id}/invites` | Invite by email + role |
| DELETE | `/api/orgs/{id}/members/{user_id}` | Remove |
| POST | `/api/orgs/{id}/transfer` | Transfer ownership |
| POST | `/api/orgs/{id}/devices/pair` | 10-minute pairing code |
| POST | `/api/devices/claim` | Phone claims the code → `ta_dev_` token |
| GET | `/api/orgs/{id}/devices` | List paired phones |
| POST | `/api/orgs/{id}/devices/{id}/revoke` | Revoke a phone |
| GET | `/api/orgs/{id}/usage` | This month vs the free allowance |
| GET / POST | `/api/orgs/{id}/export` · `/api/orgs/restore` · `/purge` | Lifecycle (Postgres required) |

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

## 14. WebSocket events

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
| `connection_status` | `connection_id`, `system_id`, `status` (`ok`/`error`), `detail` |
| `actions_paused` | `paused` (Pause-all) |
| `pr_opened` | production repo-fix PR opened |
| `option_status` | progress of an incident option |

---

## 15. Testing

```bash
./scripts/check.sh                                   # python suite + simulation smoke + web build
venv/bin/python -m pytest -q tests                   # 1000+ tests, no network (Docker tests need Docker)
cd apps/mobile && flutter test                       # mobile
npx tsc --noEmit -p apps/web                         # dashboard types
```

`scripts/smoke_demo.sh` starts the API on a spare port with a temporary
data dir, arms the demo shop and runs two live agent runs (needs model
keys). Model clients, Modal and HTTP are mocked in unit tests.
`tests/test_setup_acceptance.py` runs the shop (S-*) and cold-chain
(C-*) acceptance cases with a stubbed model. Commerce tests skip
Postgres unless `TEST_DATABASE_URL` is set. Live checks need real keys
and the running demo.

---

## 16. Deployment

Railway project `telemetry-agent` hosts the public demo.

| Service | Source | URL |
| :--- | :--- | :--- |
| `api` | `maximuskay2/telemetryAgent` @ `main` (repo root) | https://api-production-0c9a.up.railway.app |
| `web` | same repo @ `main`, root directory `apps/web` | https://web-production-926b3.up.railway.app |
| `proof-app` | `maximuskay2/telemetryAgent-proof-app` | https://proof-app-production-a916.up.railway.app |

`railpack.json` starts the API:
`uvicorn apps.api.main:app --host 0.0.0.0 --port $PORT`.

A push to `main` deploys web and api. `NEXT_PUBLIC_API_URL` is baked
into the web build — redeploy web after changing it. Set
`CORS_ORIGIN_REGEX` to allow the web origin.

Set the same environment variables as `.env` on the Railway services
(never in the repo).

- **Demo / self-hosted API:** file store in `TA_DATA_DIR`. Railway disks
  are wiped on redeploy unless you mount a volume. Optional
  `CONNECT_ACCESS_CODE` on connection routes.
- **Hosted API:** `DATABASE_URL` (Railway Postgres) + Clerk keys +
  `COMMERCE_MASTER_KEY`. Then `/connect` is sign-in, not a shared code.
  The public API may still be running in self-hosted mode until those
  vars are set — the **web flow** (two doors, How to, Support) is live
  either way.
- Phones on a self-hosted public API use `MOBILE_API_TOKEN` (not
  published — share it with judges directly). Hosted phones use
  `/devices` pairing codes.

Full deploy steps: [USAGE.md § B](USAGE.md#b-run-it-in-production).

---

## 17. Troubleshooting

| Symptom | Cause | Fix |
| :--- | :--- | :--- |
| Dashboard shows "disconnected" / nothing works | API not running, or dashboard pointing at the wrong port (another app on `:8000`) | Start the API on `:8001`; `apps/web/.env.local` → `NEXT_PUBLIC_API_URL=http://localhost:8001` |
| `/` sent you to `/welcome` | First visit, walkthrough not finished | Use **Try the live demo**. There is no skip |
| `/connect` sent you to `/signin` | Production is gated | Sign in, or use the live demo from Home |
| `/shop` shows "unreachable", no products | Shop down, or CORS | Start the shop; shop allows `localhost:3000` (override with `CORS_ORIGIN_REGEX`) |
| Modal `AuthError` | Only one of `MODAL_TOKEN_ID` / `MODAL_TOKEN_SECRET` set, overriding `~/.modal.toml` | Unset both (in `.env` and the shell) or set both |
| Verification fails with Docker not found | Docker CLI not on `PATH` | Set `DOCKER_BIN` or add Docker Desktop's `bin` to `PATH`; build the image |
| Baseten 404 "check the model" | Wrong model id | `BASETEN_PATCH_MODEL=meta-models/muse-spark-open-1026` |
| Model steps return 503 | No key loaded | Fill `.env`; `scripts/demo.sh` sources it |
| Fix/verification appear then vanish | Several runs from one burst replacing each other | Watcher quiet period (`--quiet-seconds 60`) |
| Every order fails with 503 after heavy traffic | Known shop worker-thread leak | Restart the shop (`./scripts/demo.sh` or the shop command) |
| No PR opened | `GITHUB_TOKEN` / `GITHUB_DEMO_REPO` not set | Create the demo repo and a fine-grained token |
| Phone shows no alarm | Permissions or not paired | Settings → permission checklist + Test alarm; `API_HOST=0.0.0.0`; same Wi-Fi |
| Defrost raises an alarm | System not armed or no profile | Finish the walkthrough (or Advanced setup) and arm |
| Production errors arrive but no fix starts | System not armed, no GitHub, no traceback frames, unsupported language, or allowance reached | Teach → **Confirm + Arm**; connect the repo; forward full traces; check `/usage` |
| Fix run says "collection error" / import fails | Tests can't import the app | Make the language's suite work from the repo root |
| Railway test: "Not Authorized" | Project token, or token can't see the service | Account/workspace token from railway.com/account/tokens |
| Railway test: "railway connection needs config.service_id" | Connection made without a service ID | Disconnect and reconnect with the service ID |
| GitHub test: "can read, cannot open PRs" | Token lacks write | Fine-grained token: Contents + Pull requests **read and write** |
| `/connect` says it's switched off | `PRODUCTION_CONNECT_ENABLED=0` | Set it to `1` (or unset) and redeploy the API |
| `/connect` asks for an access code | Self-hosted + `CONNECT_ACCESS_CODE` | Get the code from whoever runs the instance, or sign in on hosted |
| Railway did not pick a GitHub push | Service had no GitHub source | Web and api must be connected to `maximuskay2/telemetryAgent@main` |
| App on Railway/Render has no log file | Platform logs go to its own stream | Pipe `railway logs` into a file and forward that ([USAGE C.1](USAGE.md#c1-logs--ship-us-your-errors)) |

---

## 18. Repository layout

```text
telemetry-agent/
├── apps/
│   ├── api/main.py               FastAPI hub
│   ├── api/routes/               production.py, devices.py, commerce.py
│   ├── web/app/                  Next.js: welcome, guide, support, start,
│   │                             signin, connect, members, devices, usage,
│   │                             mission, setup, shop
│   └── mobile/                   Flutter on-call app
├── agent/ta_forward.py           customer log forwarder (also /forwarder.py)
├── core/
│   ├── schemas/                  telemetry, diagnosis, remediation, events, profile
│   ├── infer/                    Meta, Baseten, Fireworks + failover
│   ├── agent/loop.py             shared loop (software + appliance)
│   ├── verify/                   Modal, Docker, repo sandbox, safety rules
│   ├── actions/                  GitHub PR, notify, veto, mitigate
│   ├── connections/              connection store, key auth, GitHub checks
│   ├── ingest/                   production log/Sentry ingest → gate
│   ├── repo_fix/                 locate → snapshot → sandbox → prove → PR
│   ├── repo_fix/lang/            python, javascript, java, go, rust, php
│   ├── devices/                  device command queue + cold-chain options
│   ├── commerce/                 orgs, auth, encrypted store (James)
│   ├── usage/                    events, allowance, costs (Jude)
│   ├── watch/                    log watcher, rules, sensor watcher
│   ├── setup/                    extract, gate, modes, baseline, store
│   └── simulate/                 fridge stream, scenario
├── demo/                         AutoParts Lagos + sample profiles
├── examples/proof-app/           reference customer app (real bug + tests)
├── hardware/                     sim_device.py + wokwi/ firmware
├── docker/sandbox/               Docker verification image
├── scripts/                      demo.sh, check.sh, smoke_demo.sh, commerce-*
├── tests/                        unit + acceptance + commerce
├── docs/                         PRD, DOCUMENTATION, USAGE, production-*, proof-run
│   └── brand/telemetry-agent-logo.png   Jude’s pulse-to-check master
├── commercial-roadmap.md         accounts, free-for-now, look
└── languages-roadmap.md          auto-fix beyond Python
```

---

## 19. Production route (real integrations)

How a real customer error becomes a proven PR:

```
customer app ─► ta_forward.py / Sentry ─► POST /api/ingest/* (ta_live_ key)
                                              │ reassemble traces (per language)
                                              ▼
                                      gate (§6) + allowance (§10)
                                              ▼ armed + GitHub + frames + language supported?
core/repo_fix: locate frames → diagnose → snapshot repo at --commit → sandbox
  → baseline suite → repro test must FAIL → patch (≤ 3 files) → repro PASSES, no new failures
  → PR on the customer repo (one open PR per fingerprint; repeats comment hourly)
  → unprovable → draft PR with diagnosis
                                              ▼ hosting connected
core/actions/mitigate: rollback / restart proposal → 20 s window → expires unless approved
```

Customer-facing steps: [USAGE.md § C](USAGE.md#c-connect-your-production-customer-guide).

- [production-backend.md](production-backend.md): connections, ingest, repo-fix, mitigations, commerce env.
- [production-devices.md](production-devices.md): device options, firmware, the `/connect` wizard half of the proof run.

---

## 20. Team and support

| Person | Role |
| :--- | :--- |
| Akingbade Kayode (Maximusinfotech Services) | Owner, product, deploy, docs |
| James | Muse Code — backend core (commerce store, auth, language contracts, Java/Kotlin/Go) |
| John | Muse Code — web / app / look (Clerk session, members, devices, Meta-style UI) |
| Jude | Muse Code — usage + free allowance, Rust/PHP adapters, pulse-to-check logo |
| Janet | Muse Code — tester (report in-repo; does not implement or push `main`) |

**Support (human):** email [support@maxit.com.ng](mailto:support@maxit.com.ng),
phone [0803 695 4577](tel:+2348036954577). In the product: `/support`.
How to: `/guide`.
