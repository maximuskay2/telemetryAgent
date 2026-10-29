# Proof run (human script, backend half)

Run this twice from a clean state (T-R1). It proves the 🔵 production
route on a real customer-shaped app. John's half (phone cards, ESP32,
`/connect` clicks) lives under "Proof run" in
[`production-devices.md`](production-devices.md); the steps below are the
backend spine both runs follow.

## 0. Prereqs (once)

- [ ] Public repo `maximuskay2/telemetryAgent-proof-app` created from
  `examples/proof-app/` (README inside).
- [ ] Proof app deployed on Railway from that repo (Procfile start).
- [ ] GitHub fine-grained token with Contents + Pull requests write on
  the proof repo; `RAILWAY_TOKEN` + service id for the rollback step.
- [ ] API + web running; phone paired; `PRODUCTION_CONNECT_ENABLED=1`.

## 1. Connect (5 min, via `/connect`)

1. Name the system, connect logs (forwarder one-liner on the machine
   tailing the proof app's log, or the Sentry webhook).
2. Watch for **✓ first log** (`connection_status`).
3. Connect the proof repo → **Test** → green with the default branch.
4. Connect Railway (token + service id) → **Send test ping**.
5. Teach normal (docs + short learn), set permissions to **PR + rollback**,
   tick "I understand", pair the phone, **Start watching**.

## 2. Break it (2 min)

```bash
python trigger_bug.py https://<proof-app>.up.railway.app
# -> crashed as expected: 500
```

The traceback lands in the app log; the forwarder ships it; the gate
records an `observe` candidate with frames; a repo run starts and the
phone shows the progress (locate → diagnose → snapshot → verify →
generate → PR).

## 3. Watch the fix (3–6 min)

- Backend: `GET /api/runs` → the `repo` run goes `PASS` with `pr_url`,
  `suite {passed, failed: 0, new_failures: 0}`, fail→pass evidence.
- GitHub: a PR on the proof repo touching `app/cart.py` (+ the repro
  test), label `telemetry-agent`, proof in the body.
- Phone (John): "Software · PR ready" card with Open PR; a rollback
  window was proposed and expired untouched (approve-to-run).

## 4. Roll back, then merge (5 min)

1. On the phone, tap the rollback option → **approve** → Railway
   redeploys the previous successful deployment (or the webhook fires);
   the run's `mitigation` reads `done`.
2. Merge the PR on GitHub → Railway redeploys → `trigger_bug.py` now
   returns 200 with `average_item_price: 0.0`.

## 5. Repeat offenders (2 min)

Fire `trigger_bug.py` 4 more times: still exactly **1 open PR** from
`telemetry-agent/fix-<fp>` (repeats comment, throttled hourly).

## 6. Simulation route still works (3 min)

Run `/welcome` → `/start` → `/start/setup` → `/?tour=1` once: both
doors green. Then `./scripts/check.sh` must be fully green.

## If something fails

- No candidate: check the forwarder is tailing the right file and the
  key (`TA_FIXTURE_KEYS` is NOT for prod).
- Run FAILs "no sandbox": Docker down and no Modal creds — start Docker.
- Draft PR instead of fix: read the "why no fix" line (deps, no tests,
  unreproducible) — that IS the honest outcome; fix forward.
- Production route unstable on camera: `PRODUCTION_CONNECT_ENABLED=0`
  and record the simulation route (cut order in the roadmap §5).
