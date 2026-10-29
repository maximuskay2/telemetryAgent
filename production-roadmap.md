# 🔌 TelemetryAgent: Real Production Roadmap (Connect → Detect → Fix → Notify → Act, without downtime)

**Goal (24 hours, two developers in parallel):** a real customer, not our simulation, can:
1. **connect** their production server, their GitHub repo and (optionally) their hosting platform or a cold-chain device;
2. have TelemetryAgent **catch a real error**, write and **prove a fix on their real code**, and open a **PR on their repo**;
3. get the incident and the **fix options on our Flutter app**: software (PR ready, roll back, restart) and hardware (remote defrost, setpoint, backup unit, technician);
4. be confident **nothing in production is shut down or changed without them**. Every action is reversible, goes through the gate and the cancel window, and has a kill switch.

**Team:**
- **James — Backend.** Connections, ingest, the real fix pipeline, safe production actions.
- **John — App, Hardware, Web.** Flutter action center, device options + firmware, the `/connect` wizard.

**Starting point:** `main` @ `21246cd` (Oct 29). This commit has the Mission Control UI, the guided demo journey, the Home links, the mobile classic mint-green theme and the Android splash fix. 485 Python tests pass. Both developers branch from here. **§9 has the copy-paste brief for each.**

**Two routes, both always working:**
- 🟢 **Simulation route (preserved, frozen):** `/welcome` → `/start` → `/start/setup` → Mission Control with the demo shop and freezer.
- 🔵 **Production route (new):** `/welcome` → `/connect` → the customer's real server, repo, hosting and devices.

> This file owns **real integrations** and **how James and John work together**. `journey-roadmap.md` owns screen order, `ui-roadmap.md` the look, `mobile-roadmap.md` app basics. Nothing here changes the gate, the veto rules or existing API shapes.

---

## 0. Where we are (repo audit, Oct 29)

| Piece | Real today | Simulation-only today |
|---|---|---|
| Diagnosis / patch / test (Muse Spark, Spark Open, Wonder) | ✅ | — |
| Fail-to-pass proof in Modal | ✅ | Runs **one** generated `test_solution.py` against **one** file (`core/verify/sandbox.py`) |
| Code it can fix | — | Only `demo/target-service/inventory.py` (`core/verify/targets.py` rejects anything else; `target: Literal["inventory"]`) |
| Pull request | ✅ Git Data API, any `repo` argument | Repo comes from one env var `GITHUB_DEMO_REPO` |
| Error intake | ✅ `POST /api/logs`, log tail, `POST /api/telemetry/appliance` | No auth keys, no Sentry/webhook, no packaged forwarder |
| "Deploy" | — | Hot-swap of the demo shop's module |
| Hardware fix | Runbook text + deterministic safety rules ✅ | Alert is a stub (`core/actions/notify.py`); no device commands |
| Phone app | ✅ WebSocket, full-screen alarm, local notifications, foreground service, Approve/Disapprove with `X-Mobile-Token`, QR pairing | No fix options, no PR actions, no "pause all". (Android splash build error fixed in `21246cd`; theme is classic mint-green `#A5EFC0` on `#0B0E10`.) |
| Code layout | `apps/api/main.py` holds every route; no `apps/api/routes/`, `core/connections/`, `core/schemas/production.py`, `agent/` or `scripts/check.sh` yet | James creates them at H0 |

---

## 1. The real customer experience

```
Web /connect (John)                          Their infra                    Our backend (James)
───────────────────                          ───────────                    ───────────────────
1 Name the system
2 Connect logs     ── one-liner forwarder ─► server tails app.log ──────►  /api/ingest/logs (key)
                   ── or Sentry webhook ───► Sentry ─────────────────────►  /api/ingest/sentry/{key}
3 Connect repo     ── repo + scoped token ─► GitHub  ◄── read code, open PR ── real fix pipeline
4 Connect hosting  ── Railway token or      ► Railway / their own script ◄── rollback · restart
   (optional)         signed webhook
5 Connect device   ── device key ──────────► ESP32 ── readings ─────────►  /api/telemetry/appliance
                                              ESP32 ◄── polls commands ──  /api/devices/{id}/commands
6 Teach normal     (existing setup: docs + learn baseline)
7 Permissions      PR-only · PR + rollback · auto-merge (🔒 off by default) + the uptime promise
8 Pair phone → Start watching

Incident: error ─► gate ─► diagnose ─► their repo @ commit in Modal ─► reproduce test fails
          ─► patch ─► new test passes + their suite still green ─► PR on THEIR repo
          ─► Flutter app (John): "PR ready · Roll back now? 20 s" / "Choose a fix" ─► audit log
```

---

## 2. The uptime promise (shown on `/connect`, enforced in code)

1. **Read-only by default.** Logs come *to* us. We never SSH, never get shell access, never hold database credentials.
2. **We never edit production code directly.** Fixes arrive as a **pull request**. Their CI runs and a human merges; auto-merge is off by default and a human-only setting 🔒.
3. **Only reversible actions run automatically:** roll back to the previous deployment, restart a service, or a device action inside the hard limits. **Never** stop, scale to zero, delete, or power off without a human.
4. **Every action waits for the cancel window** (default 20 s, existing `core/actions/auto_action.py`). It rings the phone, and one tap cancels.
5. **Kill switches:** global `AUTO_ACTION_ENABLED`, per-system **Stop watching**, per-connection **Disconnect**, and a new **Pause all actions** on the phone and web.
6. **Rate limits:** at most 1 automatic mitigation per system per 10 minutes; no actions while learning; **one open PR per error fingerprint**.
7. **Full audit** of every decision, action, approver and result, visible in the incident report.
8. **Data disclosure:** code is copied only into a short-lived Modal sandbox and sent to the listed model providers. Secrets are server-side, never returned by the API, and never in `NEXT_PUBLIC_*`.

---

## 3. How James and John work together (read first)

