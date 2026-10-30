# TelemetryAgent usage guide

Three jobs, one doc:

- **A. Use it locally** — run the demo and kick the tires.
- **B. Run it in production** — deploy the API + dashboard for real.
- **C. Connect your production** — the customer guide: your server, repo,
  hosting and devices watched by TelemetryAgent.

Notation: `YOUR-API` is wherever the API runs (`http://localhost:8001`
locally, your Railway URL in production).

---

## A. Use it locally

### A.1 Prerequisites

- Python 3.9+, Node.js 20.9+, npm.
- Docker Desktop (only if you verify without Modal — see A.4).
- Flutter (only for the mobile app — see A.6).
- Model keys for the agent loop: `MODEL_API_KEY` (Meta Model API, Spark
  diagnosis + Wonder escalation) and `BASETEN_API_KEY` (Spark Open
  generation). Without them the dashboard and simulators run, but
  diagnose/generate calls fail.

### A.2 Install

```bash
git clone https://github.com/maximuskay2/telemetryAgent.git
cd telemetryAgent
python -m venv venv && venv/bin/pip install -r requirements.txt
npm install                       # web workspace deps
cp .env.example .env              # then fill in the keys (see table below)
```

Key environment variables (full list with comments in `.env.example`):

| Variable | Purpose |
| --- | --- |
| `MODEL_API_KEY` | Meta Model API (Muse Spark + Muse Wonder) |
| `BASETEN_API_KEY` | Muse Spark Open on Baseten (primary generation) |
| `FIREWORKS_API_KEY`, `FIREWORKS_PATCH_MODEL` | Optional backup generation |
| `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET` | Modal Sandboxes (or `modal setup` once) |
| `TA_VERIFY=local` | Force Docker verification instead of Modal |
| `TA_SANDBOX_IMAGE`, `DOCKER_BIN` | Docker image name / CLI path |
| `GITHUB_TOKEN` | Opening PRs (demo repo + connected customer repos) |
| `GITHUB_DEMO_REPO`, `GITHUB_BASE_BRANCH` | Demo PR target (`owner/repo`, `main`) |
| `MOBILE_API_TOKEN` | `X-Mobile-Token` for phone approve/pause (empty = open, dev only) |
| `AUTO_ACTION_SECONDS`, `AUTO_ACTION_ENABLED` | Veto window length (default 20 s) + master switch |
| `PRODUCTION_CONNECT_ENABLED` | `0` switches `/connect` off and refuses every connection route (default `1`) |
| `CONNECT_ACCESS_CODE` | If set, `/connect` and every connection route need this code (`X-Connect-Code` header) |
| `TA_FIXTURE_KEYS` | `1` accepts `ta_live_fixture` (automated tests only) |
| `RAILWAY_TOKEN` | Railway rollback/restart adapter |
| `TA_DATA_DIR` | Data root (default `./data`): profiles, connections, audit, pause |
| `SHOP_PORT` | Shop simulator port (default `8002`) |
| `CORS_ORIGIN_REGEX` | Extra allowed web origins |

### A.3 Run the services

One command starts everything (API with the fridge stream, shop, log
watcher, dashboard):

```bash
./scripts/demo.sh                 # API_HOST=0.0.0.0 ./scripts/demo.sh for a phone
```

Or piece by piece:

```bash
# terminal 1 — API on :8001
venv/bin/python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8001

# terminal 2 — shop simulator on :8002
venv/bin/python demo/shop/app.py

# terminal 3 — log watcher (without it, shop crashes never start a run)
venv/bin/python -m core.watch.log_watcher --file demo/shop/logs/shop.log \
  --api http://localhost:8001 --target inventory

# terminal 4 — dashboard on :3000
NEXT_PUBLIC_API_URL=http://localhost:8001 npm run dev --workspace apps/web
```

Health: `curl localhost:8001/api/health`. If the dashboard shows
"disconnected", the API isn't up or the ports mismatch (see
`docs/DOCUMENTATION.md` §15 troubleshooting).

To try the production route locally against a real app, use
`examples/proof-app/` (a small shop with a real bug and its tests) and
follow [`docs/proof-run.md`](./proof-run.md).

### A.4 The demo journey (3 minutes)

1. `http://localhost:3000/welcome` — landing, "Try the live demo".
2. `/start` — onboarding; `/start/setup` — guided setup arms the demo
   shop + freezer together.
3. `/` — Mission Control with the first-incident tour: inject a deadlock,
   watch the gate decide (with citations), follow diagnose → patch →
   verify live, get the real PR, then the wrap-up.

