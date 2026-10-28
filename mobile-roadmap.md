# 📱 TelemetryAgent Mobile: Alerts, Reports & 20-Second Veto (Flutter)

Companion to [`roadmap.md`](roadmap.md) (agent core + Command Center UI) and [`simulation-roadmap.md`](simulation-roadmap.md) (shop, fridge, watchers).

**One line:** the agent catches, diagnoses, fixes, and verifies; the phone **alarms** and shows a **20-second countdown**. If nobody taps **Disapprove**, the verified fix is applied automatically.

```
laptop: shop breaks ─► watcher grabs ─► agent runs ─► VERIFIED ─► server opens 20 s window
                                                                     │
phone:  ██ FULL-SCREEN ALARM ██  loud alarm sound + strong vibration pattern
        "Deadlock in AutoParts shop — verified fix ready"
        Crash ✔ Grab ✔ Suggest ✔ Verify ✔ Fix ⏳ 17 s
        [ DISAPPROVE ]                 [ APPROVE NOW ]
                                                                     │
        no answer by 0 s ─► server auto-applies ─► shop orders turn green
        Disapprove      ─► action cancelled, incident stays open for a human
```

## What the app is for
1. **Alerts that can't be missed:** full-screen overlay, loud alarm sound, strong vibration.
2. **20-second veto:** Approve now / Disapprove; silence means auto-fix.
3. **Reports:** every incident's Crash → Grab → Suggest → Verify → Fix story, and what happened to it (auto-applied, approved, disapproved, expired).

## Safety rules (non-negotiable)
- **The server owns the countdown.** The phone only displays it and sends a decision. If the phone is offline, the server still acts at the deadline (that is the "auto unless disapproved" contract).
- **Only verified actions can auto-run:**
  - Software: run status `PASS` with fail-to-pass verification against the real target file.
  - Appliance: runbook passed `validate_runbook`, and only steps mapped to safe automatable actions (e.g. `close_door`, `clean_condenser` in the sim). Anything else is report-only.
- **FAIL, escalated-without-pass, or rejected runbooks never get a countdown**; they alert as "needs a human".
- **Disapprove always wins if it arrives before the deadline**; a late decision gets `409 too late` and the phone shows what already happened.
- **Kill switch:** `AUTO_ACTION_ENABLED=false` turns every countdown into "approve required".
- **Audit trail:** each window records opened, decision, who/which device, and outcome; shown in reports.
- Approve/Disapprove calls require `MOBILE_API_TOKEN`.

## Platform reality

| Capability | Android | iOS |
| :--- | :--- | :--- |
| Full-screen overlay over lock screen | ✅ full-screen intent (`USE_FULL_SCREEN_INTENT`) | ❌ not allowed; banner + in-app full screen only |
| Loud sound even on silent | ✅ alarm-usage notification channel; DND bypass if user grants | ⚠️ needs Apple **Critical Alerts** entitlement (weeks); use Time-Sensitive notifications instead |
| Custom vibration pattern | ✅ `vibration` package patterns | ⚠️ system haptics only |
| Keep connection in background | ✅ foreground service | ⚠️ limited; needs push (FCM/APNs) |

**Demo device: Android.** iOS gets the best-effort version.

## 🔌 Plugs into what already exists

| Existing piece | Where | Mobile use |
| :--- | :--- | :--- |
| Live event stream | `WS /api/ws` (`apps/api/main.py`) | Alerts, live stepper, countdown ticks |
| `AgentStep` (`step`, `status`, `model`, `detail`, `suggestions`, `source`, `run_id`, `domain`) | `core/schemas/events.py` | Report sections: Diagnosis, Suggestions, Generated fix, Verification, Final action |
| `SimEvent` `watcher_trigger` | Sim 2 / Sim 4 watchers | **Crash + Grab** steps, early-warning alert |
| Recent results by `run_id` (Sim 5 gate) | `apps/api/main.py` | Decides whether a run is eligible for a countdown |
| `POST /api/sim/shop/apply-fix` | Sim 5 | What the server calls when the window auto-applies or is approved (software) |
| `POST /api/sim/fridge/apply-runbook` | Sim 5 | Same, appliance |
| `SimEvent` `fix_applied` | Sim 5 | Confirms the action landed |
| `send_alert` (`channel="sms-stub"`) | `core/actions/notify.py` | Gains a `push` channel (M5) |
| Status colours (green / amber / red / violet AI) | Command Center UI plan | Same theme; countdown uses amber → red |

