# 🧭 TelemetryAgent: New-Customer Journey Roadmap (Advert → Onboarding → Setup → First Incident)

**Goal:** someone clicks an advert, lands on TelemetryAgent, and in about **6 minutes** without help:
1. understands what it does,
2. sets up the two demo systems (the AutoParts shop and the cold-chain freezer),
3. watches the agent catch, fix and verify a real incident,
4. knows where to go next.

Every system in this journey is **our simulation**. Real customer systems come after the hackathon.

**Deadline:** Nov 4, 9:00 PM ET. **Owner of this file:** product (Akingbade). **Builders:** web + API developer.

> Read this before `ui-roadmap.md` work continues. This file decides **which screen comes when**. `ui-roadmap.md` decides **how each screen looks**. Nothing here changes the agent, the gate, the veto logic or existing API responses.

---

## 0. Why it's confusing today (repo audit, Oct 29)

| # | What a new visitor hits | Where in the code |
|---|---|---|
| A1 | `/` opens straight into the 3-pane Mission Control. There's no welcome and no explanation. | `apps/web/app/page.tsx` |
| A2 | With no systems, the left pane shows two dashed "No shop registered yet" tiles. The centre and right panes are empty. | `mission/LeftPane.tsx`, `mission/GatedTile.tsx` |
| A3 | The top bar has 8 icon-only buttons (play, reset, QR, key, bell, focus, presenter) with no labels. **Play** works even when nothing is armed, so the visitor sees nothing happen. | `mission/TopBar.tsx` |
| A4 | Setup is 6 steps of jargon: *Connect · Teach · Review · Learn · Policy · Arm*. Steps can be clicked out of order. | `setup/page.tsx` L55–64, L520–553 |
| A5 | The wizard sets up **one system at a time**. To see both demos you go through it twice. | `setup/page.tsx` |
| A6 | Step 2 asks for spec PDFs and photos. A visitor doesn't have them; they're on *our* disk in `demo/setup/`. The only shortcut, "Load sample profile", skips the impressive part (reading the manuals). | `setup/page.tsx` L697–770 |
| A7 | Step 4 "Start 2-minute learning" only opens a learning window. In the UI nothing sends normal traffic into it; only the CLI script `demo/setup/accelerated_learn.py` does. The shop can finish learning with ~0 patterns. **Verify first (J0).** | `main.py` L1952, L2049 |
| A8 | Step 5 bounces back to Review if "Confirmed by" was left empty, with the message "confirm again to continue". | `setup/page.tsx` L1189–1194 |
| A9 | The customer storefront `/shop` is only linked from the footer of `/classic`. Nobody finds it. | `classic/ClassicDashboard.tsx` L1089 |
| A10 | Approve and Disapprove need the operator token (key icon) when `MOBILE_API_TOKEN` is set. A visitor doesn't have it. | `mission/TopBar.tsx` TokenButton |
| A11 | The hosted Railway demo is **one shared world**. Visitor B sees visitor A's systems, incidents and half-finished setup. | API in-memory state + `setup_store` |
| A12 | Phone pairing, presenter mode and the incident report page exist, but nothing tells a visitor about them. | — |

**Root cause:** each feature was built to its own roadmap (sim, setup, UI, mobile), and **no single document owns the order**. This one does.

---

## 1. The one golden path

```
Advert ─► /welcome ─► /start ─► /start/setup ─► / ?tour=1 ─► wrap-up card
         landing     3 cards    guided setup    first incident   what next
         (15 s)      (30 s)     (~3 min)        (~2 min)         (15 s)
```

