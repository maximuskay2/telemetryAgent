# Demo video script (3 minutes, Meta Global AI Developer Hackathon)

Record at 1080p, 30fps, browser zoom 100%. Narrate calmly (~130 wpm);
timings below assume the guided demo on a warm API. If Meta 404s
mid-take, keep rolling — the agent fails over to Baseten and the video
stays honest.

## Before you press record

- [ ] API + web freshly deployed; open `/api/health` once to warm it.
- [ ] Fresh demo state: `/start/setup` → Reset world (or restart the
  API — demo runs are in-memory by design).
- [ ] Android phone paired (QR on `/start/phone`), sound on, do-not-disturb off.
- [ ] Close other tabs; hide bookmarks bar; clear notifications.
- [ ] `telemetryAgent-demo` old `telemetry-agent/fix-*` PRs closed (fresh PR is easier to spot).

## 0:00–0:15 — The problem

**On screen:** `/welcome` landing.
**Say:** "Every team has two nightmares: the 3am crash nobody sees, and
the fix nobody trusts. TelemetryAgent is an autonomous SRE agent on
Meta's Muse models that watches your software and your hardware, proves
every fix in a sandbox, and opens a pull request — while your phone
holds a twenty-second veto."

## 0:15–0:45 — Teach it normal

**On screen:** `/start` → `/start/setup`, stage 2.
**Do:** expand "Use your own manual" on the shop; paste two lines
("Order error rate stays under 1%… Error rate over 50% is never
normal."); Upload & extract. Show the learned counts.
**Say:** "First it learns what normal means — from your manuals, not
vibes. Spec PDFs, runbooks, photos, or pasted notes. Every value keeps
its quote."

## 0:45–1:15 — Arm both systems

**On screen:** stages 3–4, both sides.
**Do:** click through Learn and Arm on shop + freezer; linger half a
second on the 30-second "Watch normal" countdown.
**Say:** "It watches normal for thirty seconds, then both systems arm —
a Python shop and a cold-chain freezer, same reasoning core."

## 1:15–2:15 — Break the shop, watch the loop

**On screen:** Mission Control (`/`), then the incident drawer.
**Do:** Break shop. Point at the error-rate climb; open the incident;
read the gate citation aloud ("Expected: …" / hard-limit line). Cut to
the phone the moment the alarm fires: show the 20-second veto ring,
tap nothing, let it auto-apply. Back on desktop, follow the trace:
diagnose → patch → sandbox proof (fail-to-pass) → PR link. Open the
GitHub PR in a new tab, show the repro test + green suite.
**Say:** "Now we break it. Errors climb — and the agent doesn't page
me, it works: diagnosis from Muse Spark, a patch from Muse Spark Open,
proven fail-to-pass in an isolated Modal sandbox, then a pull request
with the evidence attached. My phone held a veto the whole time — I
let it ride."

## 2:15–2:45 — The real product in 30 seconds

**On screen:** quick cuts — `/dashboard`, `/keys`, `/connect` Teach
step, phone report.
**Say:** "The same flow connects real systems: log forwarder or Sentry,
your GitHub repo, Railway or a signed webhook, per-device keys, and a
dashboard that resumes every unfinished setup. Nothing arms until you
say so; nothing shuts down without a human."

## 2:45–3:00 — Close

**On screen:** `/welcome`.
**Say:** "TelemetryAgent — the on-call engineer that proves its work.
Links below: live demo, docs, and the repo."

## Shot list (B-roll / cutaways)

1. Gate citation close-up ("Expected: defrost, spec sheet p.2").
2. Phone veto ring counting down (film over the shoulder).
3. Sandbox proof lines (test fails before, passes after).
4. GitHub PR files-changed tab (one-line fix + new test).
5. Keys page `****last4` row (trust beat, 2 seconds).

## If something fails on camera

- Extraction 502s → say "Meta is throttling — watch the Baseten
  failover" and retry once; keep the take if it lands.
- API cold / demo reset → cut; restart from `/start/setup` (stages
  restore in under a minute).
- Never fake the phone shot: Settings → Test alarm only for framing;
  the aired alarm must come from the live run.