### 3.1 Rules that keep them from blocking each other
- **R-1 Contracts first, frozen at hour 0.** Every new endpoint, model and WebSocket event in §3.4 is agreed before coding. James commits them as **stubs** that return the fixture data in §3.4 in the first hour. John builds against the stubs and never waits for the real logic. A contract change needs **both** to agree and a one-line note in §8.
- **R-2 Own files only.** Each person edits only the files in their column of §3.2. Need a change in the other person's file? Ask; don't edit.
- **R-3 One shared commit, at hour 0, by James.** It's the only time shared files change: new event kinds in `core/schemas/events.py`, the two `include_router` lines in `apps/api/main.py`, `core/schemas/production.py`, and the stub routers. After that, **`apps/api/main.py` is not touched by anyone** for the rest of the 24 h. All new routes live in the two router files.
- **R-4 Additive only.** No renames, no deleted fields, no changed response shapes. New fields are optional with defaults.
- **R-5 Branches + checkpoints.** James works on `prod/james`, John on `prod/john`, each in their **own git worktree** (§9.0). At each checkpoint (after each block), each rebases on `origin/main`, runs **`./scripts/check.sh`** (§3.5), and fast-forwards `main` to **their own branch only** if it's green (merge procedure in §9.0). Red check = don't merge; fix on the branch.
- **R-6 Never wait.** If a dependency isn't real yet, use the stub or fixture and show the "not connected yet" state. Every dependency in §5 has a stub available from hour 1.

### 3.2 File ownership

| Area | **James (Backend)** | **John (App · Hardware · Web)** |
|---|---|---|
| API routes | `apps/api/routes/production.py` (connections, ingest, pause, mitigations) | `apps/api/routes/devices.py` (incident options, device command queue) |
| Core | `core/connections/*`, `core/ingest/*`, `core/repo_fix/*` (new), `core/verify/repo_sandbox.py` (new), `core/actions/mitigate.py` (new), `core/actions/github_pr.py` (additive) | `core/devices/*` (new: options builder, command queue, safety checks on options) |
| Shared schemas | `core/schemas/production.py`: **written by James at H0**, then frozen (R-1) | reads only |
| Forwarder | `agent/ta_forward.py` (new, stdlib-only) | — |
| Web | — | `apps/web/app/connect/*` (new), `apps/web/app/welcome/*` (second door), `apps/web/app/types/production.ts` (new) |
| Mobile | — | `apps/mobile/**` |
| Firmware | — | `hardware/wokwi/*`, `hardware/sim_device.py` (new: software ESP32 that speaks the same protocol) |
| Proof app | `examples/proof-app/*` (new; ready to push to its own repo) | — |
| Tests | `tests/test_prod_*.py`, `tests/fixtures/prod_*` | `tests/test_devices_*.py`, `tests/fixtures/devices_*`, `apps/mobile/test/*` |
| Scripts | `scripts/check.sh`, `scripts/smoke_demo.sh` (H0) | — |
| Docs | `docs/production-backend.md` (new); at the very end James adds one link line for each doc to `docs/DOCUMENTATION.md` | `docs/production-devices.md` (new) |
| Status | `status/james.md` | `status/john.md` |

**Frozen for both (the simulation route):** `apps/api/main.py` (after H0), `core/agent/loop.py`, `core/setup/*`, `core/watch/*`, `core/simulate/*`, `demo/**`, `apps/web/app/{page.tsx,mission,setup,shop,start,classic,incidents}/**`, `apps/web/app/lib/setupApi.ts`. If a real bug forces a change there, it goes in its own small commit with both people told.

### 3.3 Simulation vs production: how the code chooses
- `SystemProfile.environment` is a `dict[str, str]` (`core/schemas/profile.py`). Demo systems already carry `environment["demo"] = "true"` (guided journey) or nothing (`/setup`). **Production systems get `environment["mode"] = "production"`**, set only by `/connect`. No key, or any other value, means demo.
- **Demo systems keep the exact current path:** `target="inventory"`, `GITHUB_DEMO_REPO`, hot-swap deploy, stub alert, and the sim fridge.
- **Production systems** go through James's `core/repo_fix` pipeline and John's options/commands. The switch is one helper, `core.connections.is_production(profile)`, used only inside the new routes, so the demo code never sees it.
- Flag **`PRODUCTION_CONNECT_ENABLED`** (default `1` locally, set per Railway env). With `0`, the `/connect` door and `/api/connections` return "coming soon". That's the emergency switch if the production route isn't ready for the video.

| | 🟢 Simulation route (frozen) | 🔵 Production route (new) |
|---|---|---|
| Web | `/welcome` "Try the live demo" → `/start` → `/start/setup` → `/?tour=1` | `/welcome` "Connect your production" → `/connect` → `/` |
| API | `/api/sim/*`, `/api/demo/*`, `/api/run`, `/api/logs`, `/api/incidents/candidate`, `/api/systems/*` | `/api/connections/*`, `/api/ingest/*`, `/api/devices/*`, `/api/incidents/{run_id}/options*`, `/api/actions/pause` |
| Code target | `demo/target-service/inventory.py` | their repo at the failing commit |
| PR repo | `GITHUB_DEMO_REPO` | the system's `github` connection |
| Deploy/act | shop hot-swap, sim fridge | Railway / signed webhook, ESP32 command queue |

### 3.4 Contracts (frozen at H0; James ships them as stubs in hour 1)

Models live in `core/schemas/production.py`; John mirrors them in `apps/web/app/types/production.ts` and `apps/mobile/lib/models/`.