Other doors: `/setup` (full wizard: docs → profile → baseline → policy →
arm), `/shop` (simulator console), `/classic` (pre-redesign dashboard).

### A.5 Simulators and faults

- **Shop** (`demo/shop/`, `/shop`): products, retries, deadlocks, load
  controls; deploy/reset at `POST /restart`.
- **Fridge/freezer** (`/api/sim/fridge/*`): temperature/current/vibration
  stream, door, defrost, compressor faults.
- **Software ESP32** (`hardware/sim_device.py`) + Wokwi firmware: speak the
  production device protocol (commands, acks, readings) for hardware demos
  without hardware.

### A.6 Mobile app

```bash
cd apps/mobile && flutter pub get && flutter run
```

On the Pair screen enter the API URL + token from `.env`:

- Android emulator: `http://10.0.2.2:8001` (host loopback).
- Physical phone: your Mac's LAN IP, e.g. `http://192.168.x.x:8001` — and
  start the API with `--host 0.0.0.0` so it listens off-loopback.
- Token: the `MOBILE_API_TOKEN` value (blank when unset).

### A.7 Checks

```bash
./scripts/check.sh   # python suite + simulation smoke + web build + flutter
```

`scripts/smoke_demo.sh` alone spins the API on a spare port with a temp
data dir, arms the demo shop, and runs two live agent runs — the
"simulation route preserved" guarantee. Set `SMOKE_WEB_URL` to include
page checks (never point it at someone's live `:3000`).

---

## B. Run it in production

Reference deployment: two Railway services from this repo (API +
web). `railpack.json` already gives the API start command:

```bash
python -m uvicorn apps.api.main:app --host 0.0.0.0 --port $PORT
```

### B.1 Services

- **API service** (Python): root command above. Set every variable from
  A.2 that applies (model keys, `GITHUB_TOKEN`, `MOBILE_API_TOKEN`,
  `RAILWAY_TOKEN` if you offer hosted mitigations). Set
  `CORS_ORIGIN_REGEX` to allow the web origin.
- **Web service** (Node): `npm install && npm run build -w apps/web`,
  start the Next.js server. `NEXT_PUBLIC_API_URL` is **baked into the
  build** — set it to the API's public URL and redeploy web after any
  change. Deploying with the Railway CLI, upload only the web folder:
  `railway up ./apps/web --path-as-root --service web` (uploading the
  whole repo makes Railway build it as Python).
- **Sandbox backend**: prefer Modal (`MODAL_TOKEN_ID/SECRET`) — no
  Docker daemon needed on the host. Without Modal, verification needs
  Docker on the API host (`TA_VERIFY=local` + the image from
  `./scripts/build-sandbox-image.sh`); most PaaS hosts don't allow that,
  so treat Modal as required in production.

### B.2 Persistence (important)

Everything stateful lives under `TA_DATA_DIR` (default `./data`):
setup profiles, production connections (**tokens**, mode `0600`),
mitigation audit + rate stamps, the pause flag. Railway disks are
ephemeral — **mount a volume and point `TA_DATA_DIR` at it**, or every
redeploy forgets your systems, connections and pause state.

### B.3 Operating notes

- `/api/health` is the uptime probe; `/api/actions/pause` (token) is the
  global kill switch — paused means nothing runs, due windows expire,
  and device queues refuse.
- The forwarder is served by the API itself at
  `GET /forwarder.py`, so customers always fetch the matching version.
- Logs: uvicorn access log + `data/` JSON files. Nothing secret is
  logged (keys shown once on create, hints afterwards).
- Rollback story for the product itself: `PRODUCTION_CONNECT_ENABLED=0`
  hides `/connect` instantly while the simulation route keeps working.

---

## C. Connect your production (customer guide)

You keep your code, your repo, your hosting. TelemetryAgent reads your
errors, proves fixes in a sandbox, and proposes — never pushes.

**Where to do this.** Open `YOUR-WEB/connect` — on the public site,
[web-production-926b3.up.railway.app/connect](https://web-production-926b3.up.railway.app/connect).
TelemetryAgent has no user accounts, so an instance can require an
**access code** (`CONNECT_ACCESS_CODE`) before anyone can create, list,
test or delete connections. The public site does: ask the team for the
code. On your own instance (part A locally, part B on Railway) set your
own code, or leave it empty on a private network. Secrets are never
returned by the API, only hints.

The wizard's steps depend on what you pick in step 1:

- **Software:** System → Logs → Repo → Hosting → Teach → Promise → Pair →
  Start.
- **Appliance:** System → Device → Teach → Promise → Pair → Start.

Repo and Hosting have **Connect + Test** / **Connect + Test ping**;
green means really verified, not just saved, and the connection shows
**ok** in the connections list. Logs and Device have no test button —
they wait for the first log line / reading instead.

Prerequisites: depending on the steps you use — a GitHub token, a
Railway token + service ID or a webhook receiver, and (for cold chain)
an ESP32-class device.

### C.1 Logs — ship us your errors

**Option 1: forwarder (any server, 1 minute).** The wizard prints this
with your key filled in:

```bash
curl -s http://YOUR-API:8001/forwarder.py -o ta_forward.py
python3 ta_forward.py --api http://YOUR-API:8001 --key ta_live_... \
    --file /var/log/myapp.log --service myapp --release v1.2.3 --commit abc123
```

Expectations: plain text logs; WARNING+ lines and full Python
tracebacks are forwarded (tune with `--level`); multi-line tracebacks
may span batches — the server reassembles them into one event with
parsed frames. It tails from the end, survives rotation/truncation, and
buffers in memory (20k lines) with backoff while the API is unreachable.
If the file doesn't exist yet it waits for it, then reads it from the
top. `--file` repeats for several files. Pass `--commit` (the deployed
SHA) so fixes snapshot the exact failing code.

**No log file? (Railway, Render, Heroku…)** Platforms write your app's
output to their own log stream, not a file. Stream it into a file on any
machine you control and point the forwarder at that file:

```bash
# Railway CLI (railway login + railway link in your app's folder first)
railway logs --service myapp >> /tmp/myapp.log &
python3 ta_forward.py --api http://YOUR-API:8001 --key ta_live_... \
    --file /tmp/myapp.log --service myapp
```

If `railway logs` exits at once (it wants a terminal), wrap it:
`script -q /dev/null railway logs --service myapp | perl -pe 's/\e\[[0-9;]*m//g' >> /tmp/myapp.log &`.
On reconnect the stream may replay recent lines; a crash that already
has an open PR only gets a comment, never a second PR.

**Option 2: Sentry webhook.** The Logs step also creates a Sentry
connection and prints its webhook URL,
`https://YOUR-API/api/ingest/sentry/{key}`. Point a Sentry issue-alert
webhook at it. Exceptions with stacktraces flow through the same
pipeline as forwarder lines.

**Option 3: curl (smoke test).**

```bash
curl -X POST http://YOUR-API:8001/api/ingest/logs \
  -H "Authorization: Bearer ta_live_..." -H 'Content-Type: application/json' \
  -d '{"service":"api","release":"v1","commit":"","lines":[
    {"ts":1700000000,"level":"ERROR","message":"Traceback (most recent call last):"},
    {"ts":1700000001,"level":"ERROR","message":"  File \"/srv/app.py\", line 9, in get"},
    {"ts":1700000002,"level":"ERROR","message":"ZeroDivisionError: division by zero"}]}'
# -> {"accepted":3,"candidates":1}
```

Watch for **✓ first log** in the wizard (the connection flips
`waiting` → `ok`). Keys are `ta_live_*`, shown once; a wrong key gets
401; deleting the connection kills its key immediately.

### C.2 Repo — let us open PRs

Create a fine-grained GitHub token at
[github.com/settings/personal-access-tokens](https://github.com/settings/personal-access-tokens):
repository access to **your** repo,
**Contents: read + write**, **Pull requests: read + write**
(Metadata read comes free). Enter `owner/repo` + base branch + token,
then **Test**. The test checks the repo is readable, the base branch
exists, and the token can write (it creates + immediately deletes a
throwaway `ta-probe-*` ref — no trace). Read-only tokens report
"can read, cannot open PRs" instead of failing later.

What happens per error afterwards: frames locate your files → tarball
at the failing commit (else base HEAD) → sandbox (Modal; your secrets
never go inside) → baseline suite → new repro test must **fail** →
patch (≤ 3 files) → repro passes **and** no previously-passing test
fails → PR with the evidence, labeled `telemetry-agent`, **one open PR
per error fingerprint** (repeats comment on it instead). Unprovable
cases become **draft** PRs with diagnosis only — never a crash, never a
direct edit to your branches.

**What your repo needs for auto-fix:**

| Language | We detect | Log the error as | Test runner (offline after install) |
|---|---|---|---|
| Python | `requirements.txt` / `pyproject.toml` / `setup.py` | Full `Traceback (most recent call last):` | `python -m pytest` from the repo root |
| JavaScript / TypeScript | `package.json` (`tsconfig.json` → TS) | V8 stack (`Error: …` + `at …` lines); ship source maps (`node --enable-source-maps`) | Jest, Vitest, Mocha or `node --test` |
| Java | `pom.xml` / `build.gradle(.kts)` | Full stack trace (`Exception in thread …` + `at …`, incl. `Caused by:`) | Maven Surefire or Gradle (`mvn -o test` / `./gradlew --offline test`) |
| Kotlin | `build.gradle(.kts)` + `.kt` files | Full JVM stack trace, as Java | Maven or Gradle, as Java |
| Go | `go.mod` | `panic: …` + `goroutine …` stack | `go test ./...` |
| Rust | `Cargo.toml` | Panic location + `RUST_BACKTRACE=1` backtrace | `cargo test --offline` |
| PHP | `composer.json` | `PHP Fatal error: …` + `Stack trace:` (`display_errors=stderr`) | PHPUnit or Pest with `--log-junit` |

- Frames must point at files in the repo (container paths like
  `/app/x.py` are matched by suffix; `dist/` JS maps back to `src/` TS
  when the sources are in the repo).
- Dependencies install once with network (`pip`, `npm ci` / `pnpm` /
  `yarn --frozen-lockfile`, `mvn`, `./gradlew`, `go mod download`,
  `cargo fetch`, `composer install`); the suite itself must run offline.
- A fix that fits in at most 3 files. Anything bigger becomes a draft PR
  with the diagnosis.
- The system must be **armed** (Teach → Confirm + Arm). Errors from an
  unarmed system are recorded but never start a fix.
- A language we don't support yet gets alerts and rollback only — the
  repo test says so up front ("Detected: … · alerts and rollback only").

### C.3 Hosting — roll back and restart

**Option 1: Railway.** You need two values:

- **Token:** an *account or workspace* token from
  [railway.com/account/tokens](https://railway.com/account/tokens).
  Project tokens (Project Settings → Tokens) don't work.
- **Service ID:** the service to roll back — in Railway open the
  service → Settings, or run `railway status --json` in the linked
  folder.

Enter both, then **Connect + Test ping**. The test passes only if the
token can read that service's deployments. Afterwards:

- *Rollback* redeploys your newest **successful** deployment
  (zero-downtime swap).
- *Restart* restarts your latest deployment.

**Option 2: signed webhook.** Give us your receiver URL + a shared
secret. We `POST` it:

```jsonc
// POST {your url}, Content-Type: application/json
// X-Telemetry-Signature: sha256=<HMAC-SHA256(secret, raw body)>
// X-Telemetry-Timestamp: 1700000000.0
{"action": "rollback", "system_id": "acme-9f2c", "run_id": "a1b2c3", "ts": 1700000000.0}
```

`action` is only ever `rollback`, `restart` (or `ping` for the test
button). 2xx means done. Minimal receiver sketch:

```python
import hmac, hashlib, json
from http.server import BaseHTTPRequestHandler, HTTPServer

SECRET = "whsec_..."  # the secret you pasted into /connect

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        raw = self.rfile.read(int(self.headers["Content-Length"]))
        want = "sha256=" + hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(want, self.headers.get("X-Telemetry-Signature", "")):
            self.send_response(401); self.end_headers(); return
        body = json.loads(raw)
        if body.get("action") == "ping":
            self.send_response(200); self.end_headers(); return
        # TODO: rollback/restart YOUR service here, then:
        self.send_response(200); self.end_headers()
        self.wfile.write(b'{"ok":true}')
    def log_message(self, *a): pass

HTTPServer(("0.0.0.0", 9000), Handler).serve_forever()
```

Safety rails (enforced server-side, not by convention): the allowlist
is rollback + restart **only**; max 1 mitigation per system per
10 minutes (failures don't consume the budget); every proposal opens a
20 s window and **expires unless a human approves**; nothing runs while a
system is still learning; everything is audited with approver + result.

### C.4 Devices — cold-chain hardware (optional)

Create a `device` connection to get a key, then flash the snippet. The
protocol is three calls with `Authorization: Bearer <device key>`:

```text
GET  /api/devices/{device_id}/commands   -> {"commands":[{"id","action","params","expires_at"}]}
POST /api/devices/{device_id}/commands/{command_id}/ack  {"ok":true,"detail":""} -> {"status":"done"}
POST /api/devices/{device_id}/readings   {temperature_c, door_open, ...}       -> stored for the gate
```

Actions: `defrost`, `setpoint`, `power_cycle`, `backup_on`. Commands
expire after 2 minutes; acks dedupe; the queue refuses while Pause-all
is on. Behavior reference: `hardware/sim_device.py` (runs without
hardware) and the Wokwi sketch (compile-check it in Wokwi before
flashing — see `hardware/wokwi/`).

### C.5 Teach normal, arm, read the promise

- **Teach:** enter the owner contact and any **hard limits** (e.g.
  `temp_c > 8`) — a breached hard limit always counts as a real
  incident. Click **Save**, then **Confirm + Arm**. **Don't skip Confirm
  + Arm:** until the status reads `armed`, errors are recorded but never
  start a fix.
  - Want the agent to learn your normal from documents (runbooks, spec
    sheets — values are quoted, not guessed) and a baseline run? Use
    `/setup` for the same system; while it's learning, it watches but
    never acts.
- **Promise:** read what the agent may and may not do, tick "I
  understand", continue. What you connected decides what it can do: a
  repo alone means **PRs only**; adding Hosting allows **rollback /
  restart proposals** too. Kill switches: global Pause-all, per-system
  Stop watching (on `/setup`), per-connection Disconnect.

### C.6 Pair your phone, start watching

Scan the QR (it carries the API URL), type the mobile token, then
**Start watching**. There's no app-store build yet: install the app from
source (`cd apps/mobile && flutter run`, see A.6).

### C.7 Day 2: what an incident looks like

1. Your app throws → forwarder/Sentry → a gate candidate with frames
   (suppressed with a citation if it's known-normal).
2. A repo run starts; progress streams to the dashboard and phone
   (locate → diagnose → snapshot → verify → generate → PR). A rollback
   window is proposed alongside — it **expires** unless you approve.
3. The phone shows **"Software · PR ready"**: open the PR, or tap
   **Roll back now** for immediate relief (human taps run at once, still
   gated by pause/rate/learning). Approve/deny inside the 20 s window;
   the server acts at the deadline even if no device responds.
4. Cold chain: **"Choose a fix"** cards (defrost, setpoint within
   profile limits, compressor power-cycle after its delay, backup unit,
   manual checklist, dispatch a technician) — each with fail-closed
   safety; unsafe ones are shown disabled with the reason.
5. Everything lands in the run report: diagnosis, proof outputs, suite
   summary, PR link, mitigation + approver audit.

Pause-all freezes the world in one tap. Per-connection **Disconnect**
instantly kills that key; **Stop watching** on `/setup` disarms the
system.

### C.8 Security notes and FAQ

- **What credentials do you need?** A GitHub token scoped to one repo,
  optionally a Railway token or a webhook secret, and device keys we
  mint. Never SSH, never database passwords. Server-side secrets are
  hashed (our keys) or masked (yours); nothing secret is logged or sent
  to the browser (`NEXT_PUBLIC_*` carries only the API URL).
- **Do you touch my code?** Only via PRs on your repo, from
  `telemetry-agent/fix-*` branches, labeled `telemetry-agent`. Drafts
  when unprovable. Never direct commits to your branches.
- **What runs automatically?** Only reversible mitigations inside their
  policy, inside the rate limit, after the cancel window — and today,
  proposals expire unless a human approves.
- **Noisy error (same crash ×1000)?** One candidate fingerprint → one
  run at a time → one open PR; repeats add throttled comments.
- **Leaving?** Disconnect connections (keys die instantly), then Stop
  watching and delete the system on `/setup`. Your repo keeps the PR
  history.
- **Limits (today):**
  - Auto-fix is for Python tracebacks only.
  - No user accounts: one instance = one team. The access code keeps
    strangers out; everyone with the code sees the same systems.
  - Railway: the token + service check runs live; the rollback and
    restart calls are tested against mocks and Railway's docs, not yet
    against a real rollback.
  - No push notifications when the app is fully closed (FCM descoped);
    alerts arrive over the live connection while the app runs.
  - The mobile app is installed from source (Flutter), not an app store.

---

## Further reading

- [`README.md`](../README.md) — the pitch + demo path.
- [`docs/DOCUMENTATION.md`](./DOCUMENTATION.md) — full technical reference.
- [`docs/production-backend.md`](./production-backend.md) — backend
  architecture behind this guide.
- [`docs/production-devices.md`](./production-devices.md) — devices, app
  wiring, firmware, proof-run device half.
- [`docs/proof-run.md`](./proof-run.md) — the human proof-run script.
- [`examples/proof-app/`](../examples/proof-app/) — the reference
  customer app (real bug, 20 tests, trigger script).
