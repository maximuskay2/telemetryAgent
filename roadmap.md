# 🛡️ TelemetryAgent: Roadmap & Timetable

**Project Name:** TelemetryAgent  
**Track:** Indie Developer Track — Problem Statement: Push the Frontier  
**Scope:** Software-first autonomous SRE agent (~80% of effort) with a lightweight appliance-telemetry proof point (~20%) running through the same reasoning core.  
**Core Objective:** Ingest a crash log → **Muse Spark 1.3** finds the root cause → **Muse Spark Open** (Baseten) writes a patch and test → **Modal Sandbox** runs pytest → self-correct on failure → open a **real GitHub PR**. The same loop handles synthetic fridge telemetry, verified by a rule-based safety validator instead of pytest.

---

## ✅ Hackathon Compliance Checklist

- [x] Pipeline uses Meta models only: `muse-spark-1.3`, `muse-wonder-1.0` (Meta Model API) and `meta-models/muse-spark-open` (Baseten).
- [x] Repository is **public** with an MIT license.
- [x] Repository started fresh, so all code is built during the event.
- [ ] README lists everything **built during the hackathon** (Oct 27 – Nov 4).
- [ ] Demo video is **3 minutes** and shows only hackathon-built work.
- [ ] All code, data, and assets are ours or properly licensed.
- [ ] Every contributor (max 4) listed; one Representative submits.
- [ ] Submitted on the [CV platform](https://cerebralvalley.ai/e/meta-ai-developer-hackathon/hackathon/submit) before **Wed, Nov 4 @ 9:00 PM ET**.

---

## 🎯 Scope Rules

1. **Software loop first.** No appliance work starts until the software loop opens a real PR end to end (target: Oct 30).
2. **No physics simulator.** Appliance runbooks are verified by deterministic safety rules only.
3. **No hardware.** Appliance telemetry is synthetic, generated with injectable faults.
4. **SAM 3.1: cut.** The optional visual-confirmation step was cut at the Day 7 go/no-go.
5. **No overclaiming.** Say "verified fix" and "abnormal behavior detected early", never "zero hallucination" or "predicts failure".

---

## 🎯 Stage 2 Judging Rubric Alignment

| Rubric Category | Weight | How TelemetryAgent Scores |
| :--- | :--- | :--- |
| **Impact** | **30%** | Outage diagnosis and fix verification in minutes instead of hours; the same agent extends to physical equipment where failures spoil stock. |
| **Use of Meta AI Tooling** | **25%** | Model routing by job: Muse Spark diagnoses, Muse Spark Open generates, Muse Wonder escalates; structured output; feedback-driven self-correction. Built with Muse Code. |
| **Technical Depth & Execution** | **20%** | Typed two-domain telemetry contracts, sandboxed untrusted code, deterministic safety validation, bounded retries, real PRs, tests. |
| **Demo** | **25%** | Two incidents side by side: the software one ends in a real PR, the appliance one in an alert and work order. |

**Bonus prizes:** Best Agentic Use-Case ($5K), Best Build on Meta Open Weight Models ($10K), Most Viral Project ($20K), Community Vote ($10K).

---

## 🏗️ Architecture

```
   [ Software crash log ]            [ Appliance sensor window (synthetic) ]
             └──────────────┬──────────────┘
                            ▼
          muse-spark-1.3 — classify + diagnose
                            ▼
   muse-spark-open on Baseten (backup: Fireworks → muse-spark-1.3)
     software → patch + pytest        appliance → runbook
                            ▼
     software → pytest in Modal       appliance → safety rules
                            │
              FAIL ─────────┴───────── PASS
                ▼                        ▼
   retry with feedback (max 3,     software  → real GitHub PR
   last try on muse-wonder-1.0)    appliance → alert + work order
```

---

## 🗓️ Timetable (all times ET)

```
[Oct 26]          ──> Setup: credits, accounts, baseline tag
[Oct 27 - Oct 30] ──> Phase 1: Software loop end to end, real PR  (core, 80%)
[Oct 31]          ──> Phase 2: Dashboard + streaming
[Nov 01 - Nov 02] ──> Phase 3: Appliance path + hardening          (20%)
[Nov 03 - Nov 04] ──> Phase 4: Demo video, README, submission
[Nov 05 - Nov 09] ──> Judging, X engagement, closing ceremony
```

### Live sessions and support

| Date | Session |
| :--- | :--- |
| Tue, Oct 27 · 12:00 PM | Agents 101: Build a Multimodal AI Agent |
| Wed, Oct 28 · 12:00 PM | Agents 102: Best Practices for Verifiable Agents (core to our verify loop) |
| Fri, Oct 30 · 12:00 PM | Building Specialized Intelligence on Fireworks with Muse Open Models |
| Weekdays · 10–11 AM | Meta office hours in Discord `#office-hours` |
| Tue, Nov 3 | Last full day for submission and technical questions |

---

### 📍 Daily Task Breakdown

#### **Day 0: Mon, Oct 26 — Setup**
- [x] Start the repository fresh.
- [ ] Watch the kickoff; join the [Discord](https://cerebralvalley.ai/e/meta-ai-developer-hackathon/discord).
- [ ] Claim **$150 Meta Model API credits** ([form](https://docs.google.com/forms/d/e/1FAIpQLScam78z7tHsNYibiFyJQVFzEgr0coyBTiY568SxxNbsPa3jiw/viewform)); add a card and set a spend limit.
- [ ] Request [Baseten](https://docs.google.com/forms/d/e/1FAIpQLSfM7gcK8yMZEmAGq6DbTyiuv2c71IH7CKCy0fXGIfUED1qxVQ/viewform), [Modal](https://docs.google.com/forms/d/e/1FAIpQLSe_GDPtLZsdA57xPhFcOCi_yLjPf8HRxMIQJ5V7ystoKSqWCQ/viewform), and [Fireworks](https://docs.google.com/forms/d/e/1FAIpQLSdPQTTES8_nhavzZkOrebVNYbM1FumWLdpeZx8ZSNe4QLXKPA/viewform) credits.
- [x] Install Muse Code (`curl -fsSL https://dev.meta.ai/install.sh | sh`, then `muse`).
- [x] Make the GitHub repo public.
- [x] Decide the deploy host for the live demo → Railway (public API + web URL for judges).
- [x] Hygiene: first event commit dated ≥ Oct 27 (`95b2cb9`, Oct 27); `pre-hackathon` tag confirmed present.

#### **Day 1: Tue, Oct 27 — Diagnosis on Meta Model API**
- [x] Reconcile the scaffold to the target layout (`telemetry.py`/`remediation.py`, `verify/sandbox.py`, shared `run_loop` core, `samples/`); first commit of event work.
- [x] Confirm `.env.example` covers `MODEL_API_KEY`, `BASETEN_API_KEY`, `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET`, `GITHUB_TOKEN`, optional `FIREWORKS_*`.
- [x] Confirm `core/schemas/telemetry.py` (software/appliance union) and `core/schemas/remediation.py` (patch, runbook, verification result).
- [x] Confirm the FastAPI app (`apps/api/main.py`) ingests logs and relays the WebSocket stream.
- [x] Confirm `core/infer/meta_client.py` diagnoses via `muse-spark-1.3` with structured output behind `/api/diagnose`.
- [x] Verify with a deadlock sample from `samples/` (live run passed Oct 27: Muse Spark diagnosis, Muse Spark Open patch, 14 tests passed in Modal).
- [ ] Attend Agents 101.
- Exit: deadlock sample in → valid `Diagnosis` out via the Meta API.

#### **Day 2: Wed, Oct 28 — Patch generation**
- [x] Build `core/infer/baseten_client.py` (`meta-models/muse-spark-open`).
- [x] Build `core/infer/fireworks_client.py` backup and the failover chain (Baseten → Fireworks → `muse-spark-1.3`).
- [x] Create `demo/target-service/` with a seeded, reproducible bug (e.g. lock-ordering deadlock) and a minimal test suite.
- [ ] Create the demo-target repo + fine-grained `GITHUB_TOKEN` (`contents`, `pull_requests` write).
- [x] Dashboard skeleton with mock events (parallel frontend track).
- [ ] Attend Agents 102 and apply its verifiable-agent practices.
- Exit: diagnosis in → `GeneratedPatch` JSON out via Baseten; failover verified by unsetting the key.

#### **Day 3: Thu, Oct 29 — Modal Sandbox verification**
- [x] Build `core/verify/sandbox.py`: write patch + test into a Modal Sandbox, run pytest, return pass/fail and feedback.
- [x] Require the generated test to **fail on the original code and pass on the patch**, so a test cannot simply agree with its own fix.
- [x] Timeouts on every sandbox; generated code never runs outside it.
- [ ] Measure sandbox cold-start; note the pacing for the demo script.
- [x] Contingency trigger: no Modal access by EOD → develop against a local Docker pytest runner (`core/verify/local_runner.py`, auto-fallback in `verify_patch`).
- Exit: seeded test fails on original code, passes on patch, everything inside the sandbox.

#### **Day 4: Fri, Oct 30 — Closed loop + real PR** *(software milestone)*
- [x] Build `core/agent/loop.py`: diagnose → generate → verify → retry with feedback (max 3), final attempt on `muse-wonder-1.0`.
- [x] Build `core/actions/github_pr.py`: branch, commit, open a PR on the demo target repo with diagnosis, test output, and attempt count.
- [ ] End-to-end run: deadlock log in → real PR out.
- [x] Unit tests for the loop with mocked model clients.
- [x] Record per-stage durations in stream events for the dashboard.

#### **Day 5: Sat, Oct 31 — Dashboard**
- [x] Next.js dashboard with two incident panels (software, appliance) on the Day 2 skeleton, each showing: incoming telemetry, diagnosis, generated fix, verification result, final action.
- [x] FastAPI WebSocket streaming of every loop step, including which model and provider served it.
- [x] "Inject incident" buttons for both domains.
- [x] Deploy API + web to the public demo URL.
- Exit: inject → both panels update live over the socket on the public URL. ✅ Live on Railway 2026-10-27: API `https://api-production-0c9a.up.railway.app` (health 200, fridge ticking), web `https://web-production-926b3.up.railway.app` (serves, baked API URL verified in bundle, CORS open).

#### **Day 6: Sun, Nov 1 — Appliance path** *(20% scope starts)*
- [x] Build `core/simulate/appliance.py`: synthetic fridge/freezer readings (temperature, current, vibration, door events) with injectable faults: door left open, condenser fouling (longer runs, higher current), power-back surge, rapid restart.
- [x] Route appliance windows through the same `muse-spark-1.3` diagnosis.
- [x] Generate runbooks with Muse Spark Open.
- [x] Build `core/verify/safety_rules.py` and plug it into the shared loop.
- [x] Draft the demo script.
- Exit: each injectable fault → correct alert + validated runbook.

#### **Day 7: Mon, Nov 2 — Appliance actions + hardening**
- [x] SAM go/no-go at start of day → CUT: skipping the optional visual-confirmation step.
- [x] Build `core/actions/notify.py`: SMS alert and work-order stub shown in the dashboard.
- [ ] ~~Optional, only if everything above works: one SAM 3.1 call confirming a visual symptom (e.g. ice build-up) in a single image.~~ CUT (see go/no-go above).
- [x] Harden error handling (`401`, `404 model_not_found`, rate limits, provider failover) and input limits.
- [ ] Record a rough-cut video; pre-capture backup footage of a known-good run.

#### **Day 8: Tue, Nov 3 — Demo video & README**
- [ ] Record and edit the **3-minute** video: both incidents side by side; the software PR shown live on GitHub; callouts for Muse Spark, Muse Spark Open, Muse Wonder, Modal, and Muse Code.
- [ ] README: architecture, setup, models used, and the "Built during the hackathon" list.
- [ ] Ask remaining submission questions in Discord.

#### **Day 9: Wed, Nov 4 — Submission**
- [ ] Final end-to-end run from a clean clone.
- [ ] Confirm the repo and video are public and all contributors are listed.
- [ ] Confirm the public demo URL is live for judges.
- [ ] Submit on the [CV platform](https://cerebralvalley.ai/e/meta-ai-developer-hackathon/hackathon/submit) before **9:00 PM ET**.
- [ ] Post the demo on X and submit the link for Most Viral Project.

#### **Nov 5 – Nov 9 — Judging & Closing**
- [ ] Keep the live demo running.
- [ ] Promote the X post (counted until Nov 8 EOD) and the community vote.
- [ ] Closing ceremony: Mon, Nov 9 at 12:00 PM ET.

---

## 🎨 UI: Incident Command Center

Replaces the current terminal-style dashboard (stacked `<pre>` boxes + raw log list), which shows data but no story and is hard to read on a 1080p video. The new UI shows **what's happening** (live shop + fridge) beside **what the agent is doing** (incidents moving through the five steps), and each incident opens a readable report.

Decisions: **dark mission-control theme**, **Command Center layout**.

```
┌───────────────────────────────────────────────────────────────────────────────┐
│ TelemetryAgent   ● All systems  ⚠ 1 incident   Muse Spark · Spark Open ·     │
│                                                Wonder · Modal   [▶ Play] [↺] │
├──────────────────────────────────────┬────────────────────────────────────────┤
│  WORLD: what's happening              │  AGENT: what it's doing                │
│  Shop tile: service map + metrics     │  Incident cards:                       │
│  Fridge tile: animated fridge,        │  CRASH → GRAB → SUGGEST → VERIFY → FIX │
│  gauges, temp chart, fault buttons    │  click → detail drawer                 │
├──────────────────────────────────────┴────────────────────────────────────────┤
│ ACTIVITY: plain-English feed ("Watcher caught 3 retries on brake-pad")        │
└───────────────────────────────────────────────────────────────────────────────┘
```

### Design rules
- **Colour = meaning:** green healthy · amber warning (early catch) · red incident · **violet = AI / Meta model activity**.
- **Type:** Inter/Geist sans everywhere; monospace only for code and logs.
- **Built for video:** large numbers and labels readable at 1080p; **Focus mode** enlarges the running incident.
- **Motion only for real events:** order dots, fridge door/compressor, step lane filling, charts.
- **Human language:** the activity feed and stage text read as sentences, not `step=verify status=ok`.

### Pages

| Page | Purpose | Plugs into |
| :--- | :--- | :--- |
| `/` Command Center | Main demo screen | `WS /api/ws` (`AgentStep`, `SimEvent`), Sim 3, Sim 4 |
| `/shop` AutoParts Lagos | Customer shop that visibly breaks | Sim 1 |
| `/incidents/[id]` | Shareable incident report | `ExecutionResult` / `ApplianceResult` by `run_id` |
| `/alert/[id]` | Phone-friendly owner alert | Mobile Extras (next version) |
| Upload modal | Drop a `.log` or paste an error | Log Ingestion I1 |

### Stack
Tailwind CSS + shadcn/ui (cards, drawer, badges), Recharts (live charts), Framer Motion (transitions), react-diff-viewer (before/after code), hand-built SVG for the service map and fridge. Keep Next.js and the existing `NEXT_PUBLIC_API_URL`.

### U0 — Foundation *(Wed, Oct 28 · ~3 h)*
- [ ] Add Tailwind + shadcn/ui to `apps/web`; dark theme tokens (status colours + violet AI accent); Inter/Geist fonts.
- [ ] Extract socket handling from `page.tsx` into a `useAgentStream()` hook (reuses `applyStep`; adds `SimEvent` handling once Sim 0 lands).
- [ ] App shell: top bar (connection, open incidents, model chips, Play/Reset placeholders), two-column body, activity bar.
- [ ] Old panels stay reachable at `/classic` until the new screen is complete.
- Exit: new shell renders live `AgentStep`s from the existing API with no backend changes.

### U1 — Incident cards + activity feed *(Thu, Oct 29 · ~4 h)*
- [ ] `IncidentCard`: domain icon, status, elapsed timer, five-step lane (software: VERIFY; appliance: SAFETY), one-line current activity, source badge (Watcher / Manual / Upload).
- [ ] Incident list keyed by `run_id` (supports several runs, not one per panel).
- [ ] `ActivityFeed`: map `AgentStep` / `SimEvent` to plain sentences with model tags in violet.
- [ ] Upload modal (Log Ingestion I1) and the existing inject buttons as "Manual incident" actions.
- Exit: injecting either incident adds a card that fills its lane live.

### U2 — Incident detail drawer + report page *(Fri, Oct 30 · ~5 h)*
- [ ] Diagnosis card (summary, likely cause, confidence, model).
- [ ] Code diff: original `inventory.py` vs verified patch (react-diff-viewer), fix line highlighted.
- [ ] Tests panel: fail on original → pass on patch, test counts, Modal duration.
- [ ] Attempts timeline: provider per attempt, retry feedback, Muse Wonder escalation.
- [ ] Result: "View PR on GitHub" button, or work-order card + runbook checklist with a safety badge per step.
- [ ] API: `GET /api/runs/{run_id}` returning the stored result + steps (small in-memory store in `apps/api/main.py`).
- [ ] Same content at `/incidents/[id]` for sharing.
- Exit: every finished incident opens a readable report without looking at raw JSON.

### U3 — World tiles *(Oct 30–31, built with Sim 3 and Sim 4)*
- [ ] Shop tile: `ServiceMap` (Sim 3) + orders/min, error rate, p95 sparklines (Recharts).
- [ ] Fridge tile: `VirtualFridge` SVG (Sim 4) + °C / A / g gauges, temperature chart, fault buttons, "Technician applies runbook" (Sim 5).
- [ ] `/shop` page restyled to match (Sim 1).
- Exit: during a scenario, the world tiles show the failure and recovery the agent cards describe.

### U4 — Demo polish *(Sat, Nov 1 · ~3 h)*
- [ ] Focus mode (auto-enlarge the active incident; toggle with `F`).
- [ ] "First warning → verified fix" timer on each card.
- [ ] Wire Play / Reset to Sim 6's scenario timeline.
- [ ] Empty, loading, and error states (API down, missing key → readable message, not a blank panel).
- [ ] Check at 1920×1080 and 1280×720; remove `/classic`.
- Exit: the full scenario records cleanly in one take.

---

## 📥 Log Ingestion: How Incidents Reach the Agent

Today both inputs are demo data: the dashboard sends a hard-coded deadlock log, and appliance readings are generated per click. This track gives the agent real ways to receive logs, so it reacts to early warnings (retries, lock timeouts) before a full crash, not only after one.

Three ingestion modes, all feeding the same `POST /api/run` loop:

| Mode | How it works | Hackathon scope |
| :--- | :--- | :--- |
| **Upload / paste** | Engineer drops a `.log` file or pastes a traceback into the dashboard | Build (I1) |
| **Log watcher** | Small process next to the service tails its log and auto-sends error windows | Build (I2–I3) |
| **Webhooks** | Sentry / Datadog / Railway call `POST /api/webhooks/<source>` on new errors | Next version (I5) |

Trigger levels the watcher understands:

| Level | Example signal | Agent acts |
| :--- | :--- | :--- |
| Warning | `WARNING retry=`, `lock wait timeout`, rising latency | Before the crash (prevent) |
| Error | `ERROR`, `Deadlock detected`, `Traceback` | At failure |
| Crash | process exit, health check down | After (fix + prevent recurrence) |

### I1 — Upload & paste in the dashboard *(Thu, Oct 29 · ~2 h)*
- [x] Add a log panel to the software incident: file picker (`.log`, `.txt`) + paste textarea; "Load sample" fills it with `samples/database_deadlock.log`.
- [x] Client-side limit (e.g. 200 KB) with a clear message; keep only the last N lines if larger.
- [x] `POST /api/run` with the user's `log_text` instead of the hard-coded `DEADLOCK_SAMPLE`.
- [x] API: reject empty or oversized `log_text` with `422` and a readable error.
- [x] Tests: API accepts pasted logs; oversized input rejected.
- Exit: any pasted or uploaded log runs the full loop from the dashboard.

### I2 — Connect the real buggy service *(Thu, Oct 29 · ~2 h)*
- [x] When the log matches the demo target, send `demo/target-service/inventory.py` as `original_code` so verification is **fail-to-pass against the real file**, not code the model invented.
- [x] Add an optional "Target file" field in the API (`target_path`), resolved only inside an allowlisted directory (`demo/target-service/`); never read arbitrary paths.
- [x] PR from `core/actions/github_pr.py` modifies `inventory.py` itself.
- [x] Tests: loop passes `original_code`; path outside the allowlist rejected.
- Exit: generated test fails on `inventory.py`, passes on the patch; PR diff touches the real file.

### I3 — Log watcher (autonomous trigger) *(Fri, Oct 30 · ~4 h)*
- [x] Build `core/watch/` runnable as `python -m core.watch --file <log> --api http://localhost:8001`.
- [x] Tail the file (handle rotation and truncation); match trigger patterns (warning, error, crash) from a small config.
- [x] Collect a context window (e.g. 30 lines before + 10 after the trigger) and send it to `POST /api/run`.
- [x] Debounce: one incident per fingerprint (error type + location) per N minutes, so a retry storm opens one run, not fifty.
- [x] Add `source` (`upload`, `watcher`, `webhook`) to the run so the dashboard shows how the incident arrived.
- [x] Tests: pattern matching, context window, debounce, rotation.
- Exit: appending a deadlock to a watched file starts a run with no clicks.

### I4 — Live demo service *(Sat, Oct 31 · ~2 h, alongside the dashboard day)*
- [x] Add `demo/target-service/run_service.py`: runs `inventory.py` under concurrent load and writes realistic logs (retries, then deadlock) to `demo/target-service/logs/service.log`.
- [x] Demo script: start the service → watcher catches the early `WARNING retry` lines → dashboard lights up → verified fix → PR appears, with nobody clicking.
- [x] Dashboard badge "Detected by watcher" and the time from first warning to verified fix.
- Exit: one command starts the service, the watcher, and the agent; the incident runs end to end on its own.

### I5 — Webhooks *(next version, after submission unless time allows)*
- [ ] `POST /api/webhooks/sentry` (and Railway / Datadog later): verify the signature, map the event to `log_text`, start a run.
- [ ] Document setup in the README as the production path: no install needed on the customer's servers.

Order matters: I1 and I2 make the core demo honest; I3 and I4 make it autonomous; I5 is the production story for the README and video narration.

> **Superseded:** I2–I4 are now planned in detail, with the visual shop, service map and virtual fridge, in [`simulation-roadmap.md`](simulation-roadmap.md). I1 and I5 stay here.

---

## 🎨 UI: Incident Command Center

Parallel track with [`simulation-roadmap.md`](simulation-roadmap.md): one screen where judges watch both systems break, get caught, and recover. The shop tile, service map, and fridge from Sim 1–4 become this screen's "World" column (U3); pipeline lanes become its incident cards (U1).

Layout: `World` column (live systems) + `Incidents` column (pipeline lanes + detail). Existing panels keep working until the cutover, then become the detail view.

### U0 — Shell + layout *(Oct 28 · ~2 h)*
- [ ] Command-center grid: World column + Incidents column; responsive down to laptop widths.
- [ ] Tab or toggle between the classic panels and the command center during the transition.
- [ ] Keep `applyStep`/`Stage` as the shared state core; no second event path.
- Exit: empty shell renders with live socket status; old panels untouched.

### U1 — Incident cards *(Oct 29 · ~3 h)*
- [ ] Card per active incident with the CRASH → GRAB → SUGGEST → VERIFY → FIX stepper (extends `PipelineLane.tsx` from Sim 3).
- [ ] Badges: source ("Detected by watcher" / "Manual"), model tags, warning → verified-fix timer.
- [ ] Click a card to open its detail below (U2).
- Exit: a watcher run advances its card step by step with no clicks.

### U2 — Incident detail *(Oct 30 · ~2 h)*
- [ ] Detail view per selected incident: telemetry, diagnosis, suggestions, generated fix, verification, final action (reuse `Stage`).
- [ ] Software detail shows the PR link and diff summary once opened; appliance detail shows alert + work order.
- [ ] Live event feed stays visible alongside.
- Exit: every field the classic panels showed is reachable from a card.

### U3 — World column *(Oct 31 · ~3 h, needs Sim 1+4)*
- [ ] Shop tile: live orders/min, error rate, Buy button; red while the shop fails, green after the fix.
- [ ] Service map embed (`ServiceMap.tsx`): deadlock cycle highlighted during the incident.
- [ ] Fridge embed (`VirtualFridge.tsx`): gauges, chart, fault buttons.
- Exit: breakage and recovery are visible in the World column before reading any text.

### U4 — Polish + cutover *(Nov 1 · ~2 h)*
- [ ] Toasts for key transitions (grabbed, verified, PR opened, recovered); error-rate sparkline on the shop tile.
- [ ] Reduced-motion support; keyboard-accessible cards and buttons.
- [ ] Cut over: command center becomes `/`; classic panels move to `/classic` for backup footage.
- Exit: full scenario runs end to end on the command center alone.

---

## 📱 Mobile: On-Call Companion (Flutter)

Planned in [`mobile-roadmap.md`](mobile-roadmap.md): a Flutter app for **alerts and reports**. Verified incidents trigger a full-screen alarm (loud sound, strong vibration) with a **20-second server-side countdown**: tap Disapprove to cancel, otherwise the verified fix is applied automatically. Only verified fixes and safety-passed runbooks can auto-apply. Built in parallel (M0–M6, Oct 28 – Nov 3) on the existing `WS /api/ws` stream and Sim 5 endpoints; it must not delay the web Command Center or the simulation. The web dashboard remains the main product.

---

## 📄 Submission Quick-Sheet

* **Project Title:** TelemetryAgent
* **Track:** Indie Developer
* **Problem Statement:** Push the Frontier
* **One-Liner:**  
  *An autonomous SRE agent on Meta's Muse models that diagnoses crashes, writes fixes with the open-weight Muse Spark Open, proves them in a Modal sandbox, and opens the PR — and the same reasoning core diagnoses physical equipment.*
* **Meta models used:** `muse-spark-1.3`, `muse-wonder-1.0` (Meta Model API); `meta-models/muse-spark-open` (Baseten); Muse Code for development.
* **Partners used:** Baseten (primary generation), Modal (sandbox verification), Fireworks (backup generation).
* **Built during the hackathon:** the entire repository (started fresh for the event).
* **Required links:** public GitHub repo, 3-minute demo video, X post link.
