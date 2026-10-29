# 🔌 TelemetryAgent: Real Production Roadmap (Connect → Detect → Fix → Notify → Act, without downtime)

**Goal (24 hours, two developers in parallel):** a real customer, not our simulation, can:
1. **connect** their production server, their GitHub repo and (optionally) their hosting platform or a cold-chain device;
2. have TelemetryAgent **catch a real error**, write and **prove a fix on their real code**, and open a **PR on their repo**;
3. get the incident and the **fix options on our Flutter app**: software (PR ready, roll back, restart) and hardware (remote defrost, setpoint, backup unit, technician);
4. be confident **nothing in production is shut down or changed without them**. Every action is reversible, goes through the gate and the cancel window, and has a kill switch.

**Team:**
- **James — Backend.** Connections, ingest, the real fix pipeline, safe production actions.
- **John — App, Hardware, Web.** Flutter action center, device options + firmware, the `/connect` wizard.

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
| Phone app | ✅ WebSocket, full-screen alarm, local notifications, foreground service, Approve/Disapprove with `X-Mobile-Token`, QR pairing | No fix options, no PR actions, no "pause all"; Android build currently fails (`launch_background.xml`) |

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
- **R-5 Branches + checkpoints.** James works on `prod/james`, John on `prod/john`. At each checkpoint (§5: H2, H6, H10, H14, H18, H21), each person rebases on `main`, runs **`./scripts/check.sh`** (§3.5), and merges **only their own branch** if it's green. Red check = don't merge; fix on the branch.
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
| Firmware | — | `hardware/wokwi/*` |
| Tests | `tests/test_prod_*.py` | `tests/test_devices_*.py`, `apps/mobile/test/*` |
| Scripts | `scripts/check.sh`, `scripts/smoke_demo.sh` (H0) | — |
| Docs | `docs/DOCUMENTATION.md` "Connect production (backend)" section | same file, "Phone & devices" section (separate headings, no overlap) |

**Frozen for both (the simulation route):** `apps/api/main.py` (after H0), `core/agent/loop.py`, `core/setup/*`, `core/watch/*`, `core/simulate/*`, `demo/**`, `apps/web/app/{page.tsx,mission,setup,shop,start,classic,incidents}/**`, `apps/web/app/lib/setupApi.ts`. If a real bug forces a change there, it goes in its own small commit with both people told.

### 3.3 Simulation vs production: how the code chooses
- Every system has `environment.mode`: `"demo"` (default; all existing systems) or `"production"` (created by `/connect`).
- **Demo systems keep the exact current path:** `target="inventory"`, `GITHUB_DEMO_REPO`, hot-swap deploy, stub alert, and the sim fridge.
- **Production systems** go through James's `core/repo_fix` pipeline and John's options/commands. The switch is a single check inside James's new code (`if system.mode == "production"`), reached from the new ingest routes, so the demo code never sees it.
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

---

## 4. Build blocks

### 👷 James: Backend

**J-R0 · Contracts, stubs, connections, keys (H0–H2)**
- H0 shared commit (R-3): `core/schemas/production.py`, event kinds, `apps/api/routes/{production,devices}.py` with **stub** handlers returning the §3.4 fixtures, two `include_router` lines, `scripts/check.sh`, `scripts/smoke_demo.sh`. **Tell John "contracts are in"** (he starts immediately).
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
- New public repo `maximuskay2/telemetryAgent-proof-app`: small FastAPI service with a real bug (empty-cart division by zero or the deadlock) + ~20 pytest tests, deployed on Railway, forwarder beside it.
- `DOCUMENTATION.md` → "Connect production (backend)".

### 👷 John: App · Hardware · Web

**N-R0 · Unblock the app (H0–H2)**
- Fix the Android build: `drawable-v21/launch_background.xml` uses `#09090B` as `android:drawable`; move it to a `<color>` resource (`values/colors.xml`) and reference `@color/…`. Same for `drawable/launch_background.xml`.
- Mobile models + `types/production.ts` from §3.4 contracts.
- **Accept:** `flutter run` builds on the emulator; `flutter analyze` clean.

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
- **Accept:** Wokwi (or a real ESP32) shows the relay toggle within 10 s of tapping the option.

**N-R3 · Flutter action center (H10–H16)**
- Cards: **Software · PR ready** (summary, proof "fails → passes, suite green", **Open PR**, mitigation countdown **Roll back now / Cancel**); **Hardware · Choose a fix** (options with live `option_status`); **Watching** (quiet channel).
- **Pause all actions** toggle (home screen); "Paused" banner from `actions_paused`.
- Pairing QR `{api, token}` (existing flow). Keep the foreground service; **stretch:** FCM push.
- Until James's R3/R4 land, cards render from the stub fixtures and show "PR pending" / "No mitigation" (R-6).
- **Accept:** phone locked → real incident rings within 10 s; Open PR opens the right page; Cancel stops the rollback; hardware option toggles the device; Pause shows on web and phone within 2 s.

**N-R4 · Web `/connect` wizard + second door (H16–H21)**
- `/welcome`: second button **Connect your production** → `/connect` (hidden when `PRODUCTION_CONNECT_ENABLED=0`). "Try the live demo" stays first and unchanged.
- `/connect` steps:
  1. name + type;
  2. logs (forwarder one-liner with the key / Sentry URL / curl) with a live "waiting → ✓ first log" (`connection_status`);
  3. repo + **Test**;
  4. hosting (Railway or webhook + secret) + **Send test ping**;
  5. device key + firmware snippet + "✓ first reading";
  6. teach normal (reuse `setupApi.ts` calls; don't edit the file);
  7. permissions + the full uptime promise + "I understand";
  8. pair phone → **Start watching**.
  It creates the system with `environment.mode="production"`.
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
| H0–H1 | Contracts + stubs + `check.sh` (shared commit) | N-R0 Android build fix | James: "contracts are in" |
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
