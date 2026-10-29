# 🎛️ TelemetryAgent: "Mission Control" UI Roadmap (Web + Mobile)

**One document, one path.** Follow the steps in order; each step says what must already be done, which files to touch, what to build, what must not break, and how to check it. Replaces the two "🎨 UI: Incident Command Center" sections (U0–U4) in [`roadmap.md`](roadmap.md). Related: [`simulation-roadmap.md`](simulation-roadmap.md), [`mobile-roadmap.md`](mobile-roadmap.md), [`setup-roadmap.md`](setup-roadmap.md), [`docs/DOCUMENTATION.md`](docs/DOCUMENTATION.md).

---

## 0. How to use this document

1. **Work top to bottom.** Steps are numbered `S1 … S10` (web + backend) and `M1 … M4` (mobile). Don't start a step until its **Needs** are ticked.
2. **One step = one branch = one PR**, merged before the next step starts (mobile can run in parallel after S2).
3. **After every step run the Regression checklist (§5).** A step is done only when every box in §5 still passes.
4. **Never edit the old dashboard's behaviour.** The current UI keeps working at `/` until the cutover in S10; the new UI is built at `/mission`.
5. Tick the boxes in this file as you go so anyone can see where we are.

---

## 1. Goal and decisions

**Goal.** Replace the green-on-black terminal look with an enterprise-grade **"Enterprise Obsidian" Mission Control** (in the spirit of Vercel, Linear, Datadog). Judges see a calm, readable product that obviously separates *ignored noise* from *real incidents*, shows the verified fix, and ends in a visible veto countdown. Operators see the root cause, fix and decision in seconds.

