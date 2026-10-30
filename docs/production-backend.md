# TelemetryAgent production backend (James)

How the 🔵 production route works behind `/connect`: a customer connects
their server, repo, hosting and devices, and TelemetryAgent catches real
errors, proves fixes on their real code, opens PRs on their repo, and
offers safe mitigations — without ever touching the 🟢 simulation route.

Contract source of truth: [`production-roadmap.md`](../production-roadmap.md)
§3.4 (frozen). This doc explains the backend half; devices/app/web are in
[`production-devices.md`](production-devices.md).

## Routes vs systems

`SystemProfile.environment["mode"] == "production"` (set only by
`/connect`) marks a production system; anything else is demo.
`core.connections.is_production(profile)` is the one switch, used only
inside the new routes, so demo code never sees it.

`PRODUCTION_CONNECT_ENABLED=0` hides the `/connect` door and disables
`/api/connections` (emergency switch; default `1`). `CONNECT_ACCESS_CODE`,
when set, makes every connection route require the `X-Connect-Code`
header (the instance has no accounts).

## Connections + keys (`core/connections/`, J-R0)

- `POST /api/connections` stores one JSON file per connection at
  `data/connections/<id>.json`, mode `0600`.
- `logs`/`sentry`/`device` kinds get a generated `ta_live_*` key: shown
  **once** on create, stored only as SHA-256. Third-party secrets
  (`github`/`railway` tokens, webhook signing secret) must stay usable
  for outbound calls, so they rest recoverable in the 600 file and are
  never returned — only `secret_hint` (`****` + last 4) leaves the API.
