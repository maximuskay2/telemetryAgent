# 🛡️ TelemetryAgent: Roadmap & Timetable

**Project Name:** TelemetryAgent  
**Track:** Indie Developer Track — Problem Statement: Push the Frontier  
**Scope:** Software-first autonomous SRE agent (~80% of effort) with a lightweight appliance-telemetry proof point (~20%) running through the same reasoning core.  
**Core Objective:** Ingest a crash log → **Muse Spark 1.3** finds the root cause → **Muse Spark Open** (Baseten) writes a patch and test → **Modal Sandbox** runs pytest → self-correct on failure → open a **real GitHub PR**. The same loop handles synthetic fridge telemetry, verified by a rule-based safety validator instead of pytest.

---

## ✅ Hackathon Compliance Checklist

- [ ] Pipeline uses Meta models only: `muse-spark-1.3`, `muse-wonder-1.0`, optional `sam-3.1` (Meta Model API) and `meta-models/muse-spark-open-1026` (Baseten).
- [ ] Repository is **public** with an MIT license.
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
4. **SAM 3.1 is optional.** At most one image confirming one visual symptom, and only if time allows. It is never a standalone feature.
5. **No overclaiming.** Say "verified fix" and "abnormal behavior detected early", never "zero hallucination" or "predicts failure".

---

## 🎯 Stage 2 Judging Rubric Alignment

| Rubric Category | Weight | How TelemetryAgent Scores |
| :--- | :--- | :--- |
| **Impact** | **30%** | Outage diagnosis and fix verification in minutes instead of hours; the same agent extends to physical equipment where failures spoil stock. |
| **Use of Meta AI Tooling** | **25%** | Model routing by job: Muse Spark diagnoses, Muse Spark Open generates, Muse Wonder escalates, optional SAM 3.1 confirms; structured output; feedback-driven self-correction. Built with Muse Code. |
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
   muse-spark-open-1026 on Baseten (backup: Fireworks → muse-spark-1.3)
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
- [ ] Install Muse Code (`curl -fsSL https://dev.meta.ai/install.sh | sh`, then `muse`).
- [ ] Make the GitHub repo public.

#### **Day 1: Tue, Oct 27 — Diagnosis on Meta Model API**
- [ ] Add `.env.example` (`MODEL_API_KEY`, `BASETEN_API_KEY`, `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET`, `GITHUB_TOKEN`, optional `FIREWORKS_*`).
- [ ] Add `core/schemas/telemetry.py` (software/appliance union) and `core/schemas/remediation.py` (patch, runbook, verification result).
- [ ] Scaffold the FastAPI app (`apps/api/main.py`) with log ingestion and a WebSocket stream.
- [ ] Build `core/infer/meta_client.py` with `muse-spark-1.3` and a `/api/diagnose` endpoint using structured output.
- [ ] Add sample crash logs in `samples/` and verify with `GET /v1/models` and a deadlock log.
- [ ] Attend Agents 101.

#### **Day 2: Wed, Oct 28 — Patch generation**
- [ ] Build `core/infer/baseten_client.py` (`meta-models/muse-spark-open-1026`).
- [ ] Build `core/infer/fireworks_client.py` backup and the failover chain (Baseten → Fireworks → `muse-spark-1.3`).
- [ ] Create `demo/target-service/` with a seeded, reproducible bug (e.g. lock-ordering deadlock) and a minimal test suite.
- [ ] Attend Agents 102 and apply its verifiable-agent practices.

#### **Day 3: Thu, Oct 29 — Modal Sandbox verification**
- [ ] Build `core/verify/sandbox.py`: write patch + test into a Modal Sandbox, run pytest, return pass/fail and feedback.
- [ ] Require the generated test to **fail on the original code and pass on the patch**, so a test cannot simply agree with its own fix.
- [ ] Timeouts on every sandbox; generated code never runs outside it.

#### **Day 4: Fri, Oct 30 — Closed loop + real PR** *(software milestone)*
- [ ] Build `core/agent/loop.py`: diagnose → generate → verify → retry with feedback (max 3), final attempt on `muse-wonder-1.0`.
- [ ] Build `core/actions/github_pr.py`: branch, commit, open a PR on the demo target repo with diagnosis, test output, and attempt count.
- [ ] End-to-end run: deadlock log in → real PR out.
- [ ] Unit tests for the loop with mocked model clients.

#### **Day 5: Sat, Oct 31 — Dashboard**
- [ ] Next.js dashboard with two incident panels (software, appliance), each showing: incoming telemetry, diagnosis, generated fix, verification result, final action.
- [ ] FastAPI WebSocket streaming of every loop step, including which model and provider served it.
- [ ] "Inject incident" buttons for both domains.

#### **Day 6: Sun, Nov 1 — Appliance path** *(20% scope starts)*
- [ ] Build `core/simulate/appliance.py`: synthetic fridge/freezer readings (temperature, current, vibration, door events) with injectable faults: door left open, condenser fouling (longer runs, higher current), power-back surge, rapid restart.
- [ ] Route appliance windows through the same `muse-spark-1.3` diagnosis.
- [ ] Generate runbooks with Muse Spark Open.
- [ ] Build `core/verify/safety_rules.py` and plug it into the shared loop.

#### **Day 7: Mon, Nov 2 — Appliance actions + hardening**
- [ ] Build `core/actions/notify.py`: SMS alert and work-order stub shown in the dashboard.
- [ ] Optional, only if everything above works: one SAM 3.1 call confirming a visual symptom (e.g. ice build-up) in a single image.
- [ ] Harden error handling (`401`, `404 model_not_found`, rate limits, provider failover) and input limits.
- [ ] Write the demo script.

#### **Day 8: Tue, Nov 3 — Demo video & README**
- [ ] Record and edit the **3-minute** video: both incidents side by side; the software PR shown live on GitHub; callouts for Muse Spark, Muse Spark Open, Muse Wonder, Modal, and Muse Code.
- [ ] README: architecture, setup, models used, and the "Built during the hackathon" list.
- [ ] Ask remaining submission questions in Discord.

#### **Day 9: Wed, Nov 4 — Submission**
- [ ] Final end-to-end run from a clean clone.
- [ ] Confirm the repo and video are public and all contributors are listed.
- [ ] Submit on the [CV platform](https://cerebralvalley.ai/e/meta-ai-developer-hackathon/hackathon/submit) before **9:00 PM ET**.
- [ ] Post the demo on X and submit the link for Most Viral Project.

#### **Nov 5 – Nov 9 — Judging & Closing**
- [ ] Keep the live demo running.
- [ ] Promote the X post (counted until Nov 8 EOD) and the community vote.
- [ ] Closing ceremony: Mon, Nov 9 at 12:00 PM ET.

---

## 📄 Submission Quick-Sheet

* **Project Title:** TelemetryAgent
* **Track:** Indie Developer
* **Problem Statement:** Push the Frontier
* **One-Liner:**  
  *An autonomous SRE agent on Meta's Muse models that diagnoses crashes, writes fixes with the open-weight Muse Spark Open, proves them in a Modal sandbox, and opens the PR — and the same reasoning core diagnoses physical equipment.*
* **Meta models used:** `muse-spark-1.3`, `muse-wonder-1.0`, optional `sam-3.1` (Meta Model API); `meta-models/muse-spark-open-1026` (Baseten); Muse Code for development.
* **Partners used:** Baseten (primary generation), Modal (sandbox verification), Fireworks (backup generation).
* **Built during the hackathon:** the entire repository (started fresh for the event).
* **Required links:** public GitHub repo, 3-minute demo video, X post link.