| Stage | Visitor sees | Visitor does | Done when |
|---|---|---|---|
| **J-A Landing** `/welcome` | One sentence: *"An AI on-call engineer that catches failures, proves its fix works, and asks before it acts."* Shop and freezer side by side, a 3-step strip (**Notice → Fix & prove → Ask, then act**), the models used. | Clicks **Try the live demo** (primary) or **Watch 3-min video**. | They're on `/start`. |
| **J-B Onboarding** `/start` | 3 short cards, swipe/next: ① what it watches (your software + your equipment) ② how it stays safe (it learns normal first; it never acts without a cancel window; hard limits are human-only) ③ choose a path. | Picks **Use the demo business** (recommended, the only live option). **Connect my own system** shows "After the hackathon — join the waitlist" and links to the advanced `/setup`. | They're on `/start/setup`. |
| **J-C Guided setup** `/start/setup` | One page, 4 stages, **both systems at once** (shop and freezer cards side by side): ① **Meet the business** ② **Read the manuals** ③ **Watch normal** ④ **Choose permissions & start watching**. | Clicks one button per stage. Each stage shows live progress from the real endpoints. | Both systems are `armed`; redirect to `/?tour=1`. |
| **J-D First incident** `/?tour=1` | Mission Control with a coach-mark rail (right edge, 5 steps) and the storefront in a mini window. | Clicks **Break the shop** (then later **Open the freezer door**), watches the trace, sees the cancel window, lets it run or clicks Approve. | `fix_applied` received for the shop (the freezer is optional). |
| **J-E Wrap-up** (modal on `/`) | What just happened, with the measured times. Links: the GitHub PR, the incident report, pair your phone, **Replay the demo**, **Advanced setup**. | Picks a next step or closes the modal. | `localStorage.ta_onboarded = "1"`. |

**Returning visitor** (`ta_onboarded` set) goes straight to Mission Control. A **"Guided demo"** button in the top bar restarts the journey at any time.

---

## 2. Decisions (agreed before building)

- **D1 · One demo world, two named systems.** The journey always uses **"AutoParts Lagos"** (software) and **"Cold-chain Freezer"** (appliance), tagged `demo: true`. The left pane already picks the *first* system of each kind (`LeftPane.tsx`). Duplicate demo systems would confuse it, so bootstrap is idempotent (J1).
- **D2 · Already armed by an earlier visitor?** The guided setup shows each stage as ✓ with **"Already set up — replay this step"**. The visitor can watch it or skip to the incident. We **never delete** the shared systems from the journey.
- **D3 · Real work, not a slideshow.** "Read the manuals" runs the **real extraction** on the server's copies of `demo/setup/coldchain_spec_sheet.pdf`, `coldchain_rating_plate.jpg` and `autoparts_ops_guide.md`. If extraction fails (no model key, timeout over 45 s), it falls back to the sample profile and **says so** ("Using the saved reading of these manuals").
- **D4 · Hosted demo permissions.** `/start/setup` sets each demo system's policy to `auto_fix_allowed: true` with the 20 s countdown. The visitor therefore never *needs* the token: the fix runs when the countdown ends. Approve/Disapprove buttons stay visible; without a token they show *"Operator only — the countdown will act for you"*. No token in the browser bundle, ever (G2 in `ui-roadmap.md`).
- **D5 · Routes.** New: `/welcome`, `/start`, `/start/setup`. Kept unchanged: `/` (Mission Control), `/setup` (now labelled **Advanced setup**), `/shop` (now labelled **Customer storefront**), `/incidents/[id]`, `/classic` (until the video is recorded), `/kit` (dev only).
- **D6 · First-visit redirect.** `/` redirects to `/welcome` **only** when `ta_onboarded` is unset **and** there's no `?tour` / `?skip` query. `?skip=1` sets the flag. This is how you get straight in when recording the video.
- **D7 · Words.** Visible copy changes (table in §5); **API fields, statuses and event kinds do not**.

---

## 3. Ground rules (don't break anything)

1. **Additive API only.** New endpoints live under `/api/demo/*`; existing request and response shapes stay as they are. `tests/test_api.py` must still pass untouched.
2. **Reuse, don't fork.** The guided setup calls the same endpoints as `/setup` (`POST /api/systems`, `/documents`, `/profile/confirm`, `/baseline/start`, `/arm`). Shared logic moves into `app/lib/setupApi.ts`; `/setup` keeps working exactly as it does now.
3. **The gate and veto are untouched.** No skipping arming, no auto-approving, no client-side shortcut that acts on a system that isn't armed.
4. **The full-demo button (Play scenario) and Reset keep working** for the video. Reset doesn't delete systems (that's already true).
5. **No secrets in `NEXT_PUBLIC_*`.** Build passes (`npm run build -w apps/web`), Python tests pass, before each push.
6. **Commits:** owner identity only, no AI/co-author trailers. Nothing pushed without Akingbade's OK.

