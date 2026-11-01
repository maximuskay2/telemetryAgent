# Demo video script (3 minutes, Meta Global AI Developer Hackathon)

Record in segments (one clip per beat), 1080p, 30fps, browser zoom 100%.
Record the narration separately (~130 wpm) and lay it over the edit.
Speed up the sandbox wait (caption "4× speed"); never fake a step. If
Meta 404s mid-take, keep rolling — the agent fails over to Baseten and
the video stays honest.

## Tools

- Screen: QuickTime / Cmd+Shift+5 (or OBS for browser + phone in one frame).
- Phone on screen: `brew install scrcpy`, then `scrcpy` (USB debugging on;
  the same adb that installs the APK).
- Real-phone cutaway: film the phone ringing for 2–3 s.
- Edit: iMovie or CapCut. Upload to YouTube as unlisted.

## Before you press record

- [ ] Production up: `/api/health` on the API, `/welcome` on the web,
  `/health` on the deploy hook. Open each once to warm them.
- [ ] Meta key in Railway `api` variables is current (else Baseten failover).
- [ ] Phone paired with **Claim code** (web → Your devices → pairing code →
  app → "Claim code & connect"). Plain Connect / Scan QR (no token) and
  "Try the demo" cannot approve your own production runs (401).
- [ ] Phone sound on, Do Not Disturb off, latest APK installed.
- [ ] Production system armed, hosting = deploy webhook, repo =
  `maximuskay2/telemetryAgent-demo`, Logs key (`ta_live_…`) at hand.
- [ ] No open `telemetry-agent/fix-*` PRs on `telemetryAgent-demo`.
- [ ] Fresh demo state: `/start/setup` → Reset world.
- [ ] One window, bookmarks bar hidden, notifications off.

## 0:00–0:15 — The problem

**On screen:** `/welcome`.
**Say:** "Every team has two nightmares: the 3am crash nobody sees, and
the fix nobody trusts. TelemetryAgent is an autonomous SRE agent on
Meta's Muse models. It watches your software and your hardware, proves
every fix in a sandbox, and opens a pull request — while your phone
holds a twenty-second veto."

## 0:15–0:45 — Teach it normal

**On screen:** `/connect` Teach step (or `/start/setup` stage 2).
**Do:** paste the ops manual (`telemetryAgent-demo/docs/telemetry-setup-manual.md`
sections 1–4), extract, scroll the review tables so the quotes show; add
the hard limit `error_rate > 0.5`.
**Say:** "First it learns what normal means — from your manuals, not
vibes. Every value keeps the sentence it came from. Hard limits come
from a human, never from a document."

## 0:45–1:00 — Arm

**On screen:** Watch normal countdown → armed.
**Say:** "It watches normal for thirty seconds, then arms. Until then,
errors are recorded but nothing acts."

## 1:00–2:00 — Break it, watch the loop

**On screen:** Mission Control, incident drawer, phone (scrcpy), GitHub.
**Do:** Break shop. Read the gate citation aloud. The phone rings the
moment the fix is generated — "Verifying fix…" — then counts down 20 s
once verification passes. Let it ride (or tap Approve). Follow the trace:
diagnose → patch → fail-to-pass in the sandbox → PR. Open the PR: new
repro test + green suite.
**Say:** "Errors climb, and the agent goes to work: diagnosis from Muse
Spark, a patch from Muse Spark Open, proven fail-to-pass in an isolated
Modal sandbox. My phone rang the second a fix existed — nothing deploys
until it's verified and the veto runs out."

## 2:00–2:40 — The real product: your repo, not our simulator

**On screen:** terminal, production site, phone, GitHub, deploy-hook page.
**Do:** in `telemetryAgent-demo`, run
`python3 trigger_bug.py --key ta_live_…` (a real deadlock in
`inventory.py`, real stack trace shipped to production). Show the
incident on the production site, the rollback alarm on the phone, the
signed `rollback` landing on
`https://deploy-hook-production-6c1c.up.railway.app/`, and the new
`telemetry-agent/fix-*` PR on the repo.
**Say:** "This isn't the simulator. A real service deadlocks; its stack
trace reaches TelemetryAgent through a logs key; the phone offers a
rollback through a signed webhook; and the fix arrives as a pull
request on the customer's repo — proven, never pushed."

## 2:40–3:00 — Close

**On screen:** `/welcome` or the README architecture.
**Say:** "Muse Spark diagnoses, Muse Spark Open patches, Muse Wonder
escalates, Modal proves. Built by one developer with a team of Muse Code
agents. TelemetryAgent — the on-call engineer that proves its work.
Links below."

## Shot list (B-roll / cutaways)

1. Gate citation close-up (quoted sentence from the manual).
2. Phone: "Verifying fix…" then the 20 s countdown ring.
3. Sandbox proof lines (test fails before, passes after).
4. GitHub PR files-changed tab (sorted lock order + new test).
5. Deploy-hook page showing the signed `rollback` row.

## If something fails on camera

- Extraction 502s → "Meta is throttling — watch the Baseten failover";
  retry once, keep the take if it lands.
- Phone shows "Bad mobile token — re-pair" → re-pair with Claim code.
- `trigger_bug.py` prints `401` → wrong key; rotate the Logs connection.
- No new PR → system not armed, or the crash matched an open PR (it
  comments instead). Close it and trigger again.
- Never use Settings → Test alarm for the aired shot; the alarm must come
  from a live run.
