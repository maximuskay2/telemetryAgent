# TelemetryAgent usage guide

This is the human guide to what we built and how to use it. The technical
reference is [DOCUMENTATION.md](./DOCUMENTATION.md).

**What it is.** TelemetryAgent is an AI on-call engineer. It watches
software and equipment, ignores what it has learned is normal, writes a
fix, **proves** that fix in a sandbox, and waits 20 seconds so a human
can approve or cancel. It is **free for now** — no prices, no checkout.

The mark in the header and the browser tab is Jude’s pulse-to-check
logo (Meta blue `#0866FF`). Same file in local and on the public site:
`apps/web/public/logo.svg`.

**You do not need the team to try this.** This file and
[DOCUMENTATION.md](./DOCUMENTATION.md) are enough. Stuck: `/support`,
[support@maxit.com.ng](mailto:support@maxit.com.ng),
[0803 695 4577](tel:+2348036954577).

---

## Demo vs production (pick one)

Two environments, same agent. Do not mix them.

| | **Demo** (no account) | **Production** (sign in) |
| :--- | :--- | :--- |
| Who | Anyone: testers, judges, organizers | You connecting *your* shop, repo, or fridge |
| Start | [Home](https://web-production-926b3.up.railway.app/welcome) → **Try the live demo** | Home → **Connect your production** → sign in |
| What you watch | AutoParts Lagos shop + the virtual freezer already running on our API | Your logs / Sentry, your GitHub repo, your Railway or webhook, optional ESP32 |
| Fridge | Mission Control **fault buttons** (door, defrost…). No Wokwi needed | Real device protocol: [Wokwi.com](https://wokwi.com) or `sim_device.py` (see [§ E](#e-wokwi--the-esp32-without-hardware)) |
| Mission Control | Opens after the 4-step guided setup. No skip | Opens after Connect → Teach → **Confirm + Arm** |
| Local | `./scripts/demo.sh` then http://localhost:3000/welcome | Same laptop, then sign in and `/connect` (or the public site) |
| Public | https://web-production-926b3.up.railway.app/welcome | Same host, **Sign in** |

**Public URLs**

- Home: [web-production-926b3.up.railway.app/welcome](https://web-production-926b3.up.railway.app/welcome)
- How to: [/guide](https://web-production-926b3.up.railway.app/guide)
- Support: [/support](https://web-production-926b3.up.railway.app/support)
- API: [api-production-0c9a.up.railway.app](https://api-production-0c9a.up.railway.app)

Notation: `YOUR-API` is wherever the API runs (`http://localhost:8001`
locally, the Railway URL above in production). `YOUR-WEB` is the
dashboard.

---

## What you will see (read this first)

Home has **two doors**. Mission Control does not open until a
walkthrough finishes. There is **no Skip to Mission Control**.

| Door | Account? | Path |
| :--- | :--- | :--- |
| **Try the live demo** | No | Home → `/start` → set up the demo shop + freezer → Mission Control |
| **Connect your production** | Yes | Home → Sign in → `/connect` → your system |

**How to** and **Support** are menu pages, not blocks on the home hero.
Support: [support@maxit.com.ng](mailto:support@maxit.com.ng),
[0803 695 4577](tel:+2348036954577).

**Advanced setup** lives inside a walkthrough only:

- Demo: on **Read the manuals**, if you want to upload your own documents.
- Production: on **Teach**, if you want manuals and a full profile review
  for that system.

The guided demo already teaches from our copies. You do not need
Advanced setup to finish.

After you sign in you stay in **Connect · Members · Devices · Usage**.
**Live demo** stays in the header so you can still try the shop without
logging out.

---

Five jobs, one doc:

- **A. Use it locally** — run the **demo** on your machine.
- **B. Run it in production** — deploy the API + dashboard (hosted site).
- **C. Connect your production** — your server, repo, hosting, devices.
- **D. Your account** — members, phones, free allowance.
- **E. Wokwi** — virtual ESP32 for the **production** appliance path.

---

## A. Use it locally

### A.1 Prerequisites

- Python 3.9+, Node.js 20.9+, npm.
- A sandbox for verification: a [Modal](https://modal.com) account
  (`modal setup` once), **or** Docker Desktop (see B.1).
- Flutter (only for the mobile app — see A.6).
- Model keys. Without them the dashboard and simulators run, but
  diagnose/generate steps fail:

| Key | What it does | Where to get it |
| --- | --- | --- |
| `MODEL_API_KEY` | **Required.** Meta Model API: Muse Spark diagnosis, Muse Wonder last attempt, and last-resort generation | Your Meta Model API access (the client calls `https://api.meta.ai/v1`) |
| `BASETEN_API_KEY` | Recommended. Muse Spark Open generation (tried first) | [baseten.co](https://www.baseten.co) → account → API keys |
| `FIREWORKS_API_KEY` | Optional backup generation | [fireworks.ai](https://fireworks.ai) → account → API keys |
| `MODAL_TOKEN_ID` / `_SECRET` | Optional; `modal setup` stores a token in `~/.modal.toml` instead | [modal.com](https://modal.com) → Settings → API tokens |

Generation tries Baseten → Fireworks → Meta Model API and skips any
provider without a key.

### A.2 Install

```bash
git clone https://github.com/maximuskay2/telemetryAgent.git
cd telemetryAgent
python -m venv venv && venv/bin/pip install -r requirements.txt
npm install                       # web workspace deps
cp .env.example .env              # then fill in the keys (see table below)
```

Never commit `.env`. Do not ask an agent to write it.

Key environment variables (full list with comments in `.env.example` and
[DOCUMENTATION.md §4](./DOCUMENTATION.md#4-configuration)):

| Variable | Purpose |
| --- | --- |
| `MODEL_API_KEY` | Meta Model API (Muse Spark + Muse Wonder) |
| `BASETEN_API_KEY` | Muse Spark Open on Baseten (primary generation) |
| `FIREWORKS_API_KEY`, `FIREWORKS_PATCH_MODEL` | Optional backup generation |
| `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET` | Modal Sandboxes (or `modal setup` once) |
| `TA_VERIFY=local` | Force Docker verification instead of Modal |
| `GITHUB_TOKEN` | Opening PRs (demo repo + connected customer repos) |
| `GITHUB_DEMO_REPO`, `GITHUB_BASE_BRANCH` | Demo PR target (`owner/repo`, `main`) |
| `MOBILE_API_TOKEN` | Self-hosted phone approve/pause (empty = open, dev only) |
| `AUTO_ACTION_SECONDS`, `AUTO_ACTION_ENABLED` | Veto window (default 20 s) + master switch |
| `PRODUCTION_CONNECT_ENABLED` | `0` switches `/connect` off (default `1`) |
| `CONNECT_ACCESS_CODE` | Self-hosted: `/connect` and connection routes need this code |
| `DATABASE_URL` | Hosted: Postgres orgs. Unset = file store (local demo) |
| `CLERK_*` / `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | Hosted sign-in |
| `TA_FREE_*` | Hosted fair-use limits (systems, devices, fix runs, cost) |
| `TA_DATA_DIR` | Data root (default `./data`) |
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
[DOCUMENTATION.md §17](./DOCUMENTATION.md#17-troubleshooting)).

To try the production route locally against a real app, use
`examples/proof-app/` and follow [`docs/proof-run.md`](./proof-run.md).

### A.4 The demo journey (about 5 minutes)

1. Open `http://localhost:3000/welcome` (or just `:3000` — first visit
   is sent here).
2. Optional: read **How to** (`/guide`) or **Support** (`/support`).
3. Click **Try the live demo** → `/start`. Three short cards: what it
   watches, how it stays safe, then choose **Use the demo business**.
   (Card 3 also offers **Connect my own system**, which is the signed-in
   production door.)
4. `/start/setup` — about three minutes: meet the business, **Read the
   manuals**, watch two quiet minutes, start watching. On Read the
   manuals you *may* open Advanced setup; the guided path already uses
   our copies.
5. Mission Control opens with a short tour. Break the shop (later you
   can open the freezer door). The agent finds the cause, writes a fix
   with a test, and waits **20 seconds**. Approve, cancel, or let the
   countdown finish.

What to look for: the **gate** cites its sources (“Expected: defrost,
spec sheet p.2”); the **proof** is fail-to-pass in a sandbox; the **PR
is real** when GitHub is configured; nothing deploys without the
cancel window.

Other public pages: `/shop` (the storefront), `/classic` (old
dashboard, kept for the video).

### A.5 Simulators and faults

- **Shop** (`demo/shop/`, `/shop`): products, orders, retries,
  deadlocks, load controls. Its own endpoints on `:8002`: `POST /deploy`
  (deploy mode), `POST /reload` (hot-swap the inventory module),
  `POST /restart` (restarts the shop process); `POST /api/sim/reset` on
  the API restores the buggy shop, the fridge and open windows.
- **Fridge/freezer (demo):** Mission Control fault buttons, or
  `/api/sim/fridge/*`. This is the virtual freezer. **You do not need
  Wokwi for the demo.**
- **ESP32 (production appliance):** same protocol two ways — Python
  `hardware/sim_device.py`, or the firmware in `hardware/wokwi/` on
  [wokwi.com](https://wokwi.com). Step-by-step: [§ E](#e-wokwi--the-esp32-without-hardware).

### A.6 Mobile app (download the APK)

Users do **not** need Flutter. Download the Android APK and pair it to
the demo or to production:

- File: [YOUR-WEB/downloads/telemetry-agent.apk](https://web-production-926b3.up.railway.app/downloads/telemetry-agent.apk)
- In the product: **How to → Download APK** (`/guide#phone`)
- Android only. The phone will warn that the file is not from Play
  Store — that is expected.

**Demo (no account)**

1. Finish the live-demo walkthrough so Mission Control opens.
2. Install the APK. Open the app.
3. Tap **Pair** on Mission Control and scan the QR (it carries the API
   URL).
4. Token: leave blank on the public demo. On a local API, type
   `MOBILE_API_TOKEN` from `.env` (blank if unset). Local phones need
   the same Wi-Fi and `API_HOST=0.0.0.0`.
5. The phone shows the report. Approve, cancel, or do nothing. If no
   one answers, it acts — you already gave that permission.

**Production (signed in)**

1. Install the same APK.
2. **Devices** → label the phone → **Get pairing code** (10 minutes).
3. In the app, claim that code (API URL is the public API or your
   instance).
4. Revoke the phone on Devices to stop its approvals at once.

Developers who want to run from source:

```bash
cd apps/mobile && flutter pub get && flutter run
# or: ./scripts/build-apk.sh
```

Android emulator API URL: `http://10.0.2.2:8001`. Physical phone: your
Mac’s LAN IP.

### A.7 Checks

```bash
./scripts/check.sh   # python suite + simulation smoke + web build + flutter
```

`scripts/smoke_demo.sh` alone spins the API on a spare port with a temp
data dir, arms the demo shop, and runs two live agent runs — the
“simulation route preserved” guarantee. Set `SMOKE_WEB_URL` to include
page checks (never point it at someone's live `:3000`).

---

## B. Run it in production

Reference deployment: Railway services **web** and **api** from
[`maximuskay2/telemetryAgent`](https://github.com/maximuskay2/telemetryAgent)
`main`. A push to `main` deploys both. Web’s root directory is
`apps/web`. `railpack.json` starts the API:

```bash
python -m uvicorn apps.api.main:app --host 0.0.0.0 --port $PORT
```

### B.1 Services

- **API service** (Python): repo root, command above. Set every
  variable from A.2 that applies (model keys, `GITHUB_TOKEN`,
  `MOBILE_API_TOKEN` or Clerk, `RAILWAY_TOKEN` if you offer hosted
  mitigations). Set `CORS_ORIGIN_REGEX` to allow the web origin.
- **Web service** (Node): root directory `apps/web`.
  `NEXT_PUBLIC_API_URL` is **baked into the build** — set it to the
  API’s public URL and redeploy web after any change.
- **Sandbox:** prefer Modal (`MODAL_TOKEN_ID` / `SECRET`) — no Docker
  daemon on the host. Without Modal, verification needs Docker on the
  API host (`TA_VERIFY=local` + `./scripts/build-sandbox-image.sh`);
  most PaaS hosts don’t allow that, so treat Modal as required in
  production.

If a service was created with a CLI upload and has **no GitHub
source**, Railway will not pick `main`. Connect it to
`maximuskay2/telemetryAgent@main` (web: also set root `apps/web` and
watch `apps/web/**`).

### B.2 Two ways to run the API

**Self-hosted (file store)** — leave `DATABASE_URL` unset. State lives
under `TA_DATA_DIR` (default `./data`): profiles, connections
(**tokens**, mode `0600`), audit, pause. Railway disks are ephemeral —
**mount a volume** or every redeploy forgets systems and connections.
Optional `CONNECT_ACCESS_CODE` on connection routes. Fine for a private
team or the public demo’s simulators.

**Hosted (many customers)** — set `DATABASE_URL` (Railway Postgres),
Clerk (`CLERK_JWKS_URL`, `CLERK_SECRET_KEY`, and on web
`NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`), and `COMMERCE_MASTER_KEY`. Then
each customer signs in, gets an organization, and `/connect` does **not**
ask for the shared access code. Usage and the free allowance are
enforced here.

The **web doors** (demo public, production behind sign-in, How to,
Support) work in both modes. Hosted org pages (Members, Devices, Usage)
need the hosted API.

### B.3 Operating notes

- `/api/health` is the uptime probe; `/api/actions/pause` is the global
  kill switch — paused means nothing runs, due windows expire, and
  device queues refuse.
- The forwarder is served at `GET /forwarder.py`, so customers always
  fetch the matching version.
- Nothing secret is logged (keys shown once on create, hints afterwards).
- `PRODUCTION_CONNECT_ENABLED=0` hides `/connect` instantly while the
  simulation route keeps working.

---

## C. Connect your production (customer guide)

You keep your code, your repo, your hosting. TelemetryAgent reads your
errors, proves fixes in a sandbox, and proposes — never pushes. **Free
for now.**

### C.0 Sign in first

Open **Connect your production** on Home. That goes to `/signin`, then
`/connect`. Signing in creates your organization. The live demo stays
open from Home — you do not need an account for that.

On a **self-hosted** instance with `CONNECT_ACCESS_CODE` set, and you
are *not* signed in, `/connect` still asks for that code. Ask whoever
runs the instance. Secrets are never returned by the API, only hints.

**Using the public site? Know this:**

- Anything you connect is **erased when the public API is redeployed**
  unless that API has a volume or Postgres. Fine for trying it; for
  anything lasting, run your own instance (B.2).
- Fix runs use the team’s model and sandbox credits — please connect
  only a test repo.
- When the allowance is reached, monitoring still works; spending fix
  runs stop. See **Usage**.

The wizard’s steps depend on what you pick in step 1:

- **Software:** System → Logs → Repo → Hosting → Teach → Promise → Pair →
  Start.
- **Appliance:** System → Device → Teach → Promise → Pair → Start.

Repo and Hosting have **Connect + Test** / **Connect + Test ping**;
green means really verified. Logs and Device wait for the first log
line / reading.

On **Teach**, set hard limits in the wizard, or open **Advanced setup**
to upload manuals and review the extracted profile. **Don’t skip
Confirm + Arm:** until the status reads `armed`, errors are recorded
but never start a fix.

### C.1 Logs — ship us your errors

**Option 1: forwarder (any server, 1 minute).** The wizard prints this
with your key filled in:

```bash
curl -s http://YOUR-API:8001/forwarder.py -o ta_forward.py
python3 ta_forward.py --api http://YOUR-API:8001 --key ta_live_... \
    --file /var/log/myapp.log --service myapp --release v1.2.3 --commit abc123
```

Expectations: plain text logs; WARNING+ lines and full traces are
forwarded (tune with `--level`). Multi-line traces may span batches —
the server reassembles them (Python, JS/TS, Java/Kotlin, Go, Rust,
PHP). It tails from the end, survives rotation/truncation, and buffers
in memory (20k lines) with backoff while the API is unreachable. Pass
`--commit` (the deployed SHA) so fixes snapshot the exact failing code.

**No log file? (Railway, Render, Heroku…)** Stream platform logs into a
file and point the forwarder at that file:

```bash
railway logs --service myapp >> /tmp/myapp.log &
python3 ta_forward.py --api http://YOUR-API:8001 --key ta_live_... \
    --file /tmp/myapp.log --service myapp
```

If `railway logs` exits at once (it wants a terminal), wrap it:
`script -q /dev/null railway logs --service myapp | perl -pe 's/\e\[[0-9;]*m//g' >> /tmp/myapp.log &`.
On reconnect the stream may replay recent lines; a crash that already
has an open PR only gets a comment, never a second PR.

**Option 2: Sentry webhook.** The Logs step creates a Sentry connection
and prints `https://YOUR-API/api/ingest/sentry/{key}`. Point a Sentry
issue-alert webhook at it.

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
**Contents: read + write**, **Pull requests: read + write**.
Enter `owner/repo` + base branch + token, then **Test**. The test
creates and immediately deletes a throwaway `ta-probe-*` ref. Read-only
tokens report “can read, cannot open PRs”.

What happens per error: frames locate your files → tarball at the
failing commit → sandbox (customer secrets never go inside) → baseline
suite → new repro test must **fail** → patch (≤ 3 files) → repro
passes **and** no previously-passing test fails → PR labeled
`telemetry-agent`, **one open PR per error fingerprint**. Unprovable
cases become **draft** PRs with diagnosis only — never a crash, never a
direct edit to your branches.

**Languages we can auto-fix today:** Python, JavaScript/TypeScript,
Java, Kotlin, Go, Rust, PHP. The crash trace picks the language; the
repo must match (e.g. a Java trace from a Python repo will not start a
run). Unknown language: recorded, no fix, gate says auto-fix is not
supported yet.

**What your repo needs:**

- Errors logged as full traces whose frames point at files in the repo
  (container paths like `/app/x.py` are matched by suffix).
- The language’s normal test command from the repo root (pytest, Jest,
  Maven/Gradle, `go test`, `cargo test`, PHPUnit/Pest).
- Dependencies the adapter can install (lockfile / `go.mod` /
  `Cargo.toml` / Composer / Maven or Gradle wrapper).
- A fix that fits in at most 3 files. Bigger → draft PR.
- The system must be **armed**.

### C.3 Hosting — roll back and restart

**Option 1: Railway.** You need two values:

- **Token:** an *account or workspace* token from
  [railway.com/account/tokens](https://railway.com/account/tokens).
  Project tokens do not work.
- **Service ID:** the service to roll back — Settings, or
  `railway status --json`.

Enter both, then **Connect + Test ping**. Afterwards:

- *Rollback* redeploys your newest **successful** deployment.
- *Restart* restarts your latest deployment.

**Option 2: signed webhook.** Give us your receiver URL + a shared
secret. We `POST`:

```jsonc
// POST {your url}, Content-Type: application/json
// X-Telemetry-Signature: sha256=<HMAC-SHA256(secret, raw body)>
// X-Telemetry-Timestamp: 1700000000.0
{"action": "rollback", "system_id": "acme-9f2c", "run_id": "a1b2c3", "ts": 1700000000.0}
```

`action` is only ever `rollback`, `restart`, or `ping` (the test
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

Safety rails: allowlist is rollback + restart **only**; max 1
mitigation per system per 10 minutes; every proposal opens a 20 s
window and **expires unless a human approves**; nothing runs while a
system is still learning; everything is audited.

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
is on.

To drive the device without buying hardware, use **§ E** (Wokwi in the
browser) or the Python stand-in the wizard also prints:

```bash
python3 hardware/sim_device.py --api YOUR-API --device fridge-01 \
  --key ta_live_… --fault door_open
```

### C.5 Teach normal, arm, read the promise

- **Teach:** owner contact and **hard limits** (e.g. `temp_c > 8`) — a
  breached hard limit always counts as a real incident. **Save**, then
  **Confirm + Arm**. Optional Advanced setup: documents are quoted, not
  guessed; while learning, it watches but never acts.
- **Promise:** read what the agent may and may not do, tick “I
  understand”. A repo alone means **PRs only**; adding Hosting allows
  **rollback / restart proposals**. Kill switches: global Pause-all,
  per-system Stop watching, per-connection Disconnect.

### C.6 Pair your phone, start watching

Download the APK first (same file as the demo — see [A.6](#a6-mobile-app-download-the-apk)
or `/guide#phone`).

- **Hosted / signed-in:** **Devices** → label the phone → 10-minute
  code → claim it in the app. Revoke there to stop approvals immediately.
- **Self-hosted / local demo:** scan the Mission Control **Pair** QR
  (API URL), then type `MOBILE_API_TOKEN` if that instance set one.

Then **Start watching**. There is no Play Store listing. The APK is the
install.

### C.7 Day 2: what an incident looks like

1. Your app throws → forwarder/Sentry → a gate candidate (suppressed
   with a citation if it's known-normal).
2. A repo run starts; progress streams to the dashboard and phone. A
   rollback window is proposed alongside — approve it by tapping
   **Roll back now** (step 3) or it **expires**.
3. The phone shows **“Software · PR ready”**: open the PR, or tap
   **Roll back now**. (The demo shop is different: its verified fix
   applies at the deadline unless you disapprove.)
4. Cold chain: **“Choose a fix”** cards — unsafe ones are shown
   disabled with the reason.
5. Everything lands in the run report: diagnosis, proof, suite, PR
   link, mitigation + approver audit.

Pause-all freezes the world in one tap. **Disconnect** kills that key;
**Stop watching** disarms the system.

### C.8 Security notes and FAQ

- **What credentials do you need?** A GitHub token scoped to one repo,
  optionally a Railway token or a webhook secret, and device keys we
  mint. Never SSH, never database passwords.
- **Do you touch my code?** Only via PRs on your repo, from
  `telemetry-agent/fix-*` branches, labeled `telemetry-agent`. Never
  direct commits to your branches.
- **What runs automatically?** Only reversible mitigations inside
  policy and rate limits — and today, proposals expire unless a human
  approves. The demo shop is the exception (apply-at-deadline).
- **Noisy error (same crash ×1000)?** One fingerprint → one run → one
  open PR; repeats add throttled comments.
- **Leaving?** Disconnect, Stop watching, delete the system. Hosted
  owners can delete the organization (grace period). Your repo keeps
  the PR history.
- **Limits (today):**
  - Auto-fix: Python, JS/TS, Java, Kotlin, Go, Rust, PHP.
  - **Free for now:** default 3 systems, 5 phones, 30 fix runs / month,
    $25 estimated provider cost. Over that, alerts continue; spend
    stops.
  - Hosted: one org’s data is not visible to another. Self-hosted: one
    instance = one team.
  - No push notifications when the app is fully closed (FCM descoped).
  - The mobile app is an Android APK (not on the Play Store). Download
    it from How to (`/downloads/telemetry-agent.apk`); pair it to the demo or to
    production.

---

## D. Your account (after sign-in)

These pages sit behind sign-in. The live demo does not.
Local development can also sign in with a test token on the
sign-in page (needs a local API running with `TA_AUTH_TEST_ISSUER`).

### D.1 Members (`/members`)

Roles: **owner** (everything, including delete org) · **admin**
(connect, arm, approve, invite, revoke phones) · **member** (view +
approve) · **viewer** (read only).

Invite by email. The teammate opens `/invite/<token>` while signed in.
Remove a member and their session and phone stop immediately. Owners
can transfer ownership or delete the organization.

### D.2 Devices (`/devices`)

Pair a phone with a short-lived code (10 minutes). Revoke a phone to
stop its approvals now. Hosted approvals check that user’s role on the
incident’s org.

### D.3 Usage (`/usage`)

This month against the free allowance: fix runs, systems, devices,
estimated cost, and a split by language. There are **no prices and no
checkout**. When a limit is hit, the next spending fix run is blocked
with the reason `free allowance reached: …`. Watching and alerts
continue.

---

## E. Wokwi — the ESP32 without hardware

[Wokwi.com](https://wokwi.com) is a **browser ESP32**. Use it for the
**production appliance** path (Connect → Device). It is **not** how the
live demo freezer runs.

| You want | Use |
| :--- | :--- |
| 5-minute **demo** (shop + freezer) | Mission Control fault buttons. Skip this section. |
| Prove the device protocol, no browser | `sim_device.py` (wizard prints the command) |
| Show “same firmware as a real chip” | Wokwi.com, steps below |
| Local API + Wokwi in the cloud | Wokwi **cannot** reach `localhost`. Use your LAN IP or `sim_device.py` |

Files: `hardware/wokwi/sketch.ino` + `hardware/wokwi/diagram.json`.
The sketch already defaults `API_BASE` to the public API.

### E.1 Public production (judges, testers, organizers)

1. Open [Home](https://web-production-926b3.up.railway.app/welcome) →
   **Connect your production** → sign in.
2. Create an **appliance** (fridge or freezer). On **Device**, set an id
   such as `wokwi-esp32-01` → **Create device key**. Copy the key
   (shown once). The page also prints the three `#define` lines.
3. Open [wokwi.com](https://wokwi.com) → New Project → **ESP32** →
   Arduino.
4. Replace the editor files with `sketch.ino` and `diagram.json` from
   `hardware/wokwi/` in this repo.
5. Libraries **+** → **DHT sensor library** (Adafruit) and
   **ArduinoJson** (Benoit Blanchon).
6. Paste at the top of the sketch (wizard values):

```c
#define API_BASE "https://api-production-0c9a.up.railway.app"
#define WIFI_SSID "Wokwi-GUEST"
#define WIFI_PASS ""
#define DEVICE_ID "wokwi-esp32-01"
#define DEVICE_KEY "ta_live_…"
```

`Wokwi-GUEST` is Wokwi’s built-in Wi-Fi. Leave it on wokwi.com.

7. Press **▶**. Serial should show `POST readings -> 200` every 2 s.
   The wizard flips to **✓ first reading**.
8. **Hold the red DOOR button** — modeled temperature climbs and the
   hardware lane can open an incident.
9. On the phone (or incident options) tap **Start defrost** — the blue
   DEFROST LED should light within ~10 s.

That is the clip: door → agent → command → LED. The same `.ino` flashes
onto a real ESP32; LEDs become relays on pins 13 (compressor), 12
(defrost), 14 (backup).

### E.2 Local demo API

Wokwi in the cloud cannot call `http://localhost:8001`.

```bash
# Same protocol, no browser — works against local demo
python3 hardware/sim_device.py --api http://localhost:8001 \
  --device fridge-01 --key ta_live_… --fault door_open
```

To use Wokwi.com against a laptop API: start with
`API_HOST=0.0.0.0 ./scripts/demo.sh`, set `API_BASE` to
`http://192.168.x.x:8001` (your Mac’s LAN IP), same Wi-Fi. Or use
[Wokwi for VS Code](https://docs.wokwi.com/vscode/getting-started)
(private gateway can reach localhost).

### E.3 What is real vs modeled

| Signal | In Wokwi | On a real fridge |
| :--- | :--- | :--- |
| `door_open` | Red DOOR button | Door switch |
| `current_a` | CURRENT knob (0–5 A) | Current sensor |
| `temperature_c` | Modeled (DHT22 cannot cool) | The sensor (one line in `loop()`) |
| Outputs | Green / blue / yellow LEDs | Relays on GPIO 13 / 12 / 14 |

Device-side safety matches `sim_device.py`: the compressor never
restarts before `min_off_s`; `power_cycle` during defrost is refused.

Public connections can vanish on API redeploy (no volume). Fine for a
judge session. Need a key and `/connect` on. Stuck: `/guide` or
Support.

---

## Support

In the product: [YOUR-WEB/support](https://web-production-926b3.up.railway.app/support).

| | |
| :--- | :--- |
| Email | [support@maxit.com.ng](mailto:support@maxit.com.ng) |
| Phone | [0803 695 4577](tel:+2348036954577) |

Please say whether you are on the live demo or connecting production,
which page you were on, what you expected, and the system name if you
have one.

How to (short in-app guide): `/guide`.

---

## Who built it

| Person | Role |
| :--- | :--- |
| Akingbade Kayode (Maximusinfotech Services) | Owner |
| James | Muse Code — backend core |
| John | Muse Code — web, app, look |
| Jude | Muse Code — usage, allowance, Rust/PHP, brand mark (pulse → check) |
| Janet | Muse Code — tester |

---

## Further reading

- [`README.md`](../README.md) — the pitch + demo path.
- [`docs/DOCUMENTATION.md`](./DOCUMENTATION.md) — full technical reference.
- [`docs/production-backend.md`](./production-backend.md) — connections, ingest, commerce env.
- [`docs/production-devices.md`](./production-devices.md) — devices, firmware.
- [`docs/proof-run.md`](./proof-run.md) — the human proof-run script.
- [`examples/proof-app/`](../examples/proof-app/) — reference customer app.
- [`commercial-roadmap.md`](../commercial-roadmap.md) — accounts, free-for-now, look.
- [`languages-roadmap.md`](../languages-roadmap.md) — auto-fix beyond Python.