---

## 4. Build steps with acceptance cases

Estimates assume one developer. Do them in order; each step ships on its own.

### J0 · Verify the learning gap (A7) — *30 min*
- Arm nothing. Create a software system in `/setup`, click **Start 2-minute learning**, wait for it to finish, and record the pattern count. Repeat for the appliance.
- **Accept:** the result is written in this file under §8. If the shop learns fewer than 3 patterns, J3 is a MUST, otherwise a SHOULD.

### J1 · Demo bootstrap API — *2 h* (`apps/api/main.py`, tests in `tests/test_api.py`)
- `POST /api/demo/bootstrap` → ensures the two `demo: true` systems exist (creates them if missing), returns `{shop: Profile, freezer: Profile}`. It's idempotent: calling it 5 times leaves exactly one of each.
- `GET /api/demo/status` → one call the journey polls: per system `status`, `baseline.status`, `baseline` %, `policy.auto_fix_allowed`, plus `scenario.playing`, the last run id, and whether a GitHub PR URL exists.
- **Accept:** a new test shows 5 bootstrap calls → `GET /api/systems` lists exactly 2 demo systems. Existing systems a user made in `/setup` are left alone.

### J2 · "Read the manuals" with server copies — *2 h*
- `POST /api/demo/{system_id}/documents` → feeds the server's demo files into the **same** extraction code path as `/documents`. It streams the same `setup_progress` events and returns the same body. On failure or timeout over 45 s it loads the sample profile and returns `fallback: true`.
- **Accept:** with a model key, the freezer profile shows values quoted from the PDF and photo (e.g. holding range 2–8 °C). Without a key, the response has `fallback: true` and the UI says so. Conflicts appear in the review stage exactly as in `/setup`.

### J3 · Learning that actually sees normal — *3 h*
- `POST /api/demo/{system_id}/learn` → calls the existing `baseline/start` (120 s), then drives **gentle** normal traffic server-side, ported from `accelerated_learn.py`:
  - **Shop:** low-rate load (1 shopper, ~2 orders/s, below the deadlock threshold) plus metrics observations.
  - **Freezer:** normal readings plus one defrost hump.
- It stops the traffic when the window ends.
- **Accept:** the shop learns at least 3 patterns and the freezer at least 3 (one of them a defrost). **No incident run starts during learning.** The shop isn't jammed afterwards (`GET /health` returns 200, and a test order succeeds). If the shop thread leak bites here, fix it first (see roadmap backlog).