```jsonc
// Connection (secrets never returned; key only once on create)
{ "id": "con_ab12", "system_id": "acme-api-9f2c", "kind": "logs|sentry|github|railway|webhook|device",
  "config": { "repo": "acme/api", "base_branch": "main" }, "secret_hint": "****abcd",
  "status": "waiting|ok|error", "detail": "", "last_seen": 1730200000.0 }

POST   /api/connections            { system_id, kind, config, secret? } -> { connection, key? }
GET    /api/connections?system_id= -> { connections: [Connection] }
POST   /api/connections/{id}/test  -> { ok, detail, permissions?: {read: bool, pull_requests: bool} }
DELETE /api/connections/{id}       -> { deleted: true }

POST /api/ingest/logs   (Authorization: Bearer ta_live_…)
  { "service": "api", "release": "v42", "commit": "9f2c…", "lines": [ { "ts": 1730200000.1, "level": "ERROR", "message": "Traceback …" } ] }
  -> { "accepted": 3, "candidates": 1 }
POST /api/ingest/sentry/{key}   (Sentry issue-alert webhook body) -> { "accepted": 1 }

// Incident options: same shape for software and hardware (John's router)
GET  /api/incidents/{run_id}/options -> { "run_id": "…", "domain": "software|appliance", "options": [
   { "id": "opt_1", "kind": "open_pr|rollback|restart|remote|manual|dispatch",
     "title": "Roll back to previous deploy", "detail": "…", "url": "https://github.com/…/pull/7",
     "safety": { "ok": true, "reason": "" },
     "status": "available|sent|done|failed|expired|cancelled" } ] }
POST /api/incidents/{run_id}/options/{id}/execute  (X-Mobile-Token) -> { "status": "sent", "command_id": "cmd_1" }

// Device command queue (John's router; device auth via James's key helper)
GET  /api/devices/{device_id}/commands  (Bearer) -> { "commands": [ { "id": "cmd_1", "action": "defrost|setpoint|power_cycle|backup_on", "params": {}, "expires_at": 1730200120 } ] }
POST /api/devices/{device_id}/commands/{cid}/ack  (Bearer) { "ok": true, "detail": "" } -> { "status": "done" }

// Pause (James)
GET  /api/connections/enabled -> { "enabled": true }   // PRODUCTION_CONNECT_ENABLED
GET  /api/actions/pause -> { "paused": false }
POST /api/actions/pause  (X-Mobile-Token) { "paused": true } -> { "paused": true }

// Software run result: additive optional fields (James fills them; John reads them)
{ "pr_url": "…", "repo": "acme/api", "suite": { "passed": 212, "failed": 0, "new_failures": 0 }, "mitigation": { "action": "rollback", "status": "proposed|done|cancelled" } }

// New WebSocket SimEvent kinds (added by James at H0)
connection_status { connection_id, system_id, status, detail }
option_status     { run_id, option_id, status, detail }
actions_paused    { paused }
pr_opened         { run_id, system_id, pr_url, repo }
```