- `system_for_key(key, kind)` resolves keys; the `ta_live_fixture` key
  works only with `TA_FIXTURE_KEYS=1` (tests, John's stub phase).
- Delete removes the file; the key fails immediately (nothing cached).

## Error intake (`core/ingest/`, `agent/ta_forward.py`, J-R1)

- `agent/ta_forward.py` (stdlib only, served at `GET /forwarder.py`) tails
  files from the end, forwards WARNING+ plus full tracebacks, batches,
  and buffers in memory (cap 20k lines) with 1→60 s backoff while the
  API is down. Rotation/truncation-safe. A 401 batch is reported and
  dropped (a bad key never recovers).
- `POST /api/ingest/logs` (Bearer key) reassembles multi-line tracebacks
  **server-side** (per system+service buffer, 30 s stale flush, 200-line
  cap) so cross-batch splits still become ONE event with parsed frames.
- `POST /api/ingest/sentry/{key}` renders Sentry issue webhooks as
  traceback text through the same path.
- Each entry runs the **existing** watcher rules + gate with the real
  `system_id`. Production candidates are evaluated in-process (an `act`
  is recorded; log lines carry no metrics so it cannot fire yet — J-R3
  wires production acts); anything else delegates to the existing
  candidate endpoint for identical demo behaviour.
- First delivery flips the connection `waiting` → `ok` (`mark_seen`) and
  emits `connection_status` (real connections only, transition only).

## GitHub repo (`core/connections/github.py`, J-R2)

- `POST /api/connections/{id}/test` on a `github` connection checks the
  repo is readable, the base branch exists, and the token can write —
  the write probe creates + immediately deletes a throwaway
  `ta-probe-*` ref, leaving no trace. Read-only →
  `ok:false` "can read, cannot open PRs".
- `connection_repo(system_id)` resolves `{repo, base, token}` for the
  fix pipeline. `open_pr`/`open_fix_pr` already took repo/token, so no
  demo-path change was needed (`GITHUB_DEMO_REPO` still serves demos).

## Repo-fix pipeline (`core/repo_fix/`, `core/verify/repo_sandbox.py`, J-R3)

Auto-triggers from ingest for armed production systems with a github
connection and a parseable traceback (rule-agnostic: a traceback that
mentions "deadlock" still triggers). No new endpoint — tests call
`run_repo_fix` directly, keeping §3.4 untouched.

1. **Locate** (`locate.py`): tree at the commit via git-trees API; frame
   files match by suffix; top 1–3 files ±40 lines. No frame match →
   keyword-ranked files, model picks ≤ 5.
2. **Snapshot** (`snapshot.py`): tarball at the failing commit (else base
   HEAD); download aborts past 50 MB; filtering drops `.git`,
   `node_modules`, caches, > 2 MB files and binaries, strips the top
   dir, refuses unsafe entries.
3. **Sandbox** (`repo_sandbox.py`): Modal first (Python 3.11 + pytest;
   snapshot arrives as chunked base64 execs — **no customer secrets go
   inside, ever**); ANY Modal failure falls back to Docker (host
   extract + throwaway containers, network only for pip); neither →
   clear error. `TA_VERIFY=local` forces Docker.
4. **Install + baseline**: `pip install -r requirements.txt` (5-min cap)
   or `-e .`; baseline `pytest -q` outcomes recorded.
5. **Reproduce**: model-written `tests/test_telemetry_agent_<fp>.py` must
   FAIL on the original (3 attempts, output fed back, Muse Wonder on
   the last — Baseten Spark Open before that).
6. **Patch**: `files: [{path, content}]`, max 3 known files (kept first
   3 + note when the model proposes more).
7. **Prove**: repro passes AND no baseline-passing test newly fails.
8. **PR**: one open PR per fingerprint via the deterministic branch
   `telemetry-agent/fix-<fp12>`; an existing open PR gets a "seen
   again" comment instead (throttled 1/hour/fingerprint). Body carries
   diagnosis, fail→pass evidence, suite summary. Label
   `telemetry-agent`. `pr_opened` event; `pr_url`/`repo`/`suite` land on
   the run result (additive `ExecutionResult` fields, §3.4).
9. **Draft fallback** (`NO_ACTION` + `pr_url`): locate fails, snapshot
   > 50 MB, pip fails, no tests, repro won't fail, patch won't prove →
   draft PR with `TELEMETRY_AGENT_DIAGNOSIS.md` (+ repro test when one
   failed). Only "no sandbox" is a hard `FAIL`.

Runs are stored in `software_runs` with `target: "repo"` and broadcast
the usual `diagnose/generate/verify/done` steps, so Mission Control and
the phone show progress with no new UI code.

Live proof (Oct 29): PR #9 on `maximuskay2/telemetryAgent-demo`
(one-line `sorted()` lock-order fix + repro test; fail→pass in Docker;
suite 5 passed / 0 new failures). Same error ×5 → 1 PR + 1 comment.
Draft path verified live (PR #10, closed after).

## Mitigations + pause (`core/actions/mitigate.py`, J-R4)

- **Allowlist: `rollback`, `restart` ONLY** — checked first, so `stop`,
  `delete`, `scale-0` etc. are impossible even if suggested.
- Gates: allowlist → **paused** → learning → rate (**1/system/10 min**,
  in-memory atomic + `data/mitigations.json` for restarts; only DONE
  runs consume budget) → policy (`allowed_actions`, proposals only —
  explicit human taps bypass it) → hosting connection. Railway first,
  else webhook.
- **Railway adapter**: redeploy newest SUCCESS deployment / restart
  latest via GraphQL (`deploymentRedeploy`, `deploymentRestart`;
  shapes from public docs — live verification still needs a
  `RAILWAY_TOKEN`, see NEEDS below).
- **Webhook adapter**: `POST {action, system_id, run_id, ts}` with
  `X-Telemetry-Signature: sha256=<HMAC-SHA256(secret, raw body)>`.
  `ping` exists for the connection test only (never executes).
- **Windows**: server-proposed mitigations open a 20 s `PendingAction`
  window (mitigate-owned store — main's apply dispatch is frozen —
  reusing `action_pending/tick/resolved` events). Proposals are
  **approve-to-run** (`auto_apply=False`): they expire unless a human
  approves, because no error-rate feed exists yet to justify automatic
  action. A repo-run start proposes rollback (policy-gated, silent
  skip) — this is what rings the phone in the proof run.
- **Pause**: `GET/POST /api/actions/pause` (`X-Mobile-Token`), persisted
  in `data/pause.json`, broadcasts `actions_paused`. Paused → nothing
  runs, due windows expire, John's command queue refuses.
- **Audit**: every proposal/decision/execution appends to
  `data/mitigations.json` (cap 500) with approver + result; the run's
  `mitigation` summary (§3.4) mirrors the latest execution.
- `software_options(run)` returns `open_pr` (when `pr_url` exists) plus
  always-listed `rollback`/`restart` with safety reasons; ids are
  `opt_<action>` (`action_for_option_id` parses them for the router).

Live-checked: signed webhook rollback over real HTTP (HMAC verified),
pause gate, rate limit, options safety.

## Key files

| Area | Files |
|---|---|
| Schemas | `core/schemas/production.py`, additive `repo/suite/mitigation` on `ExecutionResult` |
| Routes | `apps/api/routes/production.py` (devices.py is John's after H0) |
| Connections | `core/connections/{store,auth,github}.py` |
| Ingest | `core/ingest/{traceback,pipeline}.py`, `agent/ta_forward.py` |
| Fix pipeline | `core/repo_fix/{run,locate,snapshot,generate}.py`, `core/verify/repo_sandbox.py` |
| Mitigations | `core/actions/mitigate.py`, `github_pr.py` additive (labels/draft/lookup/comment) |
| Checks | `scripts/check.sh`, `scripts/smoke_demo.sh` |
| Tests | `tests/test_prod_*.py` (all externals mocked; Docker + webhook live) |
| Proof app | `examples/proof-app/` (own repo when created) |

## Environment

| Var | Meaning |
|---|---|
| `PRODUCTION_CONNECT_ENABLED` | `0` hides the `/connect` door (default `1`) |
| `CONNECT_ACCESS_CODE` | Access code for every connection route (empty = no code) |
| `TA_FIXTURE_KEYS` | `1` accepts `ta_live_fixture` (tests/stub phase) |
| `TA_VERIFY` | `local` forces the Docker verifier |
| `TA_SANDBOX_IMAGE` | Docker image (default `telemetry-agent-sandbox`) |
| `DOCKER_BIN` | Explicit docker CLI path |
| `MOBILE_API_TOKEN` | `X-Mobile-Token` for pause/execute (empty = open, dev) |
| `MODEL_API_KEY` / `BASETEN_API_KEY` | Diagnose (Spark) / generate (Spark Open, Wonder last) |
| `GITHUB_TOKEN` | Demo-repo writes only |

## NEEDS (human)

- Create public repo `maximuskay2/telemetryAgent-proof-app` from
  `examples/proof-app/` and deploy it on Railway (then the T-R1 proof
  run in [`proof-run.md`](proof-run.md)).
- `RAILWAY_TOKEN` + staging service id to live-verify the Railway
  rollback/restart mutations (mocked + doc-researched so far).