### J4 · `/welcome` landing page — *2 h* (`apps/web/app/welcome/page.tsx`)
- Static and fast. Hero sentence, a 2-tile illustration (shop + freezer), the **Notice → Fix & prove → Ask, then act** strip, model credits (Muse Spark, Muse Spark Open on Baseten, Muse Wonder, Modal), CTA **Try the live demo** → `/start`, secondary **Watch 3-min video** (link set once recorded; hidden until then).
- `/` first-visit redirect per D6.
- **Accept:**
  - An incognito visit to `/` lands on `/welcome`.
  - `/?skip=1` lands on Mission Control and stays there on reload.
  - Lighthouse accessibility ≥ 90 on `/welcome`.
  - The page works when the API is down (it's static), and the CTA then shows "Demo is waking up…".

### J5 · `/start` onboarding — *2 h*
- 3 cards with Next/Back, keyboard and swipe support, plus a progress dots strip. Card 3 has the two path buttons (D5).
- **Accept:** a visitor reaches `/start/setup` in ≤ 3 clicks. **Connect my own system** never leads to a dead end: it shows the waitlist note plus an "Advanced setup" link.

### J6 · `/start/setup` guided setup — *6 h* (the big one)
One page with a vertical 4-stage stepper. Each stage acts on **both** systems in parallel, with one card per system showing live status. Stages unlock in order, and a finished stage collapses to a ✓ summary line.

| Stage | Button | Calls | Shows |
|---|---|---|---|
| ① Meet the business | **Set up my demo business** | `POST /api/demo/bootstrap` | Two cards: AutoParts Lagos (online parts shop, 3 services) and Cold-chain Freezer (vaccine and food storage, 2–8 °C). |
| ② Read the manuals | **Read the manuals** | `POST /api/demo/{id}/documents` ×2 | File chips (PDF, photo, ops guide) ticking through `setup_progress`. Then **3 highlighted facts per system**, each with its quote, e.g. *"Holding 2–8 °C" — spec sheet p.1*. "See everything it learned" opens the full review table, read-only, reusing the review section from `/setup`. |
| ③ Watch normal | **Watch normal for 2 min** | `POST /api/demo/{id}/learn` ×2 | Two progress rings (`baseline_progress`), a live count of patterns learned, and a line explaining *"It's learning that a defrost cycle and a cold cache look scary but are normal."* A **Skip (not recommended)** link is allowed. |
| ④ Permissions & start | **Start watching** | `PUT /profile` (D4 policy), `POST /profile/confirm` with `confirmed_by: "Demo visitor"`, then `POST /arm` ×2 | A plain-language summary: *"It may fix the shop on its own after a 20-second cancel window. It will alert, not act, on the freezer's hard limits."* Then a redirect to `/?tour=1`. |

- Conflicts (if extraction found any) appear inside stage ②, **pre-resolved to the safest value** with a "change" link. They never block the visitor.
- D2 behaviour: if a system is already armed, stage ① shows "Already running (set up by an earlier visitor)", with **Jump to the incident** plus **Replay setup** (replay runs ②–③ for display only, without disarming).
- **Accept:**
  - From a fresh API (`TA_DATA_DIR` wiped), a visitor goes from stage ① to `/?tour=1` with only the 4 primary clicks, in ≤ 4 min including the 2-minute learn.
  - Both systems end up `armed`.
  - `/setup` still shows both systems and can disarm and re-arm them.
  - The refresh test: reloading mid-stage resumes at the right stage from `GET /api/demo/status`.

### J7 · First-incident tour on `/` — *4 h* (`mission/Tour.tsx`)
A coach-mark rail (dismissable, keyboard reachable) driven by WebSocket events:

| # | Coach mark points at | Text | Advances on |
|---|---|---|---|
| 1 | Shop tile + storefront mini window | "This is AutoParts Lagos taking orders. Let's give it a rush hour." Button **Break the shop** → `POST /api/sim/shop/load` (8 shoppers, 30/s, 60 s) | `watcher_trigger` |
| 2 | Agent trace | "It noticed the errors itself — no one pressed anything. Now it's diagnosing with Muse Spark." | `AgentStep` diagnosis done |
| 3 | Trace verify step | "It wrote a fix **and** a test, and proved the test fails before the fix and passes after, in a sandbox." | verify PASS |
| 4 | Cancel window (veto ring) | "It will deploy in 20 s unless someone cancels. You're in control." | `action_resolved` / `fix_applied` |
| 5 | Shop tile turning green + PR link | "Fixed, verified, and a pull request is on GitHub." Button **Now try the freezer** → `POST /api/sim/fridge/fault {door_open}` | the appliance `action_resolved` or **Skip** |

- If verification fails and the agent retries, coach mark 3 says: *"First fix failed its test — it's learning from the failure and trying again."* That's honest and on-brand.
- Timeouts: if a step doesn't advance in 120 s, show "Taking longer than usual — keep watching or **Restart demo**". Restart calls the existing reset.
- **Accept:**
  - On a fresh, armed world the tour completes the shop path end to end, and the PR link opens.
  - Closing the tour mid-way leaves Mission Control fully usable.
  - `?tour=1` with systems *not* armed bounces to `/start/setup`.

### J8 · Wrap-up and navigation — *2 h*
- A wrap-up modal after tour step 5: the measured warning → fix time (already in the TopBar as `warnFixMs`), the number of attempts, **View pull request**, **Read incident report** (`/incidents/[id]`), **Get alerts on your phone** (opens the existing pair QR), **Replay the demo**, **Advanced setup**. It sets `ta_onboarded`.
- Top bar: add a text button **Guided demo** (→ `/start`) and a **Storefront ↗** link (→ `/shop`). Give the icon buttons short visible labels at ≥ 1280 px wide. Make **Play** disabled with a "Finish setup first" tooltip when nothing is armed (A3).
- `/shop` and `/setup` headers: a **Back to Mission Control** button plus the same "Guided demo" link.
- **Accept:** from any page a visitor can reach Mission Control, the storefront and the guided demo in one click. No icon-only control remains without a tooltip and an `aria-label`.

### J9 · Copy pass + clean-up — *2 h*
- Apply the vocabulary table (§5) to `/setup`, Mission Control and the tour.
- Fix A8: on `/setup` the "Confirmed by" field moves into the Policy step, so saving never bounces back.
- **Accept:** a review by someone who's never seen the app (ask a friend; 5 minutes, no hints). They can say what it does and can finish the journey. Write down where they hesitated and fix the top 2.

**Total ≈ 27 h.** Cut order if late: J9 copy polish → J8 label tweaks → J5 (fold the 3 cards into `/welcome`) → J2 fallback-only (sample profile with "Using saved reading" note). **Never cut** J1, J3 (if J0 says it's needed), J6 or J7. They *are* the journey.

---

## 5. Vocabulary (visible text only; code names stay)

| Today | Visitor sees |
|---|---|
| Connect / Teach / Review / Learn / Policy / Arm | Meet the business / Read the manuals / Check what it learned / Watch normal / Permissions / Start watching |
| Armed · Unarm | Watching · Stop watching |
| Setup needed | Not watching yet — set up |
| Gate: suppress / observe / act | Ignored as normal / Keeping an eye on it / Acting |
| Veto ring, countdown | Cancel window |
| Approve / Disapprove | Do it now / Cancel |
| Play scenario | Play full demo (2 min) |
| Reset world | Restart demo |
| Agent trace | Agent trace (keep; `ui-roadmap.md` G-rule) |
| `/setup` | Advanced setup |
| `/shop` | Customer storefront |

---

## 6. Schedule (today is Thu Oct 29)

| Day | Work |
|---|---|
| Thu Oct 29 | J0 check, J1 bootstrap + status, start J3 |
| Fri Oct 30 | Finish J3, J2, J4 landing |
| Sat Oct 31 | J6 guided setup |
| Sun Nov 1 | J7 tour, J5 onboarding |
| Mon Nov 2 | J8 + J9, full fresh-world run ×3 locally, deploy to Railway, run the journey on Railway |
| Tue Nov 3 | **Record the video following this exact journey** (it becomes the 3-minute script), backup take |
| Wed Nov 4 | Buffer, README "Try it" link to `/welcome`, submit before 9 PM ET |

Overlap with `ui-roadmap.md`: J4–J8 use its tokens and kit (`app/ui/*`). If that work is mid-flight, J screens follow its look; the journey order still comes from this file.

---

## 7. Risks

- **R1 · Shared hosted world (A11).** Two judges at once share one shop. Mitigation: D2 (never destructive). The tour's **Restart demo** is rate-limited to once per 60 s server-side. The landing page shows "Live demo — others may be watching the same shop". Real per-visitor worlds come after the hackathon.
- **R2 · PR spam.** Every visitor's incident opens a PR on `telemetryAgent-demo`. Mitigation: `/api/demo/*`-driven runs reuse one branch per hour (or cap at 1 new PR per 10 min). Otherwise "View pull request" links the latest open one.
- **R3 · Model and sandbox cost/latency on Railway.** Cold Modal start can take tens of seconds. Coach marks 2–3 explain the wait. Warm the sandbox on the bootstrap call.
- **R4 · Shop thread leak** (known: after heavy traffic every order returns 503 until restart). The tour **must** end with a working shop. Fix the leak or have `fix_applied` / `Restart demo` restart the shop worker. This is now on the journey's critical path.
- **R5 · Learning traffic triggers an incident.** J3 keeps the load gentle, and the gate already doesn't act while `learning`. J3's acceptance case covers this.
- **R6 · Wizard drift.** Two setup UIs (`/setup` and `/start/setup`) can drift. Mitigation: ground rule 2 (shared `setupApi.ts`), and both are covered by one e2e check in the J6 acceptance case.

---

## 8. Findings log (fill in while building)

- J0 result — shop patterns: 1 (metric band only, 0 log templates) · freezer patterns: 0 · J3 is MUST (45 s windows, zero traffic, Oct 29)
- J2 live (Oct 29): shop real extraction 24 s, quoted, no fallback. Freezer timed out at 45 s → sample fallback; direct re-run took 39.6 s real (metric "temperature" 2–5 °C, 6 failures). Model latency straddles the timeout — both outcomes show sourced facts, fallback stays honest. Fixed: extraction overwrote demo name/tags via ALLOWED_KEYS — demo endpoint now restores D1 identity.
- J3 live (Oct 29): shop 2 templates + 3 metric bands · freezer 3 sensors with defrost+normal modes · zero runs started · shop /health 200 + test order ok after.
- R4 fixed (Oct 29): wedged shop had ~4096 leaked lock threads → 500s with no log lines, so no incident could ever fire. Cure: race-safe late-release in `acquire_timed`, shop `POST /restart` (re-exec, keeps active inventory), best-effort restart on Reset demo + after verified deploy. Unit-tested; verified live (4097 → 4 threads, orders ok).
- Watcher quiet fix (Oct 29): suppressed candidates set no quiet — only started runs do — so the deadlock later in a retry-led storm still posts. The gate is untouched.
- J2 cut (Oct 29): the shop uses the saved reading (blessed fallback-only). Live ops-guide extraction yields loose retry signatures with no hard limits, so the gate suppressed the hero storm 194–0. The freezer keeps live reading. Plus: the candidate endpoint now passes ambient shop error_rate/durations into the gate (log candidates carry none), so hard limits and failure definitions evaluate.
- J7 E2E (Oct 29): trigger 23 s → diagnose 116 s → verify failed once, retried, PASS 194 s → fix applied 221 s → real PR opened (opens, HTTP 200) → shop on verified patch, test order ok. Freezer: door fault → temp-warning 8 s → run PASS → runbook auto-applied → door closed, 3.4 °C.
- R2 (Oct 29): one storm opened 5 concurrent runs/PRs (candidate POSTs time out after 10 s while the server keeps working, so the watcher saw no run_id). Fixed both halves: watcher quiets on post failure too, and `open_fix_pr` reuses a fresh PR URL within 10 min. Both unit-tested.
- J6 (Oct 29): fresh-world run 2.9 min incl. checks; both manuals read live (no fallback); stage-4 chain + /setup disarm/re-arm verified; per-stage renders + button-level order gating verified headless.
- Fresh-world journey time (local): 2.9 min · (Railway): ___
- First-time tester notes: ___

---

## 9. How this fits the other roadmaps

- `setup-roadmap.md` built the **engine** (profiles, extraction, gate, baseline). This file puts a **front door** on it; nothing there is redone.
- `simulation-roadmap.md` built the **world** (shop, freezer, scenario). The tour drives it with the existing `/api/sim/*` endpoints.
- `ui-roadmap.md` owns **how screens look**. This file owns **which screen comes when**.
- `mobile-roadmap.md`: the phone appears once, in the wrap-up ("Get alerts on your phone"). No mobile work is required for this journey.
- `demo/script.md`: after J7 ships, rewrite the video script to follow §1 (landing → setup → incident → wrap-up) so the video shows exactly what a real visitor gets.