**Python hand-off functions** (James implements; John's router calls them; stubbed at H0):
- `core.connections.is_production(profile) -> bool` (`profile.environment.get("mode") == "production"`)
- `core.connections.auth.system_for_key(key: str, kind: str) -> Optional[str]`
- `core.actions.mitigate.software_options(run: dict) -> list[Option]` (stub returns `[]` until R4)
- `core.actions.mitigate.execute(system_id: str, action: str, run_id: str) -> dict`
- `core.actions.mitigate.is_paused() -> bool` (John's command queue refuses new commands while paused)

### 3.5 `scripts/check.sh` (James writes it at H0; both run it before every merge)
1. `venv/bin/python -m unittest discover -s tests`: all existing **and** new tests.
2. `scripts/smoke_demo.sh`: starts the API on a spare port with a temp `TA_DATA_DIR`, then:
   - demo bootstrap → sample profile → arm;
   - `POST /api/incidents/candidate` with `system_id: "shop"` → `act`;
   - `GET /api/sim/fridge/state` → 200;
   - `POST /api/run` with the deadlock sample → a `run_id`;
   - `/welcome`, `/start`, `/start/setup`, `/shop`, `/setup` → 200 (when the web dev server is up).
   **This is the "simulation route preserved" guarantee.**
3. `npm run build -w apps/web` (types + build).
4. `cd apps/mobile && flutter analyze && flutter test`.

Steps 3–4 print a clear `SKIP (npm/flutter not found)` instead of failing when the tool is missing. The smoke test always uses a free random port and its own temp `TA_DATA_DIR`, so it never touches the live demo on 8001/8002/3000. Exit code is non-zero if any non-skipped step fails.

---

## 4. Build blocks

### 👷 James: Backend

**J-R0 · Contracts, stubs, connections, keys (H0–H2)**
- H0 shared commit (R-3):
  - `core/schemas/production.py` and the new event kinds;
  - `apps/api/routes/__init__.py` plus `apps/api/routes/{production,devices}.py` with **stub** handlers returning the §3.4 fixtures, including `GET /api/connections/enabled`;
  - the §3.4 hand-off functions as stubs (`core/connections/__init__.py`, `auth.py`, `core/actions/mitigate.py`);
  - two `include_router` lines at the end of `apps/api/main.py`;
  - `scripts/check.sh`, `scripts/smoke_demo.sh`.

  **Tell John "contracts are in"** (he starts immediately).
- Then the real `core/connections/store.py` (`data/connections/<id>.json`, mode 600), hashed `ta_live_` keys, `system_for_key`, create/list/test/delete. James owns `devices.py` only until this commit; after it, it's John's file.
- **Accept:** the key is shown once and stored hashed; a wrong key → 401; delete → the key fails immediately; `GET` never returns a secret; `check.sh` green.

**J-R1 · Real error intake (H2–H6)**
- `POST /api/ingest/logs` → existing rules → gate candidate with the real `system_id`; multi-line Python tracebacks become **one** event with parsed frames.
- `POST /api/ingest/sentry/{key}` (fixture `tests/fixtures/sentry_issue.json`).
- `agent/ta_forward.py`: stdlib-only single file; tail + rules + batch + retry/backoff; buffers while the API is down. Served at `GET /forwarder.py`.
- `connection_status` events: "waiting" → "ok" on the first line.
- **Accept:** a forwarder on another machine or container → "✓ first log" within 5 s; traceback = 1 candidate with frames; the Sentry fixture produces the same shape; a 30 s API outage loses no lines.

**J-R2 · Connect their GitHub repo (H6–H8)**
- Kind `github` `{repo, base_branch}` + fine-grained token (Contents RW, Pull requests RW, Metadata R). `test` checks repo, read access, PR permission and branch.
- `github_pr.py`: accepts repo/token from the connection; demo systems keep `GITHUB_DEMO_REPO` (§3.3).
- **Accept:** wrong token → readable error; read-only token → "can read, cannot open PRs"; valid → green with the default branch.

**J-R3 · Real fix pipeline on their code (H8–H16, the core)**
1. **Locate:** frames → repo paths by suffix match against the tree at the commit; top 1–3 files ±40 lines; no frames → model picks from the file list + keyword search (cap 5).
2. **Snapshot:** tarball at the commit (else base HEAD), ≤ 50 MB, skip `.git`, `node_modules`, binaries.
3. **Sandbox** (`core/verify/repo_sandbox.py`): Modal, Python 3.11, `pip install -r requirements.txt` or `-e .` (5-min cap), **baseline** `pytest -q`; no customer secrets inside.
4. **Reproduce:** `tests/test_telemetry_agent_<fp>.py` must **fail on original**; retry with output; Muse Wonder on the last attempt.
5. **Patch:** `files: [{path, content}]`, max 3 files.
6. **Prove:** new test passes **and** no baseline-passing test fails; store both outputs + suite summary.
7. **PR on their repo:** evidence in the body, label `telemetry-agent`, **one open PR per fingerprint** (else comment); `pr_opened` event; `pr_url`/`suite` on the run.
- **Accept:** a real error from the proof app → PR on that repo touching the right file; fail→pass proven; suite has no new failures; the same error ×5 → 1 PR; no tests / too big → draft PR with diagnosis only, no crash.

**J-R4 · Safe production actions + pause (H16–H19)**
- `core/actions/mitigate.py`: allowlist **`rollback`, `restart` only**. Railway adapter (redeploy previous successful deployment / restart) and a signed-webhook adapter (HMAC-SHA256 POST to the customer's URL).
- Proposed when the policy allows and the error rate passes the hard limit → existing 20 s window → phone → run/cancel → audit. Fills `software_options()` (open_pr, rollback, restart) for John's options route.
- `/api/actions/pause` + `actions_paused` event; rate limit 1 per system per 10 min; nothing while learning.
- **Accept:** a real Railway rollback brings the error rate down; valid HMAC (fixture); paused → nothing runs; 2nd mitigation within 10 min refused with a reason; `stop` / `delete` / `scale 0` impossible even if the model suggests them (unit test).

**J-R5 · Proof app + backend docs (H19–H21)**
- `examples/proof-app/`: small FastAPI service with a real bug (empty-cart division by zero or the deadlock), ~20 pytest tests, a `requirements.txt`, a Railway-ready start command, and the forwarder line. Ready to push to a new public repo `maximuskay2/telemetryAgent-proof-app` and deploy on Railway; Akingbade does that step (it needs repo-creation and Railway credentials).
- `docs/production-backend.md`, and the backend half of `docs/proof-run.md` (exact steps for the human proof run).

### 👷 John: App · Hardware · Web

**N-R0 · Confirm the app builds + mirror the contracts (H0–H2)**
- The Android splash fix is already in `21246cd` (`values/colors.xml` → `@color/splash_background`). **Verify only:** `flutter pub get && flutter analyze && flutter test`, then `flutter run` on the emulator. If anything fails, fix it on `prod/john` first.
- When James says "contracts are in": mobile models in `apps/mobile/lib/models/` + `apps/web/app/types/production.ts` from §3.4.
- New cards use the existing theme (`lib/theme.dart`, `lib/widgets/widgets.dart`, mint-green); no new palette.
- **Accept:** `flutter run` builds on the emulator; `flutter analyze` clean; models parse the §3.4 fixtures in a unit test.

**N-R1 · Hardware fix options + command queue (H2–H8)** (after James's H0 contracts; uses `system_for_key`)
- `core/devices/options.py`: builds options **from the stored appliance run's runbook + profile** (no change to `core/agent/loop.py`):
  - `remote`: Start defrost · Lower setpoint 1 °C (only within profile limits) · Power-cycle compressor (only after `restart_delay_s`) · Switch to backup unit;
  - `manual`: close door / check seal / move stock to unit B (checklist);
  - `dispatch`: call or WhatsApp the technician (work order text).
  Every option passes the existing deterministic safety rules; unsafe ones get `safety.ok=false` and are never executable.
- `apps/api/routes/devices.py`: options GET/execute (software options come from `mitigate.software_options()`; `[]` until James's R4), command queue GET/ack, 2-min expiry, refuse while `is_paused()`. Emits `option_status`.
- `/api/telemetry/appliance` accepts a Bearer device key for production devices **via a new route alias in `devices.py`** (`POST /api/devices/{device_id}/readings`), so the existing endpoint stays untouched.
- **Accept:** door-open run → 3 option groups; unsafe setpoint never offered; power-cycle refused before the delay; execute → command queued → ack → `done`; no ack → `expired` with "device offline".

**N-R2 · ESP32 firmware (H8–H10)**
- `hardware/wokwi`: post readings to `/api/devices/{id}/readings` with the key; poll commands every 5 s; drive relay/LED for compressor, defrost and backup; ack.
- `hardware/sim_device.py`: a stdlib-only software ESP32 that speaks the same protocol (readings, poll, ack, simulated relay state, `--fault door_open`). It proves the protocol end to end without hardware and is used in tests and the proof run.
- **Accept:** `sim_device.py` against a local API acks a tapped option within 10 s (automated test); the sketch compiles in Wokwi (human check); a real ESP32 is a bonus.

**N-R3 · Flutter action center (H10–H16)**
- Cards: **Software · PR ready** (summary, proof "fails → passes, suite green", **Open PR**, mitigation countdown **Roll back now / Cancel**); **Hardware · Choose a fix** (options with live `option_status`); **Watching** (quiet channel).
- **Pause all actions** toggle (home screen); "Paused" banner from `actions_paused`.
- Pairing QR `{api, token}` (existing flow). Keep the foreground service; **stretch:** FCM push.
- Until James's R3/R4 land, cards render from the stub fixtures and show "PR pending" / "No mitigation" (R-6).
- **Accept:** phone locked → real incident rings within 10 s; Open PR opens the right page; Cancel stops the rollback; hardware option toggles the device; Pause shows on web and phone within 2 s.

**N-R4 · Web `/connect` wizard + second door (H16–H21)**
- `/welcome`: second button **Connect your production** → `/connect` next to the existing CTA in `welcome/DemoCta.tsx` (hidden when `PRODUCTION_CONNECT_ENABLED=0`, read through a small `GET /api/connections/enabled` James adds in the H0 stubs, not a `NEXT_PUBLIC_*` flag). "Try the live demo" stays first and unchanged, as do the header's "Mission Control →" link and the Home links on other pages.
- `/connect` steps:
  1. name + type;
  2. logs (forwarder one-liner with the key / Sentry URL / curl) with a live "waiting → ✓ first log" (`connection_status`);
  3. repo + **Test**;
  4. hosting (Railway or webhook + secret) + **Send test ping**;
  5. device key + firmware snippet + "✓ first reading";
  6. teach normal (reuse `setupApi.ts` calls; don't edit the file);
  7. permissions + the full uptime promise + "I understand";
  8. pair phone → **Start watching**.
  It creates the system with `environment: {"mode": "production"}`.
- Connections panel on `/connect?system=…`: last seen, test, rotate key, **Disconnect**.
- **Accept:** a new user connects proof app + repo + Railway + phone in ≤ 10 min with no help; every step has a working Test and a readable error; the simulation route pages render unchanged (`check.sh`).

### 🤝 Together

**T-R1 · Proof run + video (H21–H24)**
1. Connect the proof app through `/connect`.
2. Hit the buggy endpoint → the error arrives → the phone rings ("rollback proposed") → let it run.
3. A PR appears on the proof repo with the proof → merge → Railway redeploys → the error is gone.
4. ESP32/Wokwi door open → phone → **Start defrost** → relay toggles.
5. Then the **simulation route** once more (the `/start` journey) to show both doors work.
- **Accept:** the whole run works twice from a clean state; final `check.sh` green; push only on Akingbade's OK.

---

## 5. 24-hour schedule (nobody waits)

| Hour | **James (Backend)** | **John (App · Hardware · Web)** | Checkpoint |
|---|---|---|---|
| H0–H1 | Contracts + stubs + `check.sh` (shared commit) | N-R0 verify app build (fix already in `21246cd`) | James: "contracts are in" |
| H1–H2 | J-R0 connections + keys real | N-R0 models/types from contracts | **H2 merge** |
| H2–H6 | J-R1 ingest + forwarder + Sentry | N-R1 options + command queue | **H6 merge** |
| H6–H8 | J-R2 repo connection | N-R1 finish + tests | |
| H8–H10 | J-R3 locate + snapshot | N-R2 ESP32 firmware | **H10 merge** |
| H10–H14 | J-R3 sandbox + reproduce | N-R3 Flutter cards (on stubs) | **H14 merge** |
| H14–H16 | J-R3 patch + prove + PR | N-R3 pause + polish | |
| H16–H18 | J-R4 mitigations + pause | N-R4 `/connect` steps 1–5 | **H18 merge**: John's cards now get real PRs/mitigations |
| H18–H19 | J-R4 rate limits + tests | N-R4 steps 6–8 + panel | |
| H19–H21 | J-R5 proof app on Railway + docs | N-R4 finish + docs | **H21 merge** |
| H21–H24 | T-R1 together: proof run ×2, video, fixes, final check | ← same | final |

**Dependencies, and how neither person waits:**
- John needs contracts → in at **H1** (stubs). He uses `system_for_key` (real at H2) for device auth; until then the stub accepts the fixture key.
- John's software options need `mitigate.software_options()` → stub `[]` until **H18**; the cards show "No mitigation" meanwhile.
- John's PR card needs `pr_url` → fixture from H1; real from **H16**.
- James needs nothing from John until T-R1.

**Cut order if behind** (both routes keep working): FCM push → Sentry webhook (keep forwarder) → webhook mitigation (keep Railway) → connections panel → `/connect` polish (connect via the API on camera). **Never cut:** contracts + stubs, J-R1 forwarder, J-R2, J-R3, J-R4 pause/cancel, N-R1, N-R3 PR card. If the production route isn't stable by H21, set `PRODUCTION_CONNECT_ENABLED=0` and record the simulation route; nothing is lost.

---

## 6. After the hackathon (say it in the README, don't build it now)
- A GitHub App instead of tokens (one-click install, org-wide).
- Node/TypeScript and Go repos (per-language sandbox images).
- Datadog, CloudWatch and OpenTelemetry receivers; Kubernetes rollback adapter.
- Per-tenant isolation (data, keys) to replace the shared demo world.
- Modbus controller gateways (Dixell/Carel/Eliwell) for commercial cold rooms.

---

## 7. Risks

| Risk | Owner | Mitigation |
|---|---|---|
| Their deps won't install in the sandbox | James | 5-min cap → draft PR with diagnosis; proof app pins deps |
| Flaky existing tests | James | Baseline first; only *new* failures count |
| Model edits the wrong file | James | Frames → file mapping first; max 3 files; full diff in the PR |
| Prompt injection in logs | James | Fixed action allowlist; PR review; no secrets in the sandbox |
| Token leak | James | Hashed keys, masked tokens, file mode 600, rotate button (John's panel) |
| Device offline / unsafe command | John | 2-min expiry, safety rules before queueing, refuse while paused |
| Phone killed by the OS | John | Foreground service; FCM stretch; web shows everything |
| Merge conflict between the two | both | §3.2 ownership + the single H0 shared commit + checkpoint merges of own branch only |
| Production route breaks the simulation route | both | Frozen file list (§3.2), `environment.mode` switch (§3.3), `smoke_demo.sh` in every check |

---

## 8. Log (fill in while building)
- Contract changes (date · who · what · both agreed): ___
- J-R1 first real log from a remote machine: ___
- J-R3 first PR on a non-demo repo: ___ (link)
- J-R4 first real rollback: ___
- N-R1/N-R2 first device ack: ___
- T-R1 clean runs: ___ / 2

---

## 9. Agent instructions (James and John are both Meta Muse agents running side by side)

They can't talk to each other or to a human while working. They coordinate **only through git** (`origin/main`, one tag, their status files) and this roadmap. §9.0 applies to both; §9.1 and §9.2 are the prompts to paste.

### 9.0 Shared operating rules (both agents)

**Workspace isolation (never share a working folder):**

| | James | John |
|---|---|---|
| Worktree | `../telemetry-agent-james` | `../telemetry-agent-john` |
| Branch | `prod/james` | `prod/john` |
| API port | 8101 | 8201 |
| Shop / web port | 8102 (shop) | 3201 (web dev server) |
| Data dir | `TA_DATA_DIR=/tmp/ta-james` | `TA_DATA_DIR=/tmp/ta-john` |
| Status file | `status/james.md` | `status/john.md` |

- Create the worktree from the main checkout: `git fetch origin && git worktree add ../telemetry-agent-<name> -b prod/<name> origin/main`.
- Python: `../telemetry-agent/venv/bin/python` (or your own venv from `requirements.txt`). Node: `npm install` inside the worktree once.
- **Never** use ports 8001, 8002 or 3000 (Akingbade's live demo) or the other agent's ports. Never stop processes you didn't start.
- Secrets: load with `set -a; . ../telemetry-agent/.env; set +a`. Never print, log, echo, commit or paste a secret value. Never write to `.env`.

**Merge procedure (each checkpoint; your own branch only):**
```bash
git fetch origin
git rebase origin/main            # conflict in a file you don't own → git rebase --abort, write it under BLOCKED in your status file, keep working
./scripts/check.sh                # must exit 0 (James's first commit creates it)
git push --force-with-lease origin HEAD:prod/<name>
git push origin HEAD:main         # fast-forward only; if rejected, start again from git fetch
```
- Never `--force` to `main`. Never delete or rewrite anything you didn't create.
- Commits: keep the repo's configured git identity (don't change `git config`); **no `Co-authored-by` or AI trailers**; message prefixed with the block id, e.g. `J-R1: ingest logs endpoint + forwarder`.

**Status file (`status/<name>.md`, yours only; update and commit at every checkpoint):**
```markdown
# <Name> status
Current block: …
Done: J-R0 (sha), J-R1 (sha) …
Decisions (ambiguities I resolved): …
Contract changes requested: …   (never change §3.4 alone; write it here and keep using the current contract)
NEEDS FROM AKINGBADE: …          (credentials, repo creation, Railway, hardware, manual checks)
BLOCKED: …
```

**Working style:**
- Work autonomously to the end of your list. Don't stop to ask; when something is ambiguous, choose what best fits this roadmap (§2 safety first, then §3 rules), write it under *Decisions*, and continue.
- Test-first for every acceptance case in §4: each one becomes an automated test where possible. Manual-only checks go under NEEDS.
- Mock every external service in tests (GitHub, Railway, Sentry, Modal) with `httpx.MockTransport` or `unittest.mock`. Real calls only in explicit manual verification steps.
- Real GitHub writes are limited to **`maximuskay2/telemetryAgent-demo`** (the only repo the current token can write). Close any PR you open while testing, unless it's a deliberate proof PR (note its link in §8).
- No Railway deploys or setting changes, no new repos, no package publishing. Prepare them and list them under NEEDS.
- Don't edit frozen files (§3.2). Don't run load against the live shop.
- **Done** = every one of your §4 acceptance tests passes, `check.sh` is green on `main`, your status file is complete with the NEEDS list, and your docs are written.

### 9.1 Prompt for James (Backend)

```text
You are James, an autonomous backend engineer (Meta Muse) working in the TelemetryAgent repo at
/Users/maximusinfotechservices/Documents/META/telemetry-agent. Another agent, John, builds the app,
hardware and web side AT THE SAME TIME in a separate worktree. You cannot talk to John or to a human
while working; you coordinate only through git and the files named below.

YOUR JOB: implement every James item in production-roadmap.md — J-R0, J-R1, J-R2, J-R3, J-R4, J-R5 and the
backend half of T-R1 — until all of their acceptance cases pass, without breaking the simulation route.

READ FIRST, IN FULL: production-roadmap.md (especially §2, §3, §4 "James", §9.0).
Then skim: apps/api/main.py (the /api/logs, /api/incidents/candidate, /api/actions/*, /api/run routes),
core/actions/github_pr.py, core/actions/auto_action.py, core/verify/sandbox.py, core/verify/local_runner.py,
core/agent/loop.py, core/watch/log_watcher.py, core/watch/rules.py, core/setup/gate.py,
core/schemas/{events,profile,remediation}.py, tests/test_api.py.

SET UP (§9.0): worktree ../telemetry-agent-james on branch prod/james from origin/main; API port 8101,
shop port 8102, TA_DATA_DIR=/tmp/ta-james. Never touch ports 8001/8002/3000 or 82xx.

STEP 1 — CONTRACTS (do this before anything else; John builds against it):
  a. core/schemas/production.py with every model in roadmap §3.4.
  b. core/schemas/events.py: add kinds connection_status, option_status, actions_paused, pr_opened.
  c. apps/api/routes/__init__.py, apps/api/routes/production.py, apps/api/routes/devices.py with STUB handlers
     that return the §3.4 fixture JSON exactly (including GET /api/connections/enabled).
  d. Stub hand-off functions: core/connections/__init__.py (is_production), core/connections/auth.py
     (system_for_key — accepts the fixture key "ta_live_fixture"), core/actions/mitigate.py
     (software_options -> [], execute, is_paused -> False).
  e. Two include_router lines at the END of apps/api/main.py. After this commit no one edits main.py again.
  f. scripts/check.sh and scripts/smoke_demo.sh exactly as roadmap §3.5 (smoke = simulation route).
  g. status/james.md (template in §9.0).
  Run ./scripts/check.sh (must pass), commit "J-R0: production contracts + stubs", merge to main with the §9.0
  procedure, then: git tag contracts-in && git push origin contracts-in   ← this is John's go signal.
  After this tag, apps/api/routes/devices.py and core/devices/* belong to John. Never edit them again.

STEP 2 — BUILD IN ORDER, merging to main after each block (§9.0 procedure) and updating status/james.md:
  J-R0  real connections store (data dir under TA_DATA_DIR, file mode 600), hashed ta_live_ keys shown once,
        system_for_key, create/list/test/delete; keep accepting "ta_live_fixture" only when TA_FIXTURE_KEYS=1.
  J-R1  POST /api/ingest/logs + POST /api/ingest/sentry/{key}; agent/ta_forward.py (stdlib only, buffers through
        API outages, served at GET /forwarder.py); Python tracebacks become ONE candidate with parsed frames;
        connection_status events; candidates go to the existing gate with the real system_id.
  J-R2  github connection (fine-grained token; test = repo read + pull_requests permission + base branch);
        github_pr.py accepts repo/token from a connection; demo systems still use GITHUB_DEMO_REPO.
  J-R3  THE CORE: core/repo_fix/* + core/verify/repo_sandbox.py. Frames → repo files (suffix match on the tree)
        → tarball at commit → sandbox (Modal; if Modal creds are missing or fail, use the existing Docker runner
        pattern in core/verify/local_runner.py; otherwise fail with a clear reason) → install deps, baseline pytest
        → generated reproduce test MUST FAIL on original → patch ≤ 3 files → new test passes AND no new suite
        failures → PR on the connected repo, one open PR per fingerprint (comment otherwise), pr_url + suite on
        the run, pr_opened event. No tests / too big → draft PR with diagnosis only. Production path only when
        is_production(profile); the demo path (target="inventory") is untouched.
        Manual proof: a production-mode system connected to maximuskay2/telemetryAgent-demo with a real
        traceback → a real PR; record the link in roadmap §8.
  J-R4  core/actions/mitigate.py: allowlist rollback + restart ONLY (Railway GraphQL adapter + HMAC-SHA256 webhook
        adapter), through the existing auto_action 20 s window; /api/actions/pause GET/POST + actions_paused;
        1 mitigation per system per 10 min; none while learning; real software_options(run) returning
        open_pr / rollback / restart options in the §3.4 Option shape. Unit test: stop/delete/scale-0 impossible.
        Railway calls are mocked in tests; a real rollback only if a Railway token is present — otherwise NEEDS.
  J-R5  examples/proof-app/ (FastAPI, real bug, ~20 pytest tests, requirements.txt, Railway start command,
        forwarder line); docs/production-backend.md; docs/proof-run.md (backend steps for the human run).
        LAST: add two link lines to docs/DOCUMENTATION.md (production-backend.md, production-devices.md).

ALWAYS:
- Only edit files James owns in roadmap §3.2. Frozen: apps/api/main.py after Step 1, core/agent/loop.py,
  core/setup/*, core/watch/*, core/simulate/*, demo/**, every existing web page, everything John owns.
- Additive API only; never change an existing response shape. Never change §3.4 alone — request it in your status.
- Every acceptance case in §4 James blocks → a test in tests/test_prod_*.py. All 485 existing tests stay green.
- Secrets hashed/masked, never returned by the API, never printed or committed.
- Don't stop to ask. Decide by the roadmap, log the decision in status/james.md, continue.

FINISH when: all J-R* acceptance tests pass, check.sh is green on main, status/james.md lists every commit, every
decision and a complete "NEEDS FROM AKINGBADE" list (e.g. create telemetryAgent-proof-app repo, grant token access,
RAILWAY_TOKEN + service id, Sentry webhook setup), and docs/production-backend.md + docs/proof-run.md exist.
```

### 9.2 Prompt for John (App · Hardware · Web)

```text
You are John, an autonomous app, hardware and web engineer (Meta Muse) working in the TelemetryAgent repo at
/Users/maximusinfotechservices/Documents/META/telemetry-agent. Another agent, James, builds the backend AT THE
SAME TIME in a separate worktree. You cannot talk to James or to a human while working; you coordinate only
through git and the files named below.

YOUR JOB: implement every John item in production-roadmap.md — N-R0, N-R1, N-R2, N-R3, N-R4 and the
devices/app half of T-R1 — until all of their acceptance cases pass, without breaking the simulation route.

READ FIRST, IN FULL: production-roadmap.md (especially §2, §3, §4 "John", §9.0).
Then skim: apps/mobile/lib/** (services/api.dart, socket.dart, alarm.dart, foreground.dart, screens/*, theme.dart,
widgets/widgets.dart, models/*), apps/web/app/welcome/*, apps/web/app/lib/{api,setupApi}.ts,
apps/web/app/ui/*, core/simulate/fridge_stream.py, core/schemas/remediation.py (Runbook),
the appliance safety rules in core/agent/loop.py (read only), hardware/wokwi/*.

SET UP (§9.0): worktree ../telemetry-agent-john on branch prod/john from origin/main; API port 8201,
web dev server port 3201 (NEXT_PUBLIC_API_URL=http://localhost:8201), TA_DATA_DIR=/tmp/ta-john.
Never touch ports 8001/8002/3000 or 81xx.

STEP 1 — START NOW (needs nothing from James):
  N-R0  cd apps/mobile && flutter pub get && flutter analyze && flutter test, then flutter build apk --debug
        (flutter run if an emulator is available). The Android splash fix is already in main (21246cd);
        only fix something if a step fails. Create status/john.md (template in §9.0).
        Scaffold the new Flutter cards with the existing lib/theme.dart and lib/widgets/widgets.dart
        (classic mint-green — no new palette).
  While doing that, check for James's go signal every few minutes:
        git fetch origin --tags && git tag -l contracts-in
  When it exists: git rebase origin/main, then mirror roadmap §3.4 into apps/mobile/lib/models/ and
  apps/web/app/types/production.ts, with unit tests that parse the §3.4 fixtures.
  From now on apps/api/routes/devices.py and core/devices/* are yours. Build against James's STUBS; never wait
  for his real logic — show "PR pending" / "No mitigation" / "not connected yet" states until it lands.

STEP 2 — BUILD IN ORDER, merging to main after each block (§9.0 procedure) and updating status/john.md:
  N-R1  core/devices/options.py: options from the stored appliance run's runbook + profile (never edit
        core/agent/loop.py). remote = Start defrost · Lower setpoint 1 °C (only within profile limits) ·
        Power-cycle compressor (only after restart_delay_s) · Switch to backup; manual = close door / check seal /
        move stock; dispatch = call/WhatsApp technician with the work order. Every option passes the existing
        safety rules; unsafe ones get safety.ok=false and can't be executed.
        apps/api/routes/devices.py: GET /api/incidents/{run_id}/options (software options come from
        core.actions.mitigate.software_options), POST …/options/{id}/execute (X-Mobile-Token), device command queue
        GET /api/devices/{id}/commands + POST …/ack (Bearer key via core.connections.auth.system_for_key),
        2-minute expiry, refuse while mitigate.is_paused(), option_status events, POST /api/devices/{id}/readings.
        Leave /api/telemetry/appliance untouched.
  N-R2  hardware/wokwi/sketch.ino: readings with the device key, poll commands every 5 s, relay/LED, ack.
        hardware/sim_device.py: stdlib-only software ESP32 with the same protocol (--api, --device, --key,
        --fault door_open), used in an automated end-to-end test against a local API on 8201.
  N-R3  Flutter: "Software · PR ready" card (summary, proof "fails → passes, suite green", Open PR via url_launcher,
        Roll back now / Cancel with the countdown), "Hardware · Choose a fix" card (live option_status), quiet
        "Watching", Pause all actions toggle + "Paused" banner (actions_paused). Widget tests for each card from
        fixtures. Stretch only if everything else is green: FCM push (list Firebase setup under NEEDS).
  N-R4  Web: "Connect your production" button next to the CTA in apps/web/app/welcome/DemoCta.tsx, shown only when
        GET /api/connections/enabled returns enabled:true. "Try the live demo" stays first and unchanged; change
        nothing else in welcome/. New apps/web/app/connect/: name/type → logs (forwarder one-liner with the key
        shown once, Sentry URL, curl; live "✓ first log" from connection_status) → repo + Test → hosting
        (Railway or webhook + secret) + Test ping → device key + firmware snippet + "✓ first reading" → teach
        normal (CALL setupApi.ts functions, don't edit that file) → permissions + the full §2 uptime promise with
        an "I understand" tick → pair phone (existing QR) → Start watching. Creates the system with
        environment: {"mode": "production"}. Connections panel at /connect?system=…: last seen, test, rotate key,
        Disconnect. npm run build -w apps/web must pass.
        Docs: docs/production-devices.md; devices/app half of docs/proof-run.md is written in
        docs/production-devices.md under "Proof run" (James owns docs/proof-run.md).
  After James's status shows J-R3/J-R4 done (read status/james.md on main): rebase, switch the cards from stub
  data to real pr_url / suite / software options, and re-run your end-to-end test with sim_device.py.

ALWAYS:
- Only edit files John owns in roadmap §3.2. Frozen: apps/api/main.py, core/agent/loop.py, core/setup/*,
  core/watch/*, core/simulate/*, demo/**, apps/web/app/{page.tsx,mission,setup,shop,start,classic,incidents}/**,
  apps/web/app/lib/setupApi.ts, everything James owns.
- The simulation route (/welcome → /start → /start/setup → Mission Control) must look and work exactly as now.
- Additive API only. Never change §3.4 alone — request it in your status and keep using the current contract.
- No secret in NEXT_PUBLIC_* or the app bundle; the phone token comes from the pairing QR only.
- Every acceptance case in §4 John blocks → an automated test (Python, flutter test, or web build check) where
  possible; manual-only checks go under NEEDS.
- Don't stop to ask. Decide by the roadmap, log the decision in status/john.md, continue.

FINISH when: all N-R* acceptance tests pass, check.sh is green on main, flutter analyze/test and the web build
pass, status/john.md lists every commit, every decision and a complete "NEEDS FROM AKINGBADE" list (e.g. run the
app on a phone, flash/run the Wokwi sketch, Firebase for push), and docs/production-devices.md exists.
```

### 9.3 Akingbade's checklist while they run
1. Commit + push this roadmap first, so both agents start from the same `main`.
2. Start **James first**, then John right after. John starts on N-R0 and waits for the `contracts-in` tag by himself.
3. Watch progress: `git log origin/main --oneline`, `status/james.md` and `status/john.md` on `main`.
4. Act on each **NEEDS FROM AKINGBADE** list: proof-app repo, token access, `RAILWAY_TOKEN`, phone and Wokwi checks.
5. At the end: run `docs/proof-run.md` yourself. If the production route isn't stable, set `PRODUCTION_CONNECT_ENABLED=0` and record the simulation route.