## Screens
- **Alarm overlay** (full screen): incident title, domain icon, one-line diagnosis, stepper, big circular **20 s countdown**, **DISAPPROVE** (large, red) and **APPROVE NOW**; biometric confirm on Disapprove is optional (off by default so a panicked tap works instantly).
- **Incident report:** header (status, source badge, "first warning → fixed" time), stepper, sections — Incoming telemetry, Diagnosis, Suggestions, Generated fix (code view / runbook with 🛡 per step), Verification (fail → pass, runner Modal/Docker, attempts), Final action (PR link / work order) — and the **decision record** (auto-applied at 0 s / approved by device at 12 s / disapproved at 7 s).
- **Feed:** live incidents, newest first, filter by outcome.
- **Connect:** API URL + token by QR from the dashboard.
- **Settings:** alarm sound, vibration strength, test alarm, warnings on/off, permission checklist (notifications, full-screen intent, DND access, battery optimisation off).

---

## 🗓️ Schedule

```
[Oct 28]          ──> M0: Server-side countdown + decisions API (shared with U2)
[Oct 29]          ──> M1: Flutter skeleton + live connection + pairing
[Oct 30]          ──> M2: Alarm overlay, sound, vibration (Android)
[Oct 31]          ──> M3: Countdown approve / disapprove end to end
[Nov 01]          ──> M4: Reports + feed
[Nov 02]          ──> M5: Push when app is closed (FCM)  + M6 demo cut
```

### M0 — Server-side countdown + decisions *(Wed, Oct 28 · ~4 h)*
- [x] `core/actions/auto_action.py`: `PendingAction` (`run_id`, `domain`, `action`, `opened_at`, `deadline`, `state`: `pending | approved | disapproved | auto_applied | expired | failed`, `decided_by`).
- [x] Open a window automatically when a run finishes eligible (rules above); `AUTO_ACTION_SECONDS=20` (env).
- [x] Asyncio timer per window: at the deadline, if still `pending`, call the existing apply-fix / apply-runbook path and mark `auto_applied`.
- [x] `POST /api/actions/{run_id}/approve` (apply now) and `POST /api/actions/{run_id}/disapprove` (cancel): first decision wins under a lock; late decisions → `409`.
- [x] `GET /api/actions` (open + recent) and `GET /api/runs`, `GET /api/runs/{run_id}` (result + steps + decision record) — shared with Command Center U2.
- [x] Broadcast `SimEvent` kinds: `action_pending` (deadline, action summary), `action_tick` (seconds left, once per second), `action_resolved` (state, by whom).
- [x] `MOBILE_API_TOKEN` required on approve/disapprove and on apply-fix / apply-runbook when set; `AUTO_ACTION_ENABLED` kill switch.
- [x] `API_HOST=0.0.0.0` option in `scripts/demo.sh` for a phone on the same Wi-Fi.
- [x] Tests (no network): eligible vs non-eligible runs; auto-apply at deadline; disapprove before deadline cancels; late disapprove → 409; double decision; kill switch.
- Exit: a verified run opens a 20 s window; doing nothing applies the fix; `curl …/disapprove` within 20 s cancels it. ✅ Verified 2026-10-27 via 25 integration tests through the real ASGI app (open/settle/decide/ticks/broadcasts; keyed live e2e left for demo rehearsal). Notes: one shared 1 s ticker instead of per-window tasks; atomic check-and-set instead of a lock (single loop); apply logic factored into `_deploy_patch_for_run` / `_apply_runbook_for_run` reused by buttons and timer.

### M1 — Flutter skeleton + connection *(Thu, Oct 29 · ~4 h)*
- [x] `apps/mobile/` (Flutter 3.47, Android first); Riverpod; dark theme with shared colours.
- [x] Models for `AgentStep`, `SimEvent` (incl. `action_*`), results, decision record.
- [x] WebSocket client with auto-reconnect + connection indicator; resync from `GET /api/actions` on reconnect so a missed `action_pending` still shows.
- [x] Connect screen + QR pairing (`mobile_scanner`); token in `flutter_secure_storage`.
- [x] Dashboard: "Pair phone" QR in the Command Center top bar.
- Exit: the app connects to the running demo and lists live events. ✅ Code-verified 2026-10-27 (`flutter analyze` clean, 8 Dart tests green, `flutter build web` ✓; physical phone run is manual). Notes: QR carries the API URL from `GET /api/pairing`; the token is typed once (dashboard never sees it).