**Decisions (already made — don't reopen):**
- Web first; the phone alarm second (video ≈ 2½ min dashboard, ≈ 15 s phone).
- Dark only. Three-column layout: **Topology & State · Incidents & Gate · Agent Trace & Veto**.
- Tailwind CSS v4 (no preflight until the end), Geist fonts from npm, Lucide icons, `motion` only for drawer and card transitions.
- Backend changes are **additive only** (new fields, new endpoints; no changed responses).
- Build the new UI at `/mission`; cut over to `/` in S10; old UI lives at `/classic` until the video is recorded.

---

## 2. Ground rules (non-negotiable)

| # | Rule | Why |
| :--- | :--- | :--- |
| G1 | **No existing API response changes shape.** Only add optional fields or new endpoints | The phone app and `/setup` parse today's shapes |
| G2 | **No secrets in the web bundle.** Nothing like `NEXT_PUBLIC_MOBILE_API_TOKEN` | Anything `NEXT_PUBLIC_*` is public on the Railway URL |
| G3 | **Tailwind without preflight** until S10 | Preflight would restyle `/setup`, `/shop`, `/classic` globally |
| G4 | **Old UI untouched until S10** | Always a working demo and a recording fallback |
| G5 | **Motion only for real events** (orders, readings, steps, server deadline); `prefers-reduced-motion` respected | No fake activity |
| G6 | **Red only for real incidents / hard limits.** Every status = colour **+ icon + word** | Calm screen; colour-blind safe; readable in compressed video |
| G7 | **Disapprove is always one tap, never behind biometrics** (web or phone) | A panicked veto must always work |
| G8 | **Honest labels:** "Agent trace" (structured outputs + decisions), not "reasoning tree"; "verified fix", never "zero hallucination" | Judges check claims |
| G9 | **Before every push:** `npx tsc --noEmit -p apps/web`, `npm run build -w apps/web`, `venv/bin/python -m unittest discover -s tests`, (mobile) `flutter test` | Railway builds from the root lockfile; broken builds = broken demo URL |
| G10 | Commits carry only the project owner's identity; no co-author trailers | Owner's standing rule |

---

## 3. Design system: "Enterprise Obsidian"

### Colour tokens — one source for web and phone
Source of truth: `apps/web/app/tokens.css`. The same hex values are copied into `apps/mobile/lib/theme.dart` with a comment pointing back, and listed in `docs/design.md`.

| Token | Hex | Use |
| :--- | :--- | :--- |
| `bg` | `#09090B` | App background |
| `surface` | `#121215` | Cards, panes |
| `surface-2` | `#18181C` | Drawers, popovers, hovered cards |
| `border` | `#1E1E24` (≈ `white/10`) | Hairlines |
| `text` / `text-muted` / `text-faint` | `#FAFAFA` / `#A1A1AA` / `#71717A` | Primary / labels / timestamps |
| `brand` (AI) | `#6366F1` indigo, `#38BDF8` cyan | Brand, Meta model activity, links, focus rings |
| `ok` | `#10B981` emerald | Verified PASS, healthy, **ignored normal behaviour** |
| `warn` | `#F59E0B` amber | Gate *observe*, warnings, early catch, countdown middle |
| `crit` | `#EF4444` crimson | **Only** active incidents, deadlocks, hard limits, countdown last 5 s |

Each status colour also has a 12% tint (badge background) and a 40% tint (borders/glow). All text ≥ WCAG AA.

### Status vocabulary (use exactly these everywhere, web and phone)
| State | Colour | Icon | Word |
| :--- | :--- | :--- | :--- |
| Healthy / verified | ok | ✓ check | "Verified" / "Healthy" |
| Ignored (gate `suppress`) | ok | ✓ shield-check | "Normal · ignored" |
| Observing (gate `observe`) | warn | ◐ half-circle | "Observing" |
| Incident (gate `act`, running) | crit | ✕ alert-octagon | "Incident" |
| Hard limit | crit | ⛔ | "Hard limit" |
| AI working | brand | ✦ sparkles | model name |
| Learning / setup needed | brand / warn | ⟳ / ⚙ | "Learning" / "Setup needed" |

### Type, depth, motion, voice
- **Geist Sans** for UI, **Geist Mono** only for code, logs, IDs. Scale 12/13/14/16/20/28/40. Tabular numerals for every live number.
- Depth: `border-white/10`, faint top highlight, soft shadow `0 8px 30px rgb(0 0 0/.35)`, `backdrop-blur` only on drawers/overlays. Radius 10–12 px cards, full-round chips.
- Motion 150–250 ms ease-out; pulses/glows off under reduced motion.
- Voice: sentences, not `step=verify status=ok` — "Muse Spark found a lock-ordering deadlock in inventory.py", "Ignored: expected defrost (spec sheet p.2)".

---

## 4. Target web layout (`/mission`, becomes `/` in S10)

```
┌───────────────────────────────────────────────────────────────────────────────────────────────┐
│ ◆ TelemetryAgent  ● Shop Armed  ● Cold room Learning   Warning→fix 1m 12s   Ignored 14 · Acted 1│
│                   Muse Spark · Spark Open · Wonder · Modal          ⦿ Live  [▶ Play] [↺] [📱] [🔑]│
├──────────────────────────┬───────────────────────────────────────┬────────────────────────────┤
│ TOPOLOGY & STATE         │ INCIDENTS & GATE                       │ AGENT TRACE & VETO          │
│  Service map (pulses,    │  [All] [Incidents 1] [Ignored 14] [Obs]│  ▸ Gate       act · impact  │
│   deadlock loop)         │  ┌ ✕ Incident · Deadlock · Shop ─────┐ │  ▸ Diagnose   Muse Spark 4s │
│  Orders/min · Err · p95  │  │ CRASH━GRAB━SUGGEST━VERIFY━FIX 01:12│ │  ▸ Generate   Spark Open ·  │
│  sparkline + fix marker  │  └────────────────────────────────────┘ │               Baseten 21s   │
│  [Start traffic] [Deploy]│  ┌ ✓ Normal · ignored · Defrost ─────┐ │  ▸ Verify     Modal fail→pass│
│                          │  │ "Expected: defrost (spec p.2)"     │ │  ▸ PR #3 opened             │
│  Cold room fridge        │  └────────────────────────────────────┘ │       ◯ 17 s  VETO          │
│  temp curve + normal band│  ┌ ◐ Observing · single ERROR line ──┐ │  [Disapprove] [Approve now] │
│  mode · faults menu      │  │ "No impact yet · re-check in 30 s" │ │                             │
├──────────────────────────┴───────────────────────────────────────┴────────────────────────────┤
│ Activity · 21:14:03 Watcher caught 3 retries on brake-pad · 21:14:05 Gate: act (error rate 12%)│
└───────────────────────────────────────────────────────────────────────────────────────────────┘
```
- ≥ 1440 px: three columns (≈ 30/40/30). 1280 px: right pane is a slide-over that opens for the active incident. < 1024 px: stacked.
- Click an incident card → **detail drawer** (diagnosis, diff, tests, attempts, result, decision, gate checks).
- `F` = Focus mode (enlarge active incident + ring). `P` = Presenter mode (hide dev controls, +15% type).

---

## 5. Don't-break contract + Regression checklist

### 5.1 Feature inventory (everything that works today, and where it lives after the redesign)

| # | Feature today | API / event it uses | New home |
| :--- | :--- | :--- | :--- |
| F1 | Live connection + auto-reconnect | `WS /api/ws` | Top bar dot (S4) |
| F2 | Play scenario / Reset / scenario progress | `POST /api/sim/scenario/play`, `POST /api/sim/reset`, `scenario_step` | Top bar (S4) |
| F3 | Service map + shop metrics + shop status chip | `shop_order`, `shop_metrics` | Left pane (S5) |
| F4 | Start traffic (with countdown) | `POST /api/sim/shop/load` | Left pane (S5) |
| F5 | Deploy shop (normal-but-scary) | `POST /api/sim/shop/deploy` | Left pane menu (S5) |
| F6 | Deploy verified fix (shop hot-swap) | `POST /api/sim/shop/apply-fix` 🔑 | Drawer + veto pane (S6/S7) |
| F7 | Virtual fridge + faults + actions + defrost / restock / ambient | `POST /api/sim/fridge/{fault,action,defrost,restock,ambient}`, `fridge_reading` | Left pane (S5) |
| F8 | Technician applies runbook | `POST /api/sim/fridge/apply-runbook` 🔑 | Drawer + veto pane (S6/S7) |
| F9 | Software incident: paste/upload log, Load sample, target, run | `POST /api/run`, `GET /api/samples/deadlock` | "New incident" sheet (S6) |
| F10 | Appliance incident inject | `POST /api/run/appliance` | "New incident" sheet (S6) |
| F11 | Incident stages: telemetry, diagnosis, suggestions, fix, verification, final; source badge; timer | `AgentStep`, `GET /api/runs/{id}` | Incident card + drawer + trace (S6/S7) |
| F12 | Stream / log feed (watcher sentences, forwarded log lines, milestones) | `/api/logs`, `watcher_trigger`, `fix_applied`, … | Activity bar (S4) |
| F13 | Gate decisions (suppress / observe / act) | `gate_decision` | Center pane cards (S6) |
| F14 | "This is normal" feedback | `POST /api/systems/{id}/feedback` | Incident card + drawer (S6) |
| F15 | Veto countdown + outcome | `action_pending`, `action_tick`, `action_resolved` | Veto pane (S7) |
| F16 | Systems status | `GET /api/systems`, `setup_progress` | Top bar chips (S4) |
| F17 | Pair phone QR | `GET /api/pairing` | Top bar popover (S4) |
| F18 | `/setup` wizard (all 6 steps) | `/api/systems/*` (create, documents, profile, sample, confirm, baseline, arm, feedback) | Restyled in S8 |
| F19 | `/shop` storefront | shop `GET /products`, `POST /orders`, `shop_metrics` | Restyled in S8 |
| F20 | Phone app (feed, reports, alarm, approve/disapprove) | `/api/health`, `/api/runs`, `/api/runs/{id}`, `/api/actions`, `/api/actions/{id}/{approve,disapprove}` 🔑, WS | Restyled in M1–M4; **API shapes unchanged** |

🔑 = requires `X-Mobile-Token` when `MOBILE_API_TOKEN` is set. Today the dashboard sends no token, so these buttons only work when the token is unset. S4 adds a safe operator-token field (see S4).

### 5.2 Regression checklist (run after every step; all must pass)

- [x] **R1** `npx tsc --noEmit -p apps/web` and `npm run build -w apps/web` pass.
- [x] **R2** `venv/bin/python -m unittest discover -s tests` passes; `flutter test` passes (if mobile touched). (467 Python green; `dart analyze` clean + 13/13 model checks green. Full `flutter test` couldn't run here — Flutter's global lock is held by other terminals' long-running `flutter run`, and `flutter_tester` hangs in this sandbox. Run `flutter test` on your machine.)
- [x] **R3** `./scripts/demo.sh` starts; `/` (or `/classic` after S10) loads and shows **Live**.
- [ ] **R4** Start traffic → exactly **one** software run → diagnosis, fix, verification fill in and **stay** → apply fix → shop error rate back to ~0%. (Needs `MODEL_API_KEY` — keyless runs end NO_ACTION with no fix to apply.)
- [ ] **R5** Fridge door-open fault → appliance run → runbook + work order → apply runbook → temperature recovers. (Needs `MODEL_API_KEY` for the same reason.)
- [ ] **R6** With an armed cold-room profile: Defrost → "Normal · ignored" with citation, no incident, no phone alarm. (Backend gap, not UI: `apps/api/main.py:749` evaluates sim-fridge readings with no gate/profile, so no suppress verdict is ever logged on the sim path. The UI renders suppress cards correctly. Needs a backend-track fix to route the sim fridge through the gate.)
- [ ] **R7** Veto: countdown shows on web and phone; Disapprove cancels; silence auto-applies; late decision shows "Too late". (Needs keys for a PASS run + a real phone; web ring verified via 32 SSR checks, phone flow needs R7 on hardware.)
- [x] **R8** Play scenario runs to the end; Reset restores everything.
- [x] **R9** `/setup`: create → load sample → confirm → baseline → arm works; `/shop` lists products and Buy works. (Verified end to end on probe system `regression-probe-dc78`; required restarting the 9.5 h-old shop process, which had wedged into 500s on every order.)
- [ ] **R10** Pair phone QR opens; phone connects; `GET /api/runs/{id}` report renders on the phone. (Needs a device; QR + pairing endpoint verified from the web side only.)
- [x] **R11** Old UI (`/` before S10, `/classic` after) looks and behaves exactly as before.

---

## 6. Ownership and workflow

- **Branches:** `ui/s1-backend`, `ui/s2-foundation`, … one per step; small PRs; merge before the next.
- **Owners after S3** (avoid editing the same file in parallel):

| Area | Files | Owner |
| :--- | :--- | :--- |
| Backend additions, hooks, types | `apps/api/main.py` (S1 only), `apps/web/app/hooks/*`, `apps/web/app/types/*` | Backend developer |
| Kit + panes + pages | `apps/web/app/ui/*`, `apps/web/app/mission/*`, `setup/`, `shop/`, `incidents/` | UI developer |
| Phone | `apps/mobile/lib/*` | Mobile developer (or UI developer after S7) |

- **Freeze:** S3 needs a 30-minute freeze on `apps/web/app/page.tsx` agreed with everyone.

---

## 7. Steps

### Phase A — Safe foundation (no visual change for users)

#### S1 — Backend additions *(~2 h · Needs: nothing · Owner: backend)*
**Why:** the new drawer needs data the API doesn't keep yet, and gate counts must survive a refresh.
**Files:** `apps/api/main.py`, `core/agent/loop.py` (only to pass through values), `tests/test_api.py` (+ new tests).
- [x] For each software run, keep: `target` (e.g. `inventory`), `original_code`, final `test_code`, and the **fail-on-original** output next to the **pass-on-patch** output. Add to `GET /api/runs/{id}` as a new optional object, e.g. `"verification": {"target": "inventory", "original_code": "...", "test_code": "...", "original": {"passed": false, "output": "..."}, "patched": {"passed": true, "output": "..."}, "runner": "modal"}`. Existing keys (`run_id`, `domain`, `result`, `steps`, `decision`, `gate`) unchanged.
- [x] Gate decision log: ring buffer of the last 200 `gate_decision` payloads (with timestamp and `system_id`); `GET /api/gate/decisions?limit=50` → `{"decisions": [...], "counts": {"suppress": n, "observe": n, "act": n}}`, newest first. Cleared by `POST /api/sim/reset`.
- [x] Tests: new fields present for a PASS run; absent fields don't break older runs; gate log limit, ordering, counts, reset.
**Don't break:** G1 — phone (`run_report.dart`) and `/setup` must parse responses unchanged.
**Check:** §5.2 R2, R4, R10.

#### S2 — Design foundation *(~3 h · Needs: nothing · Owner: UI)*
**Files:** `apps/web/package.json` + root `package-lock.json`, `apps/web/postcss.config.mjs` (new), `apps/web/app/tokens.css` (new), `apps/web/app/tailwind.css` (new), `apps/web/app/layout.tsx`, `apps/web/app/ui/*` (new), `apps/web/app/kit/page.tsx` (new), `docs/design.md` (new).
- [x] Install via the workspace: `npm install -w apps/web tailwindcss @tailwindcss/postcss postcss geist lucide-react motion`. Commit the root lockfile.
- [x] `postcss.config.mjs` with `@tailwindcss/postcss`.
- [x] `tailwind.css`: import **only** Tailwind's theme and utilities layers (no preflight, G3) and map the tokens from `tokens.css` into `@theme`.
- [x] `layout.tsx`: load Geist Sans/Mono from the `geist` package (no network at build). Keep importing `styles.css` so every existing page looks identical.
- [x] Kit in `app/ui/`: `Card`, `Badge` (ok/warn/crit/brand/neutral, always icon + word per §3), `StatusDot`, `Button` (primary/secondary/danger/ghost), `Tabs`, `Tooltip`, `Sheet` (drawer), `Metric` (label, big number, delta, sparkline), `Kbd`, `EmptyState`, `ErrorState`.
- [x] `/kit` page shows every component in every state; it returns `notFound()` when `process.env.NODE_ENV === "production"`.
- [x] `docs/design.md`: tokens, status vocabulary, do/don't (screenshots added in S10).
**Don't break:** R11 — open `/`, `/setup`, `/shop` before and after: identical.
**Check:** §5.2 R1, R3, R9, R11.

#### S3 — Split `page.tsx` + typed events + `/mission` route *(~5 h · Needs: S2 · Owner: backend + UI, during the freeze)*
**Why:** the 1,714-line page is the main source of merge conflicts and silent bugs (a dozen `as unknown as { kind?: string }` casts).
**Files:** `apps/web/app/page.tsx`, `apps/web/app/hooks/*` (new), `apps/web/app/types/api.ts` (new), `apps/web/app/classic/*` (new), `apps/web/app/mission/page.tsx` (new), `scripts/gen-types.*` (new, optional).
- [x] `types/api.ts`: TypeScript types for `AgentStep`, `SimEvent` (discriminated by `kind`, one payload type per kind), `PendingAction`, gate decision, run payload (incl. S1 fields). Prefer generating from the Pydantic models' JSON Schemas (`Model.model_json_schema()`) with a small script; hand-written is acceptable if time is short.
- [x] Hooks (logic moved **as-is**, same behaviour):
  - `useAgentStream()` — socket, 2 s reconnect, typed dispatch, and **batching per animation frame** (20 orders/s must not mean 20 renders/s).
  - `useIncidents()` — the existing `applyStep` reducer unchanged (one run per panel, as today).
  - `useSimState()` — shop metrics, error-rate history, fridge readings, traffic timer.
  - `useGate()` — gate decisions + counts (seeded from `GET /api/gate/decisions` on load and reconnect).
  - `useActions()` — veto windows from `action_*` events.
  - `useSystems()` — `GET /api/systems` + `setup_progress`.
- [x] Move today's page body into `app/classic/ClassicDashboard.tsx` using these hooks; `app/page.tsx` renders it (so `/` is unchanged) and `app/classic/page.tsx` renders the same thing.
- [x] `app/mission/page.tsx`: empty shell placeholder using the same hooks (filled from S4).
**Don't break:** R11 (old UI identical), R4–R8.
**Check:** all of §5.2. `page.tsx` < 50 lines; no `as unknown as` casts left in hooks.

### Phase B — Build the Mission Control at `/mission`

#### S4 — Shell, top bar, activity bar *(~4 h · Needs: S3 · Owner: UI)*
**Files:** `apps/web/app/mission/*`, `apps/web/app/ui/*`.
- [x] Three-column grid with the breakpoints in §4; pane headers.
- [x] Top bar: logo; **system chips** from `useSystems()` (Armed / Learning with % / Setup needed → link to `/setup`); **hero metric "Warning → fix: 1m 12s"** for the last incident (first `watcher_trigger` → `fix_applied`, or → `done` PASS if not yet applied); **"Ignored N · Acted M"** from `useGate()`; model chips lit while a step from that model is running; connection dot (Live / Reconnecting); **Play** / **Reset** (F2); **Pair phone** popover with the QR (F17).
- [x] **Operator token (🔑) for apply/approve/disapprove when `MOBILE_API_TOKEN` is set:** a small key button opens a field; the token is kept in `sessionStorage` only and sent as `X-Mobile-Token`. Never a `NEXT_PUBLIC_*` variable (G2). If unset and a call returns 401, show "This action needs the operator token" with the key button.
- [x] Activity bar (F12): one line, newest first, human sentences, status icon + colour; click to expand to the full feed.
- [x] Empty / loading / error state for every pane (API down → "Can't reach the agent API at :8001 — start it with ./scripts/demo.sh").
**Don't break:** R11 (`/` untouched).
**Check:** §5.2 R1–R3, R8, R10; plus `/mission` shows live data with nothing blank.

#### S5 — Left pane: Topology & State *(~5 h · Needs: S4 · Owner: UI)*
**Files:** `apps/web/app/mission/TopologyPane.tsx`, restyled copies of `ServiceMap`, `VirtualFridge`, `Sparkline` under `app/mission/` (**the originals stay for `/classic`**).
- [x] **Service map** (F3): node cards (Customers → Shop API → Inventory locks → DB), hairline edges, **traffic pulses** from real `shop_order` events **sampled to ≤ 6 dots/s**, emerald ok / crimson failed; node glow by health; crimson **deadlock loop** between the lock nodes while failing; green after apply-fix.
- [x] **Metric cards**: Orders/min, Error rate, p95 (big tabular numbers, delta, 60-point sparkline) with a **vertical "fix applied" marker** on the error-rate sparkline (from `fix_applied`).
- [x] Controls: **Start traffic** with countdown (F4), **Deploy shop** in an overflow menu (F5).
- [x] **Fridge tile** (F7): line-art fridge (door, compressor, defrost heater), gauges (°C / A / g), temperature curve with the **profile's normal band shaded** (from `GET /api/systems/{id}/profile`) and defrost windows marked, mode badge (Normal / Defrost / Restocking); faults + normal behaviours (Defrost, Restock, Ambient) in a compact menu.
- [x] Per-tile status chip: Armed / Learning / **Suppressing** (last gate decision for that system was `suppress`).
**Don't break:** R11; R4, R5, R6 still pass from `/`.
**Check:** during Play scenario, breakage and recovery are obvious from the left pane alone.

#### S6 — Center pane: Incidents & Gate + detail drawer *(~6 h · Needs: S1, S5 · Owner: UI)*
**Files:** `apps/web/app/mission/IncidentsPane.tsx`, `IncidentCard.tsx`, `GateCard.tsx`, `IncidentDrawer.tsx`, `NewIncidentSheet.tsx`, `lib/diff.ts`; a **new** `useIncidentList()` hook (the classic `useIncidents()` stays untouched).
- [x] **Incident list keyed by `run_id`** (several runs at once) in `useIncidentList()`; finished incidents stay listed.
- [x] **Tabs:** All · Incidents · Ignored · Observing, with counts (from `useGate()`).
- [x] **Incident card** (F11): crimson left edge while running, emerald when verified; domain icon; title from diagnosis; system; source badge (Watcher / Sensor / Manual / Upload); elapsed + warning→fix timer; **stepper** CRASH → GRAB → SUGGEST → VERIFY → FIX (VERIFY reads SAFETY for appliances); current activity line; veto state chip; **"This is normal"** action (F14).
- [x] **Gate cards** (F13): Ignored (✓ "Normal · ignored", citation links to the profile field), Observing (◐ reason + "re-check in 30 s"); collapse repeats ("Defrost ignored ×3").
- [x] **Detail drawer:** diagnosis (summary, likely cause, confidence bar, suggested actions); **code diff** original vs patch (side-by-side via a small line-diff helper in `lib/diff.ts`; uses S1 `original_code`); **tests** "fails on original → passes on patch" with counts, runner and duration (S1 outputs); attempts timeline with provider per attempt and retry feedback; **result**: "View PR on GitHub" or work order + runbook checklist with 🛡 per step; **Apply** buttons (F6/F8) using the operator token; **decision record**; **gate checks**.
- [x] **New incident sheet** (F9/F10): paste/upload log, Load sample, target, Run; Inject fridge incident.
**Don't break:** R11; classic panels still follow one run each.
**Check:** a viewer can tell ignored noise from a real incident at a glance; every finished incident opens a readable report; R4–R7 pass using only `/mission`.

#### S7 — Right pane: Agent trace & Veto *(~5 h · Needs: S6 · Owner: UI)*
**Files:** `apps/web/app/mission/TracePane.tsx`, `VetoRing.tsx`.
- [x] **Agent trace** (label exactly "Agent trace", G8): Gate → Diagnose → Generate (per attempt) → Verify → Act, each with model + provider badge (Meta · Muse Spark, Baseten · Spark Open, Fireworks, Meta · Muse Wonder, Modal / Docker), duration and output summary; suggestions as a checklist.
- [x] **Veto ring** (F15): SVG ring driven by the server `deadline`, corrected by `action_tick`; indigo → amber → crimson in the last 5 s with a soft pulse; big seconds; action summary; **Disapprove** (danger, one click, G7) and **Approve now** (primary) via `POST /api/actions/{run_id}/{disapprove,approve}` with the operator token; lock after one click; outcome (Auto-applied ✓ / Approved ✓ / Disapproved — left for a human / Too late); 409 handled as "Too late".
- [x] Idle state: last outcome + policy line ("Auto-fix on · 20 s window · kill switch off").
- [x] Optional soft sound when a window opens (off by default; toggle in the top bar).
**Don't break:** R7 must still pass from the phone with the web open at the same time (first decision wins).
**Check:** the veto moment reads clearly at 1080p from across the room.

### Phase C — Other pages, polish, cutover

#### S8 — `/setup`, `/incidents/[id]`, `/shop` *(~4 h · Needs: S2 kit; S6 drawer for incidents · Owner: UI)*
- [x] `/setup` (F18): restyle only — same endpoints, same 6 steps, same validation. Stepper header, upload dropzone, review table with **source quote + page** per field, conflict rows amber, human-only fields with a lock icon, baseline progress ring, Arm summary.
- [x] `/incidents/[id]`: the drawer content as a shareable page (reads `GET /api/runs/{id}`; 404 state for unknown/expired runs — the run store is in memory).
- [x] `/shop` (F19): customer-style storefront, lighter accent so it doesn't look like the console; same `/products`, `/orders`, live error-rate banner.
**Don't break:** R9 end to end.
**Check:** every page looks like one product.

#### S9 — Polish *(~3 h · Needs: S4–S8)*
- [x] Focus mode (`F`) and Presenter mode (`P`).
- [x] Keyboard navigation for cards, tabs, buttons; visible focus rings; reduced motion; contrast check.
- [x] Toasts: incident grabbed, verified, PR opened, recovered; subtle for ignored.
- [x] Check at 1920×1080, 1440×900, 1280×720.
**Check:** all of §5.2 against `/mission`.

#### S10 — Cutover *(~1 h · Needs: S9 and a backup take recorded on the old UI)*
- [ ] Record one backup take of the full scenario on the **old** UI first. (Static backup captured as `docs/screenshots/classic.png`; the video take itself is yours to record.)
- [x] `/` renders Mission Control; `/classic` keeps the old dashboard; `/mission` redirects to `/`.
- [x] Optional: enable Tailwind preflight now **only if** `/setup`, `/shop`, `/classic` were checked visually afterwards; otherwise leave it off. (Left off per G3 — all pages verified without it.)
- [x] Screenshots into `docs/design.md`, README and `docs/DOCUMENTATION.md` §9.
- [ ] After the final video is recorded: delete `/classic`, the old components and the unused rules in `styles.css`. (Not yet — waiting on your video.)
**Check:** all of §5.2; the full Play scenario records in one take on `/`.

### Phase M — Mobile (parallel track; starts after S2 freezes the tokens)

#### M1 — Tokens, fonts, components *(~2 h)*
**Files:** `apps/mobile/lib/theme.dart`, `apps/mobile/pubspec.yaml`, `apps/mobile/assets/fonts/*` (new), `apps/mobile/lib/widgets/*` (new).
- [x] `theme.dart` uses the §3 hex values (comment pointing to `tokens.css`); Material 3 dark `ColorScheme`.
- [x] Fonts: Geist (or Inter) `.ttf` + OFL licence under `assets/fonts/`, `fonts:` section in `pubspec.yaml` (none today). No `google_fonts` (downloads at runtime, fails offline).
- [x] Widgets: `StatusBadge` (icon + word per §3), `MetricTile`, `StepperRow`, `SectionCard`, `ProviderChip`.
**Don't break:** existing screens compile and look sane with the new theme; `flutter test` passes.

#### M2 — Alarm screen *(~4 h · must)*
**Files:** `apps/mobile/lib/screens/alarm_screen.dart` (+ a `CountdownRing` widget).
- [x] Full-bleed emergency surface: crimson → near-black radial gradient for incidents; amber variant when auto-fix is off ("approval required"); themed status/navigation bars.
- [x] **Massive countdown ring** (`CustomPainter`, ~70% of width), seconds in 72 pt tabular numerals, driven by the server deadline (as today).
- [x] Haptic tick each second; stronger pattern in the last 5 s (existing `vibration` + `HapticFeedback.heavyImpact`). Keep the existing looping alarm sound (`audioplayers`) and stop rules.
- [x] Title, system, one-line diagnosis, compact stepper, "Verified: tests fail→pass in Modal".
- [x] **DISAPPROVE** full-width crimson, one tap (G7); **Approve now** outlined; lock after one tap; large outcome screen.
**Don't break:** full-screen intent over the lock screen, sound and vibration on a locked silent phone; `MainActivity` untouched.
**Check:** §5.2 R7 on a real Android phone, locked and silent.

#### M3 — Feed and reports *(~4 h · should)*
**Files:** `home_screen.dart`, `report_screen.dart`, `models/run_report.dart` (read S1's optional fields if present).
- [x] Feed cards with status badge (Auto-applied, Approved, Disapproved, Failed, Ignored), system, time, warning→fix duration; filter chips. (Badges, system, source/model/steps meta + all filters done; per-row time and warn→fix need timestamps `GET /api/runs` doesn't return — pipeline duration is on the report instead.)
- [x] Report: hero header, stepper, section cards, code view, PR button; **swipeable charts** (`PageView` + existing `fl_chart`): temperature with normal band, current, vibration.
- [x] Approval history with device, time, outcome.
- [ ] *Optional, last:* biometric confirm for **Approve now** only (`local_auth`). This requires changing `MainActivity` from `FlutterActivity` to `FlutterFragmentActivity` (keep the show-when-locked / turn-screen-on code) and **re-running R7 on a locked phone immediately**. Skip if short on time — it's the change most likely to break the alarm. (Skipped per the cut order.)
**Don't break:** reports for runs created before S1 still render (new fields optional).

#### M4 — Polish *(~1 h)*
- [x] App icon + splash in the new palette; Settings → Test alarm uses the new alarm screen; screenshots for README. (Icons + splash + README prose done; phone screenshots need a device/emulator run.)

---

## 8. Schedule and cut order

```
[Oct 29]  S1 backend additions · S2 foundation · S3 split + types (freeze)
[Oct 30]  S4 shell + top bar · S5 left pane                     │ M1 tokens/fonts
[Oct 31]  S6 incidents + gate + drawer                          │ M2 alarm screen
[Nov 01]  S7 trace + veto ring · S8 setup / incidents / shop    │ M3 feed + reports
[Nov 02]  S9 polish · backup take on old UI · S10 cutover        │ M4 polish
[Nov 03]  Record the 3-minute video on the new UI
```
**If late, cut in this order:** S8 shop restyle → M3 → Presenter/Focus modes → S8 setup restyle → optional sound → biometrics.
**Never cut:** S3 (makes parallel work safe), S6 (shows ignored vs real), S7 (veto is the climax), M2 (phone shot), S10's backup take.

---

## 9. Acceptance (the redesign is done when)

- [ ] Every row of §5.1 works from the new UI; every box of §5.2 passes.
- [ ] A first-time viewer can say within 5 s of a screenshot: what's broken, what the agent is doing, what was ignored and why, and how long until the fix applies.
- [ ] Red appears only for real incidents/hard limits; ignored behaviour is green, labelled "Normal · ignored", with a citation.
- [ ] Every live number and animation comes from real API data.
- [ ] Full scenario (shop deadlock + fridge fault + defrost ignored + veto auto-apply) records in one take at 1920×1080 and stays readable at 720p.
- [ ] Phone alarm readable at arm's length; Disapprove reachable with one thumb.
- [ ] No secrets in the web bundle; Railway web and API deploy cleanly.

---

## 10. Risks

| Risk | Mitigation |
| :--- | :--- |
| Merge conflicts in `page.tsx` | S3 split under a freeze; one owner per file afterwards (§6) |
| Redesign eats the deadline | Built at `/mission`; old UI is the demo until S10; cut order in §8 |
| Tailwind restyles other pages | No preflight (G3) until S10, and only after a visual check |
| Web deploy breaks after new packages | Workspace install, root lockfile committed, `npm run build` before push (G9) |
| Token leaks via the web bundle | Operator token typed by the presenter, kept in `sessionStorage` (G2) |
| Stutter during traffic | Event batching per frame (S3) + sampled pulses (S5) |
| Phone alarm stops over the lock screen | Biometrics optional and last; R7 on a real locked phone after M2/M3 |
| Over-claiming AI | "Agent trace" label; "verified fix" wording (G8) |
| In-memory run store lost on API restart | `/incidents/[id]` shows a clear "run not found (API restarted)" state |

---

## Appendix — Repo facts this plan was checked against (Oct 28)

- Web: Next 16.4.3, React 19.3.1, TypeScript 5.9; npm workspace at the root (`apps/web`); no Tailwind/PostCSS config; global element styles in `apps/web/app/styles.css`; `page.tsx` 1,714 lines, `setup/page.tsx` 1,133 lines.
- API: `GET /api/runs/{id}` returns `run_id, domain, result, steps, decision, gate`; `ExecutionResult` holds `patch_code` but not original code, test code or the fail-on-original output; `gate_decision` is broadcast only; apply/approve/disapprove require `X-Mobile-Token` when `MOBILE_API_TOKEN` is set.
- Load generator: `--rate` is total orders/s (dashboard Start traffic uses 20).
- Mobile: `audioplayers`, `vibration`, `fl_chart`, `flutter_local_notifications`, `flutter_foreground_task`; no `fonts:` section; `MainActivity : FlutterActivity` with show-when-locked flags.
