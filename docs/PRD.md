# TelemetryAgent — Product Requirements Document (PRD)

| | |
| :--- | :--- |
| **Product** | TelemetryAgent: autonomous SRE agent for software and physical equipment |
| **Owner** | Akingbade Kayode — Maximusinfotech Services (Nigeria) |
| **Event** | [Meta Global AI Developer Hackathon](https://cerebralvalley.ai/e/meta-ai-developer-hackathon/details) — Indie Developer track, *Push the Frontier* |
| **Build window** | Oct 27 – Nov 4, 2026 |
| **Submission deadline** | Wed, Nov 4, 2026 @ 9:00 PM ET |
| **Repository** | [github.com/maximuskay2/telemetryAgent](https://github.com/maximuskay2/telemetryAgent) (public, MIT) |
| **Status of this doc** | Living document; consolidates `about.md`, `roadmap.md`, `simulation-roadmap.md`, `mobile-roadmap.md`, `setup-roadmap.md` as of Oct 28, 2026 |

---

## 1. Summary

TelemetryAgent watches running systems, notices when something is really wrong, works out why, writes a fix, **proves the fix works** before anyone applies it, and then applies it — with a human able to veto from their phone.

The same reasoning core handles two kinds of system:

- **Software (≈80% of effort):** a crash or early-warning log → **Muse Spark** diagnosis → **Muse Spark Open** writes a code patch and a regression test → the test runs in an isolated **Modal Sandbox** (must fail on the old code and pass on the new) → a **GitHub pull request** and a hot-swap of the running service.
- **Physical equipment (≈20%):** a cold-chain fridge's sensor stream (temperature, current, vibration, door) → the same diagnosis → a **runbook** → deterministic **safety rules** → an alert, a work order, and (in simulation) the runbook applied.

The product loop is: **Crash → Grab → Suggest → Verify → Fix.**

## 2. Problem

1. **Outages are slow to fix.** An engineer has to notice the alert, find the right logs, reproduce the bug, write a fix, test it and ship it. That takes hours; customers feel every minute.
2. **AI-written fixes are not trustworthy by default.** A model can produce a plausible patch that doesn't work, or a test that agrees with its own wrong fix.
3. **Equipment failures are noticed too late.** A fridge with a stuck door or a fouled condenser is usually found when the stock has already spoiled.
4. **Monitoring is noisy.** Rules like "any ERROR line" or "temperature above 5 °C" fire on normal behaviour (a defrost cycle, a deploy, a compressor starting). Acting on those breaks working systems and trains people to ignore alerts.

## 3. Goals and non-goals

### Goals
- **G1 — Minutes, not hours:** from first warning to a verified fix in under ~2 minutes for the demo incidents.
- **G2 — Verified, not plausible:** no fix is applied unless it passed verification (fail-to-pass tests for code; safety rules for runbooks).
- **G3 — Autonomous but vetoable:** the agent acts on its own, but a human gets a loud, unmissable 20-second window to stop it.
- **G4 — Knows what normal is:** the owner teaches the system its normal behaviour from manufacturer/developer documents, so normal-but-scary behaviour is ignored with a cited reason.
- **G5 — One core, two domains:** the same loop serves software and equipment.
- **G6 — Hackathon-ready:** Meta models only, public repo, 3-minute video, public demo URL.

### Non-goals (for this build)
- Real hardware installed in a real fridge (a Wokwi ESP32 simulation is a bonus clip only).
- A physics simulator for appliances (safety rules are deterministic bounds).
- Multi-tenant SaaS, billing, user accounts.
- Webhook ingestion from Sentry/Datadog/Railway (documented as the production path; not built).
- Claims like "zero hallucination" or "predicts failure". We say **"verified fix"** and **"abnormal behaviour detected early"**.

## 4. Users

| Persona | Who | What they need |
| :--- | :--- | :--- |
| **On-call engineer** | Developer/SRE responsible for a service | Be woken only for real incidents; see the diagnosis, the fix and the test proof; approve or veto quickly |
| **Equipment owner / operator** | Shop or warehouse owner with cold-chain fridges | Know early when equipment misbehaves; get a clear runbook and a work order; never have a safe-but-scary cycle trigger an alarm |
| **Technician** | Field service for appliances | A work order with the diagnosis and a step-by-step, safety-checked runbook |
| **System setup owner** | Manufacturer, developer or owner onboarding a system | Upload spec sheets/ops docs once; review what was extracted; set the policy |
| **Hackathon judge** | Meta / partner reviewers | See a real system break, get caught and recover, with Meta models clearly doing the work |

## 5. User journeys

### J1 — Software incident (autonomous)
1. The AutoParts Lagos shop is under load; a lock-ordering bug causes retries, then deadlocks. Orders fail; the error rate climbs.
2. The **log watcher** catches the retry cluster / deadlock lines and sends the context window to the **gate**.
3. The gate confirms it's not expected behaviour and there's real impact → **act**.
4. Muse Spark diagnoses; Muse Spark Open writes a patch and a test; the sandbox shows the test fails on the original `inventory.py` and passes on the patch. Retries feed failures back (max 3, last attempt on Muse Wonder).
5. A PR is opened on GitHub. The phone alarms with a 20 s countdown.
6. No veto → the server hot-swaps the verified module into the shop; the error rate returns to 0%.

### J2 — Appliance incident (autonomous)
1. The cold-chain fridge door is left open (or the condenser fouls, or a defrost gets stuck). Temperature climbs.
2. The **sensor watcher** catches it; the gate checks expected behaviours, mode and impact → **act**.
3. Muse Spark classifies the sensor window; Muse Spark Open writes a runbook; safety rules check it against hard bounds (and the profile's forbidden actions).
4. Alert + work order are raised; the phone alarms with a countdown; the runbook is applied in simulation; the temperature recovers.

### J3 — Normal but scary (ignored, with a reason)
1. The fridge runs its scheduled **defrost**; temperature rises to ~7 °C.
2. The gate matches it to the profile's expected behaviour → **suppress**: "Expected: defrost (spec sheet p.2)". No incident, no phone alarm.
3. Same for a compressor start current spike, a 90 s restocking door-open, a shop deploy's drain retries, or the shop's startup `cache cold` warning.

### J4 — Setup ("teach it normal")
1. Open `/setup`. Pick the system type and how data arrives.
2. Upload a spec-sheet PDF, a rating-plate photo, an ops guide, or paste text (or load a sample profile).
3. Review the extracted profile: every value shows its source quote and page; conflicts must be resolved by a human; hard limits and policy are human-only.
4. Learn a baseline (accelerated for the demo). Set policy (auto-fix on/off, countdown). **Arm.**

### J5 — Veto from the phone
1. A verified action opens a server-owned 20 s window; the Android phone shows a full-screen alarm with loud sound and strong vibration, even when locked.
2. **Disapprove** before the deadline always wins; **Approve now** applies immediately; silence auto-applies at 0 s. Late decisions get `409` and the phone shows what already happened.

## 6. Functional requirements

Status: ✅ built · 🟡 partially built / in progress · ⬜ not built · ✋ manual task

### 6.1 Ingestion and detection
| ID | Requirement | Status |
| :--- | :--- | :--- |
| FR-1 | Accept a pasted/uploaded log in the dashboard (size-limited, 422 on empty/oversized) | ✅ |
| FR-2 | Log watcher tails a log file (rotation/truncation safe), detects warning/error/crash patterns and retry clusters, sends a context window (before/after lines) | ✅ |
| FR-3 | One traffic burst opens one run (per-fingerprint debounce + quiet period after a run) | ✅ |
| FR-4 | Sensor watcher evaluates every fridge reading against temperature/current rules | ✅ |
| FR-5 | Watcher forwards WARNING/ERROR lines to the dashboard stream (rate-limited) | ✅ |
| FR-6 | Webhook ingestion (Sentry/Datadog/Railway) | ⬜ next version |

### 6.2 Setup and the gate ("know what normal looks like")
| ID | Requirement | Status |
| :--- | :--- | :--- |
| FR-10 | System Profile per system: environment, normal ranges, expected behaviours, modes, failure definitions, hard limits, policy, baseline; provenance on every value; versioned | ✅ |
| FR-11 | Upload PDF / image / text; extraction quotes the source for every value, leaves unknowns empty, flags conflicts | ✅ |
| FR-12 | Documents can never set policy or hard limits (prompt-injection guard) | ✅ |
| FR-13 | 6-step setup wizard at `/setup` (connect → upload → review → baseline → policy → arm); "load sample profile" fallback | ✅ |
| FR-14 | Modes (defrost, deploy, maintenance…) from device, schedule, or human; max duration; overrun becomes an anomaly | ✅ |
| FR-15 | Gate order: hard limit → armed? → expected behaviour → mode → baseline → proof of impact; decisions `suppress` / `observe` / `act` with reason + citation | ✅ |
| FR-16 | Baseline learning (log templates, per-mode sensor bands, shop metrics); watchers never act while learning | ✅ |
| FR-17 | "This is normal" feedback from dashboard/phone, effective only after profile-review confirmation; hard limits can't be marked normal | ✅ |
| FR-18 | Diagnosis receives a profile summary; "expected" diagnoses end as `NO_ACTION` | ✅ |

### 6.3 Diagnose, generate, verify
| ID | Requirement | Status |
| :--- | :--- | :--- |
| FR-20 | Diagnosis with `muse-spark-1.3`, structured JSON output (summary, likely cause, suggested actions, confidence, expected flag) | ✅ |
| FR-21 | Patch + pytest generation with `meta-models/muse-spark-open` on Baseten; failover Baseten → Fireworks → Meta | ✅ |
| FR-22 | Self-correction: failure output fed back, max 3 attempts, final attempt on `muse-wonder-1.0` | ✅ |
| FR-23 | Generated code runs only in a sandbox (Modal; local Docker fallback with no network, memory/CPU/pid limits) | ✅ |
| FR-24 | Fail-to-pass: the generated test must fail on the real original file and pass on the patch | ✅ |
| FR-25 | If no test can fail on the original → "possibly intended, needs human"; no auto-action | ✅ |
| FR-26 | Appliance runbooks validated by deterministic safety rules + profile forbidden actions; violations fed back | ✅ |

### 6.4 Act
| ID | Requirement | Status |
| :--- | :--- | :--- |
| FR-30 | Open a real GitHub PR on the demo repo (branch, commit, PR body with diagnosis, test output, attempts) | 🟡 code built; needs `GITHUB_TOKEN` + demo repo (✋) |
| FR-31 | Shop hot-swap of the verified module (allowlisted path only) | ✅ |
| FR-32 | Appliance alert + work order; runbook applied to the virtual fridge | ✅ |
| FR-33 | Server-owned 20 s veto window; auto-apply at deadline; approve/disapprove endpoints; first decision wins; late → 409; kill switch; audit record | ✅ |
| FR-34 | Auto-apply only if verified **and** gate said `act` **and** profile policy allows auto-fix | ✅ |

### 6.5 Interfaces
| ID | Requirement | Status |
| :--- | :--- | :--- |
| FR-40 | Web dashboard: software + appliance lanes, service map, shop metrics + Start traffic, virtual fridge, stream feed, Play scenario / Reset, pair-phone QR | ✅ |
| FR-41 | `/shop` customer storefront that visibly fails | ✅ |
| FR-42 | Command Center redesign (Tailwind/shadcn, incident cards, detail drawer, `/incidents/[id]`) | 🟡 activity feed done; U0–U4 mostly open |
| FR-43 | Flutter app (Android first): QR pairing, live feed, full-screen alarm (sound + vibration), countdown, reports with decision record, test alarm | ✅ |
| FR-44 | Push notifications via FCM when the app is fully closed | ⬜ (foreground service covers the demo) |

### 6.6 Simulation (for the demo)
| ID | Requirement | Status |
| :--- | :--- | :--- |
| FR-50 | AutoParts Lagos shop with a real lock-ordering deadlock, load generator, metrics | ✅ |
| FR-51 | Virtual fridge stream with faults (door open, condenser fouling, power surge, rapid restart, defrost stuck) and normal-but-scary behaviours (defrost, compressor inrush, restocking, hot ambient) | ✅ |
| FR-52 | Shop deploy mode and startup warning (normal-but-scary) | ✅ |
| FR-53 | Scripted scenario timeline (Play scenario) and one-command demo (`scripts/demo.sh`) | ✅ |
| FR-54 | Wokwi ESP32 firmware bonus clip | 🟡 firmware built; ✋ record clip |

## 7. Non-functional requirements

| Area | Requirement |
| :--- | :--- |
| **Safety** | Generated code never runs outside a sandbox. Only verified fixes/safe runbooks auto-apply. Hard limits can never be suppressed. Disapprove before the deadline always wins. `AUTO_ACTION_ENABLED=false` disables all auto-apply. |
| **Security** | Secrets only in `.env` (git-ignored); never logged or committed. `MOBILE_API_TOKEN` guards approve/disapprove/apply endpoints. File paths for targets/hot-swap are allowlisted. Uploaded docs and logs are treated as untrusted data. CORS limited to local dashboard origins (overridable for deploys). |
| **Reliability** | Model provider failover. Modal → Docker verification fallback. Watcher debounce + quiet period. Dashboard and phone auto-reconnect and resync. |
| **Performance (demo)** | Detection within seconds of the first warning. Verified fix in ~40–130 s (model + sandbox time). Countdown ticks every second. |
| **Observability** | Every step streamed over `WS /api/ws` with model, provider, duration. Every run stored with steps, gate decision and decision record (`GET /api/runs/{id}`). |
| **Quality** | Unit tests for every module without network (≈290 tests); acceptance tests for the setup gate (`tests/test_setup_acceptance.py`). |
| **Compliance** | Meta models only in the pipeline; repo started fresh for the event; MIT license. |

## 8. Success metrics

| Metric | Target |
| :--- | :--- |
| First warning → verified fix (software demo) | ≤ 2 min |
| Runs per incident burst | exactly 1 |
| Fixes applied without verification | 0 |
| Normal-but-scary demo events that raise an alarm (defrost, inrush, restock, deploy, startup warning) | 0 |
| Real faults missed in the acceptance suite | 0 |
| Phone alarm on a locked, silent Android | appears with sound + vibration every time |
| Live take | full scenario records in one take |

## 9. Acceptance criteria

Full Given/When/Then cases live in [`setup-roadmap.md`](../setup-roadmap.md) (S-1…S-12 shop, C-1…C-14 cold chain) and the "Definition of done" sections of [`mobile-roadmap.md`](../mobile-roadmap.md) and [`simulation-roadmap.md`](../simulation-roadmap.md). Release-blocking ones:

1. **Real deadlock (S-9):** traffic → exactly one run → fail-to-pass PASS → phone countdown → auto-apply → error rate back under 1%.
2. **Defrost ignored (C-4)** and **defrost stuck acted on (C-5).**
3. **Compressor inrush ignored (C-6).**
4. **Harmless shop warning ignored (S-5).**
5. **Disapprove within 20 s cancels; late decision → 409.**
6. **FAIL runs and unsafe runbooks never auto-apply.**
7. **All unit tests green.**

## 10. Release status and remaining work (as of Oct 28)

| Area | Status | Remaining |
| :--- | :--- | :--- |
| Core loop (diagnose → generate → verify → retry) | ✅ live runs pass (Muse Spark → Baseten → Modal) | — |
| Real GitHub PR | 🟡 | ✋ Create demo repo + fine-grained `GITHUB_TOKEN` (`contents`, `pull_requests` write); set `GITHUB_DEMO_REPO`; run end to end |
| Simulation (Sim 0–7) | ✅ | ✋ backup footage; ✋ Wokwi 15 s clip |
| Setup + gate (P0–P9) | ✅ automated | ✋ live pass with real models; ✋ demo scene recording |
| Mobile (M0–M4) | ✅ | ⬜ M5 FCM push (optional); ✋ phone + laptop recording; README section |
| Command Center UI (U0–U4) | 🟡 | Tailwind shell, incident cards, detail drawer, `/incidents/[id]`, focus mode |
| Public deploy (Railway) | ✅ API + web live | Keep alive through judging; redeploy latest |
| Known defect | 🟡 | Shop worker-thread leak: after heavy traffic the shop can jam (every order 503) until restarted — fix in `demo/shop/app.py` |
| Submission | ⬜ | 3-min video, README "built during the hackathon" final pass, contributors, submit on CV before Nov 4 9:00 PM ET, X post |

## 11. Timeline

```
Oct 27        Core loop live (diagnosis → patch → Modal PASS); Railway deploy
Oct 28        Simulation Sim 0–7; mobile M0–M4; setup P0–P9 (code + tests)
Oct 29–31     Real PR end to end; Command Center UI U0–U2; shop leak fix
Nov 1–2       UI U3–U4; live acceptance pass; backup footage; rough-cut video
Nov 3         Final 3-minute video; README; Discord questions
Nov 4         Clean-clone run; submit before 9:00 PM ET; X post
Nov 5–9       Keep demo live; promotion; closing ceremony Nov 9
```

## 12. Risks

| Risk | Mitigation |
| :--- | :--- |
| Model provider down or out of credits | Failover Baseten → Fireworks → Meta; pre-recorded backup footage |
| Modal auth/cold start | Docker fallback (`TA_VERIFY=local`); narrate over the verify step |
| Over-suppression hides a real fault | Hard limits never suppressible; mode max durations; observe escalates on impact; suppressed decisions visible in the stream |
| Extraction invents numbers | Quote required per value; human confirms every field; sample profiles as fallback |
| Phone alarm blocked by OS settings | Android-only demo device; Settings → Test alarm + permission checklist before recording |
| Shop jams after heavy traffic | Restart shop between takes until the leak fix lands |
| Scope creep vs. deadline | UI polish and FCM are cuttable; core loop + simulation + setup + mobile carry the demo |

## 13. Judging alignment

| Rubric | Weight | Our answer |
| :--- | :--- | :--- |
| Impact | 30% | Outages fixed in minutes with proof; spoiled stock prevented; false alarms suppressed with reasons |
| Use of Meta AI tooling | 25% | Muse Spark (diagnosis, extraction), Muse Spark Open on Baseten (patches, tests, runbooks), Muse Wonder (escalation), Muse Code (built with) |
| Technical depth | 20% | Typed contracts, sandboxed untrusted code, fail-to-pass verification, deterministic safety rules, the gate, server-owned veto window, ~290 tests |
| Demo | 25% | Real shop and fridge visibly break and recover; phone alarm; real PR |

Bonus targets: Best Agentic Use-Case, Best Build on Meta Open Weight Models, Most Viral Project, Community Vote.

## 14. References

- Technical documentation: [`docs/DOCUMENTATION.md`](DOCUMENTATION.md)
- Blueprint: [`about.md`](../about.md) · Main roadmap: [`roadmap.md`](../roadmap.md)
- [`simulation-roadmap.md`](../simulation-roadmap.md) · [`mobile-roadmap.md`](../mobile-roadmap.md) · [`setup-roadmap.md`](../setup-roadmap.md)
- Demo script: [`demo/script.md`](../demo/script.md)