### M2 — Alarm overlay, sound, vibration *(Fri, Oct 30 · ~5 h)*
- [x] `flutter_local_notifications` **alarm channel**: max importance, alarm audio usage, custom loud sound asset, `fullScreenIntent: true`, category alarm.
- [x] Android manifest: `USE_FULL_SCREEN_INTENT`, `POST_NOTIFICATIONS`, `VIBRATE`, `WAKE_LOCK`, `FOREGROUND_SERVICE`; show-when-locked + turn-screen-on for the overlay activity.
- [x] Foreground service keeps the socket alive while the phone is locked.
- [x] Looping alarm sound in the overlay (`just_audio`, alarm stream) until a decision or the window resolves.
- [x] Strong repeating vibration pattern (`vibration`), escalating in the last 5 s.
- [ ] Optional DND bypass (`ACCESS_NOTIFICATION_POLICY`) with an onboarding explanation.
- [x] iOS fallback: Time-Sensitive notification + in-app full-screen alarm when open.
- [x] Settings → **Test alarm** to rehearse before recording.
- Exit: phone locked and on silent mode → `action_pending` wakes the screen with the overlay, sound, and vibration. ✅ Code-verified 2026-10-27 (analyze clean, widget + unit tests green, web build ✓; physical-device run is manual). Notes: `audioplayers` instead of `just_audio` (equivalent loop); alarm stream is notification-channel audio on Android; DND bypass left optional.

### M3 — Countdown approve / disapprove *(Sat, Oct 31 · ~3 h)*
- [x] Circular countdown driven by the server `deadline` (not a local timer), corrected by `action_tick`.
- [x] **DISAPPROVE** → `POST …/disapprove`; **APPROVE NOW** → `POST …/approve`; buttons lock after one tap.
- [x] Outcome screen: "Auto-applied ✓", "Approved ✓", "Disapproved — left for a human", or "Too late — already applied".
- [x] Stop sound/vibration on any `action_resolved`.
- [x] Dashboard shows the same countdown and outcome on the incident card (U1/U4).
- Exit: one take — shop breaks → phone alarms → do nothing → shop recovers at 0 s; second take — tap Disapprove → shop stays broken, incident marked for a human.

### M4 — Reports + feed *(Sun, Nov 1 · ~4 h)*
- [x] Feed from `GET /api/runs` + live updates; filters: open, auto-applied, approved, disapproved, failed.
- [x] Incident report exactly as in Screens, including the decision record and timings.
- [x] Mini temperature chart (`fl_chart`) for fridge incidents; code view for patches; PR link opens GitHub.
- [x] Share report (text summary) via the system share sheet.
- Exit: every incident from the scenario has a complete, readable report on the phone.

### M5 — Push when the app is closed *(Mon, Nov 2 · ~4 h, needed for real use, optional for the demo)*
- [ ] Firebase project; `firebase_messaging`; `POST /api/devices` registers the FCM token.
- [ ] `core/actions/notify.py` `push` channel: high-priority FCM **data** message on `action_pending` → app shows the alarm overlay from the background handler.
- [ ] Service-account key only in `.env`, never committed.
- Fallback: M2 foreground service covers the Android demo.

### M6 — Demo cut *(Nov 2–3 · ~2 h)*
- [ ] `demo/script.md`: laptop shop breaks → phone screen lights up with alarm → countdown → (take 1) no answer, auto-fix, shop turns green; (take 2, short) Disapprove.
- [ ] Record phone (Android screen record) + laptop together.
- [ ] README: "Mobile alerts & 20-second veto" with screenshots and the safety rules.

---

## ✅ Definition of done
- [ ] A verified incident opens a server-side 20 s window; with no answer, the fix is applied automatically and the shop/fridge recovers.
- [ ] Disapprove within 20 s always cancels; late decisions are rejected and reported.
- [ ] On a locked, silent Android phone the alarm overlay appears with loud sound and strong vibration.
- [ ] FAIL runs and unsafe runbooks never auto-apply.
- [ ] Every incident has a report with its decision record.
- [ ] Existing tests stay green; countdown logic is fully unit-tested.

## ⚠️ Risks and fallbacks

| Risk | Fallback |
| :--- | :--- |
| Auto-applying something wrong | Only verified/safety-passed actions; kill switch; Disapprove; sim-only actions during the hackathon |
| Phone offline during the window | Server acts anyway (by design); report shows "auto-applied, no device response" |
| Full-screen intent denied on Android 14+ | Onboarding asks for it; fallback heads-up alarm notification with sound + vibration |
| iOS can't overlay or bypass silent | Record on Android; iOS shows Time-Sensitive alerts |
| Clock drift between phone and server | Countdown from server `deadline` + `action_tick` corrections |
| Time pressure on the core demo | Cut M5, then M4 polish; M0 + M2 + M3 alone deliver the story |
