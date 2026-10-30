# 🏢 TelemetryAgent: Commercial Roadmap (one installation → many customers, free for now)

**Goal:** let many teams use TelemetryAgent on their software and hardware, each with their own account and their own data. **It is free for now — no payments, no prices, no Stripe.** Each customer signs up, connects their systems and uses it under a **free fair-use allowance**; we run the models and sandboxes on our accounts and track what each customer costs. **Pricing and billing are set up after the hackathon**, using the cost data this roadmap collects.

**What this roadmap covers — the gaps between today and a product many customers can use safely:**

| Missing | Why it matters for real customers | Phase |
|---|---|---|
| Accounts and logins | Today everyone with the access code sees every system and connection | 1 |
| Keeping each customer's data separate | Customer A must never see customer B's tokens, systems or PRs | 2 |
| Usage tracking per customer | So we know what each customer costs, keep the free allowance fair, and can price it later | 3 |
| Billing | Stripe subscriptions — **deferred until after the hackathon** | 4 (later) |
| Sales-ready look | Buyers should see a polished product in Meta's design style, built on Meta's models: light by default, dark still available, Meta-style type | now |

Phase 0 (foundations) comes first; Phase 5 (launch readiness) closes it out. **Phase 4 (billing) is not built now** — nothing in this round may add a price, a checkout, a card form or a Stripe call. The sales-ready look does not wait on anything — the product has already crossed enough journey, simulation, setup, and production work to be shown.

> Scope: commercial operation, plus the sales-facing look below. `production-roadmap.md` owns the integrations (connect → fix → act), `journey-roadmap.md` the screens. `ui-roadmap.md` still owns layout and status words; its "dark only" decision is updated by the section below (light is the default, dark stays). Nothing here weakens the gate, the veto rules, the uptime promise or the simulation route.

**Starting point:** `main` @ `89e8bdd` (Oct 30, evening). 929 tests pass. Production route proven end to end for Python (live crash → proven fix → merged PR), and auto-fix now covers **7 languages** (Python, JavaScript/TypeScript, Java, Kotlin, Go, Rust, PHP — live matrix PASS on Baseten; Go is the least reliable, drafting more often). Fix-run cost varies a lot by language (Java/Kotlin ~150–200 s of sandbox vs 20–40 s for most others).

---

## Where we are (audit, Oct 30)

| Area | Today | Problem for a paid product |
|---|---|---|
| Users | None. `/connect` behind one shared `CONNECT_ACCESS_CODE` | Can't tell customers apart, can't revoke one person |
| Phone | One `MOBILE_API_TOKEN` for the whole installation (`core/actions/auto_action.py`) | Every paired phone can approve anything |
| Storage | JSON files under `TA_DATA_DIR` (`data/profiles`, `data/connections`, audit, rate stamps, pause) | No tenant field, no transactions, wiped on redeploy without a volume |
| Secrets | Pasted tokens stored in connection files (mode `0600`) | Plain text at rest; one leak exposes all customers |
| Live events | `EventHub.broadcast` sends every event to every WebSocket client (`apps/api/main.py`) | Customer A's dashboard would show customer B's incidents |
| Pause-all | One global flag (`core/actions/mitigate.py` `_pause_path`) | One customer's pause would freeze everyone |
| Systems API | `POST/DELETE /api/systems` open | Anyone can create or delete systems |
| Model + sandbox spend | Our keys (Meta, Baseten, Fireworks, Modal); nothing recorded per run | No cost per customer, no limits |
| Billing | None — and none is built in this round | Free for now; without per-customer costs we can't price it later |
| Look | Dark only, mint on near-black, Geist (`ui-roadmap.md`) | Does not look at home next to Meta Business Suite in a sales conversation |

---

## Sales-ready look — now (does not wait on accounts or billing)

The product has already crossed the journey, the simulation, setup, and the production path. What a buyer opens should follow Meta's design style (Facebook, Meta Business Suite), with both color modes, and say honestly what it is: TelemetryAgent, **built on Meta's models** (Muse Spark, Muse Wonder).

**Brand rule:** borrow the style, never the brand. No Meta or Facebook logos, no "by Meta", "Meta TelemetryAgent" or anything implying Meta made, owns or endorses the product — unless Meta actually licenses or acquires it. The allowed attribution is "Built with Muse Spark" / "Built on Meta's Muse models", following Meta's model attribution terms.

1. **Light mode is the default.** Keep dark mode. A first visit with no saved choice opens in light. A Light / Dark control switches modes, and the choice is remembered on the next visit.
2. **Meta fonts.** UI type is Meta's Optimistic, then the Helvetica / Arial stack Meta products use when Optimistic is not on the machine. Optimistic is proprietary — use it when it is installed or when Meta has licensed redistribution; do not copy the font files into the repo without that license. Monospace stays for code, logs, and IDs only.
3. **Meta / Facebook surfaces.** Light: gray wash, white cards, near-black text, Meta blue (`#0866FF`) for primary actions with white labels. Dark: Facebook charcoal (`#18191A` background, `#242526` cards) with the same blue. Status words stay as they are today (Healthy, Normal · ignored, Observing, Incident, Hard limit); only the colors and type change.
4. **Web first.** Welcome, guided demo, Mission Control, shop, setup, and connect. The phone keeps today's palette until this web pass is done, then it matches.

**Done when:** a fresh browser opens welcome and Mission Control in light mode and it looks at home next to Meta Business Suite, with "Built with Muse Spark" attribution and no Meta/Facebook logos or ownership claims; switching to dark still works and survives a reload; a machine with Optimistic installed renders it, and one without still uses the Helvetica / Arial fallback.

---

## 0. Foundations (before any customer data) — ~1 week

1. **Provider terms.** Confirm use inside a product offered to others is allowed for Meta Model API, Baseten, Fireworks and Modal. Today we run on **hackathon credits** (Baseten: $100, key only works with `meta-models/muse-spark-open-1026`; Modal: $100 on request) — fine while free, but they run out, so Phase 3 spend alerts must warn us before they do. Record each provider's data-retention and no-training terms — they go into our privacy policy (Phase 5).
2. **Real database.** Postgres (Railway Postgres is fine to start). Tables replace the JSON files: `orgs`, `users`, `memberships`, `systems`, `connections`, `runs`, `audit`, `rate_stamps`, `pause_state`, `usage_events`, `allowances` (the free fair-use limits per org; a `subscriptions` table comes with Phase 4 later). Keep the file store as the **demo/simulation backend** so the simulation route never depends on the DB.
3. **Secrets encrypted at rest.** Envelope encryption: one data key per org, wrapped by a master key held outside the DB (Railway secret or a KMS). Connection secrets are stored encrypted; decrypted only in the process that calls GitHub/Railway/webhooks. Hints (`****abcd`) stay as today.
4. **Environments.** `staging` and `production` Railway environments, separate databases, separate model keys with spend caps on each provider.
5. **Backups.** Daily Postgres backups, tested restore.

**Done when:** API boots against Postgres; the full test suite passes with a DB fixture; simulation route still passes `scripts/smoke_demo.sh` without a DB.

---

## 1. Accounts and logins — ~1–1.5 weeks

**Model:** an **organization** (the customer) has **users** with a **role**: `owner` (everything, incl. deleting the org; billing later), `admin` (connect, arm, approve), `member` (view, approve if allowed), `viewer` (read-only).

1. **Sign-up / sign-in.** Use a managed auth provider (e.g. Clerk, Auth0, WorkOS, Supabase Auth) rather than building passwords: email magic link + Google/GitHub sign-in; MFA for owners. The API verifies the provider's session token (JWT) on every request.
2. **Org lifecycle.** Sign-up creates an org with the user as `owner`; invite by email; remove members; transfer ownership; delete org (with a grace period and export).
3. **API auth middleware.** Every route except health, `/forwarder.py`, ingest (key-authenticated) and device routes (key-authenticated) requires a signed-in user. Resolve `request.state.org_id` + role once; routes use it.
4. **Replace the shared code.** `CONNECT_ACCESS_CODE` stays only for self-hosted single-team installs. Hosted: `/connect` requires sign-in and `admin`+.
5. **Phones per user.** Pairing issues a **device token per user** (stored hashed, revocable from the web: "Your devices"). Approve / disapprove / pause / execute-option check that user's role in the incident's org. `MOBILE_API_TOKEN` remains for self-hosted only.
6. **Web.** Sign-in page, org switcher (a user can belong to several orgs), members page, devices page. `/welcome` and the simulation demo stay public with no sign-in.

**Done when:** a new user signs up, creates an org, invites a teammate, pairs a phone; a removed member's web session and phone token stop working immediately; approve from a `viewer` gets 403.

---

## 2. Keeping each customer's data separate — ~1.5–2 weeks

**Rule:** every row and every event carries `org_id`; no query, event or background job runs without one.

1. **Schema.** `org_id NOT NULL` on systems, connections, runs, audit, rate stamps, pause state, usage events. Ingest keys (`ta_live_*`) and device keys map to a connection → system → org, so key-authenticated routes resolve the org too.
2. **Enforcement in the database.** Postgres **row-level security**: the API sets `app.org_id` per request/transaction; policies hide other orgs' rows even if a query forgets the filter.
3. **Live events scoped.** `EventHub` keeps clients per org; WebSocket connect requires a session/device token and joins that org's channel only. `broadcast(org_id, event)` — no global broadcast for customer events.
4. **Per-org controls.** Pause-all, rate limits (1 mitigation / system / 10 min), the "one open PR per fingerprint" map and `_active` fingerprints in `core/repo_fix/run.py` are all keyed by org (fingerprints alone can collide across customers).
5. **Background work.** Repo-fix runs, mitigation windows and tickers carry `org_id`; sandboxes are per run (already) and never shared between orgs; temp snapshots are deleted after each run.
6. **Secrets per org.** Decrypt with that org's data key only (Phase 0.3).
7. **Isolation test suite** (must pass in CI, forever): two orgs, every endpoint and the WebSocket — org B can't read, list, test, delete or approve anything of org A's, by ID guessing or otherwise; ingest with org A's key never lands in org B; a pause in A doesn't affect B.
8. **Migration.** One-off script imports today's JSON data into a "legacy" org; demo systems stay in the file store.

**Done when:** the isolation suite passes; an external pen-test-style check (Phase 5) finds no cross-org access.

---

## 3. Usage tracking per customer — ~1 week

**Record everything that costs us money or that the free allowance limits**, at the point it happens, as `usage_events(org_id, system_id, run_id, kind, quantity, unit, provider, language, cost_estimate_usd, at)`.

| Kind | Where to hook | Unit |
|---|---|---|
| Model call | `core/infer/analyzer.py` failover chain, `core/repo_fix/generate.py` + `core/infer/baseten_client.py` (repo-fix generation — the biggest spend), and Meta client direct calls | input/output tokens, by provider + model |
| Sandbox time | `core/verify/sandbox.py`, `core/repo_fix/run.py` sandbox exec | seconds, by backend (Modal/Docker) |
| Fix run | repo-fix start/finish | 1 run (+ outcome PASS / draft / failed) |
| PR opened / commented | `core/repo_fix/run.py` | 1 |
| Mitigation executed | `core/actions/mitigate.py` (done only) | 1, by action |
| Ingest | `/api/ingest/*` | lines accepted |
| Active systems / devices | daily snapshot job | count |

1. **Cost table** in config (what providers charge us: per provider/model token price, Modal $/s — not customer prices) → `cost_estimate_usd` per event. Reconcile monthly against provider invoices.
2. **Free allowance enforced before spending.** Every org gets the same free fair-use allowance (config, e.g. 3 systems, 5 devices, 30 fix runs / month, and a monthly cost ceiling). Before a fix run starts: check the org's remaining fix runs and cost ceiling; if over, skip the run, record a gate-style decision ("free allowance reached") and notify the owner. Per-run caps: max attempts (already 3), max sandbox minutes, max tokens. Usage events carry `language` (Java/Kotlin runs cost far more sandbox time). The allowance check is one function, `allowance(org_id)`, so Phase 4 can later swap it for paid-plan entitlements without touching callers.
3b. **Provider credit alerts.** Spend per provider vs remaining hackathon credit (Baseten, Modal); warn us at 50 / 80 / 95 %.
3. **Abuse guards.** Per-org rate limits on ingest (lines/min) and on fix runs (runs/hour); a noisy crash loop can't burn the month in an hour.
4. **Customer view.** "Usage" page: fix runs, PRs, systems, devices this period vs the free allowance. No prices, no "upgrade" button.
5. **Our view.** Internal admin page: cost per org and per language, top spenders, provider credit remaining — the data we price from after the hackathon.

**Done when:** every fix run has a cost; a test org hitting its free allowance gets no further fix runs and sees why (monitoring and alerts continue); the admin page shows cost per org and remaining provider credit.

---

## 4. Billing (Stripe) — ⏸ DEFERRED until after the hackathon (do not build now)

> Kept as the plan for later. Nobody implements anything in this section in the current round: no Stripe package, no keys, no prices, no checkout, no billing routes or pages. Pricing is decided after the hackathon from Phase 3's real cost-per-org and cost-per-language data; then `allowance(org_id)` becomes `entitlements(org_id)`.

**Shape:** monthly (and annual) **subscriptions per org**, plan limits from Phase 3 as entitlements. Start with flat plans; add usage-based overage later.

1. **Stripe setup.** Build against a Stripe **sandbox** (separate ones for local and CI); use a **restricted API key** (`rk_…`), not a secret key; latest API version + `StripeClient` instance pattern.
2. **Products and prices.** Example plans (numbers are placeholders to validate against Phase 3 costs):

   | Plan | Systems | Devices | Fix runs / month | Rollback / restart | Seats |
   |---|---|---|---|---|---|
   | Starter | 1 | 2 | 20 | PR-only | 2 |
   | Team | 5 | 10 | 150 | ✅ | 10 |
   | Business | 20 | 50 | 600 | ✅ + priority | unlimited |

3. **Checkout.** "Upgrade" creates a **Checkout Session** in `subscription` mode for the org's Stripe Customer (one Customer per org, id stored on the org). Trial (e.g. 14 days) set on the subscription.
4. **Self-service.** Stripe **Customer Portal** for card updates, invoices, plan changes and cancellation — linked from the org's Billing page (owners only).
5. **Webhooks — required, not optional.** Signed endpoint `POST /api/billing/stripe-webhook` (verify signature, idempotent by event id) handling at least: `checkout.session.completed`, `customer.subscription.created` / `updated` / `deleted`, `invoice.paid`, `invoice.payment_failed`. The webhook — never the success page — updates `subscriptions` and the org's entitlements.
6. **Entitlements in the API.** One function `entitlements(org_id)` → limits + flags (e.g. hosting mitigations allowed); used by Phase 3 checks, `/connect` (block Hosting step on Starter), and system/device creation.
7. **Payment failure.** Grace period (e.g. 7 days): banner + emails; then **read-only** — keep watching and alerting (safety first), stop new fix runs and mitigations until paid. Never delete data on non-payment without notice.
8. **Tax.** Only enable Stripe Tax after confirming tax registrations for where customers are; otherwise it silently collects nothing.
9. **Later: usage-based overage** (extra fix runs) — Stripe's recommended route for new usage-based billing is Metronome; revisit once Phase 3 data shows real usage patterns.

**Done when (in sandbox):** sign up → trial → Checkout → plan active → limits applied; plan change in the Portal updates limits via webhook; a failed payment moves the org to read-only after the grace period; replaying a webhook is harmless.

---

## 5. Launch readiness — ~1 week, partly in parallel

1. **Legal:** Terms of Service, Privacy Policy (list sub-processors: Meta, Baseten, Fireworks, Modal, Railway, auth provider, GitHub; Stripe added when billing lands), Data Processing Agreement for business customers, acceptable-use policy.
2. **Security:** dependency + secret scanning in CI; external review of auth and the isolation suite; audit log of admin actions; security contact.
3. **Operations:** error monitoring, uptime monitoring + status page, alerts on model/sandbox spend per provider, on-call for our own service.
4. **Data:** customer export (systems, runs, audit) and deletion on request; retention policy for logs/snapshots (e.g. 30 days).
5. **Mobile:** signed release builds; Play Store (then App Store); push notifications (FCM) so alarms reach a closed app — today alerts need the app running.
6. **Support:** help docs from `docs/USAGE.md`, a support inbox, onboarding call for the first customers.

**Done when:** first real (free) customer onboarded on production with accepted Terms and Privacy Policy (DPA on request), and a restore-from-backup drill has passed.

---

## 6. Order and timing (three agents: James, John, Jude)

```
Now          John   Sales-ready look (web, then phone)                  — needs nothing from the others
Now          James  C-H0 team plan + contracts (tag commercial-contracts-in) → Phase 0 → Phase 1 API → Phase 2
Now          Jude   Phase 3 pure code (cost table, usage recorder, allowance) → wires in after the tag
After tag    John   Phase 1 web + app (sign-in, orgs, members, devices) → Usage page
After Ph. 2  all    Isolation suite green on main → Phase 5 items that fit (export/delete, monitoring, legal drafts)
Later        —      Phase 4 billing, after the hackathon, priced from Phase 3 data
```

**Do not skip ahead:** isolation (Phase 2) is the gate for taking the first real customer — even a free one can't be allowed to see another customer's data.

---

## 7. Rules that don't change

- The **uptime promise** holds for every customer: PRs not pushes, reversible actions only, 20 s window, rollbacks expire unless approved, kill switches.
- **Safety beats limits:** an org over its free allowance keeps monitoring and alerts; only new fix runs and mitigations stop.
- **Free for now:** no prices, checkout, card forms or Stripe code until the post-hackathon billing round.
- The **simulation route** (`/welcome` → `/start` → Mission Control) stays public, free, and independent of accounts and the database.
- **Never log secrets**; never send customer code or logs to a provider we haven't listed as a sub-processor.

---

## 8. Team plan (C-H0 — James commits this first; then frozen)

They can't talk to each other or to a human while working. They coordinate **only through git** (`origin/main`, the `commercial-contracts-in` tag, their status files) and this roadmap.

### 8.1 Rules

- **C-1 Contracts first (H0, James).** This section: file ownership, the frozen contracts below, block IDs with test-backed acceptance, and the §8.5 operating rules. James tags `commercial-contracts-in` when pushed. John and Jude code against this text before their backends land.
- **C-2 Own files only** (§8.2). Need a change in someone else's file → write it under *Contract changes requested* in your status file and keep going.
- **C-3 Additive only.** No renames, no changed response shapes; new fields optional with defaults. Every existing route keeps its shape; auth adds 401/403 where §8.4 says, nothing else.
- **C-4 Simulation never regresses.** The simulation route works with no `DATABASE_URL`, no auth provider, no sign-in — `scripts/smoke_demo.sh` stays green at every merge, run with the database unset.
- **C-5 No billing.** Phase 4 is deferred: no Stripe package, keys, prices, checkout, card forms, billing routes or billing pages. Not even a `stripe_customer_id` column — Phase 4's migration adds it.
- **C-6 Never wait.** Before a dependency lands, code against the frozen signatures in §8.3–§8.4 with fakes, and unit-test your pure functions.

### 8.2 File ownership

| Area | **James (backend core)** | **John (web/app + look)** | **Jude (usage + allowance)** |
|---|---|---|---|
| Team plan | `commercial-roadmap.md` §8 (this commit) | — | — |
| Commerce core | `core/commerce/{__init__,db,schema.sql,repo,models,auth,crypto,migrate}.py`, `scripts/commerce-*.sh` | — | — |
| Usage + allowance | — | — | `core/commerce/{usage,allowance,costs}.py` (frozen signatures §8.4) |
| API routes | `apps/api/main.py` (middleware, WS, public list), `apps/api/routes/commerce.py` (new: orgs/members/devices/usage/admin), `apps/api/routes/{production,devices}.py` (thread org_id; shapes unchanged) | types only (reads John's TS types, never edits screens) | — |
| Pipeline hooks | `core/repo_fix/run.py` (org keying, allowance check, usage hooks), `core/ingest/*`, `core/connections/*`, `core/actions/*` (per-org pause/rate/audit), `core/setup/store.py` (file backend stays), `core/verify/*`, `core/infer/*` (usage hooks at the points §3 names — hook calls only, no cost math) | — | — |
| Web | — | `apps/web/**` (sales look + sign-in/orgs/members/devices/usage pages) | — |
| App | — | `apps/mobile/**` (sales look + sign-in/devices/approve) | — |
| Proof/validation | — | — | spend validation notes in status (Baseten runs) |
| Tests | `tests/test_com_{core,api,auth,isolation,migrate}.py` | web component tests, `flutter test` widget tests | `tests/test_com_usage*.py` |
| Docs | `docs/ops-backups.md` (backups + restore drill), `docs/production-backend.md` (commerce section) | `docs/USAGE.md` (accounts/usage help), sales-look checklist in status | cost-table sources in status |
| Status | `status/com-james.md` | `status/com-john.md` | `status/com-jude.md` |

**Frozen for all three:** the simulation route's behaviour (no-DB, no-sign-in), the gate/veto/uptime rules, existing JSON shapes (additive only), `agent/ta_forward.py` (stdlib-only, one file).

### 8.3 Frozen contracts: data + auth + crypto

**Database.** Postgres. `DATABASE_URL` set → Postgres for org-scoped data; unset → file store, today's single-tenant behaviour (self-hosted). The simulation/demo routes always use the file store. Driver: `psycopg` (sync, via `asyncio.to_thread`, matching today's style). Schema: versioned `core/commerce/schema.sql` applied at boot (`ensure_schema()`); `scripts/commerce-migrate.py` imports today's JSON into a `legacy` org. Tests: `tests/commerce_db.py` helper builds a fresh database from `TEST_DATABASE_URL` (default `postgresql://postgres:postgres@localhost:5432/telemetry_test`); DB tests skip when unreachable (same rule as Docker-dependent tests).

**Schema (frozen table shapes; RLS policies ship in C-J1's `schema.sql`):**

```sql
orgs(id text pk, name text, data_key_enc text, created_at timestamptz, deleted_at timestamptz);
users(id text pk, external_id text unique, email text unique, name text, created_at timestamptz, last_login timestamptz);
memberships(org_id text, user_id text, role text, created_at timestamptz, pk(org_id, user_id));
device_tokens(id text pk, org_id text not null, user_id text not null, token_hash text unique,
  label text, created_at timestamptz, last_used_at timestamptz, revoked_at timestamptz);
pairing_codes(code_hash text pk, org_id text not null, user_id text not null, label text,
  expires_at timestamptz, used_at timestamptz);
invites(token_hash text pk, org_id text not null, email text, role text,
  created_at timestamptz, expires_at timestamptz, accepted_at timestamptz);
systems(id text pk, org_id text not null, profile jsonb, status text, version int,
  created_at timestamptz, updated_at timestamptz, deleted_at timestamptz);
systems_versions(system_id text, version int, profile jsonb, at timestamptz, pk(system_id, version));
connections(id text pk, org_id text not null, system_id text not null, kind text, config jsonb,
  secret_enc text, secret_hint text, key_hash text, status text, detail text,
  last_seen timestamptz, created_at timestamptz);
runs(id text pk, org_id text not null, system_id text, domain text, kind text, status text,
  language text, fingerprint text, pr_url text, result jsonb, cost_estimate_usd float8,
  started_at timestamptz, finished_at timestamptz);
audit(id bigserial pk, org_id text not null, actor text, action text, detail jsonb, at timestamptz);
rate_stamps(org_id text, system_id text, at timestamptz, pk(org_id, system_id));
pause_state(org_id text pk, paused bool, at timestamptz, by_user text);
usage_events(id bigserial pk, org_id text not null, system_id text, run_id text, kind text not null,
  quantity float8, unit text, provider text, model text, language text,
  cost_estimate_usd float8 default 0, at timestamptz);
allowances(org_id text pk, systems_limit int, devices_limit int, fix_runs_limit int,
  cost_ceiling_usd float8, fix_runs_used int, cost_used_usd float8,
  period_month text, updated_at timestamptz);
```

`usage_events` extends the §3 shape with `model` (the cost table is per provider+model). `allowances` counters increment in the same transaction as the usage insert. Uploaded documents stay on disk under `TA_DATA_DIR/uploads` (needs a volume on Railway — see NEEDS).

**Org rule.** Every row in an org-scoped table carries `org_id NOT NULL`; no query, event or background job runs without one. Postgres row-level security is on for all of them: the API sets `app.org_id` (+ `app.user_id`) per transaction; policies hide other orgs' rows even if a query forgets the filter. Self-hosted (no `DATABASE_URL`) presents one implicit org: `SELF_ORG_ID = "self"`.

**Auth.** Managed provider: **Clerk** (dev instance, test keys — no production keys in this round; see NEEDS). The provider only proves identity (`sub` + email); our `memberships` table is the source of truth for orgs and roles (provider-portable). The API verifies the provider session JWT (JWKS) on every non-public request:

```python
# apps/api/main.py (James)
PUBLIC_PATHS = ("/api/health", "/forwarder.py",
  "/api/sim/*", "/api/demo/*", "/api/samples/*", "/api/run", "/api/run/*",
  "/api/logs", "/api/diagnose", "/api/telemetry/*", "/api/pairing",
  "/api/ingest/*",          # key-authenticated (ta_live_*)
  "/api/devices/*/commands", "/api/devices/*/commands/*/ack", "/api/devices/*/readings",
  "/api/devices/claim",     # pairing-code authenticated
  "/api/invites/*/accept")  # invite-token authenticated
# resolved once per request; routes read request.state only:
request.state.org_id: str      # "self" when self-hosted
request.state.user_id: str     # "" for key-authenticated callers
request.state.role: str        # owner|admin|member|viewer ("" for key callers)
request.state.auth_mode: str   # session|device|ingest|open
```

**Hosted vs self-hosted.** Self-hosted (no `DATABASE_URL`): every route behaves exactly as today (code/token/open doors unchanged). Hosted (`DATABASE_URL` set): every non-public route needs session/device auth as below — except the demo channel.

**Demo channel (frozen).** Mission Control serves the public demo, so these reads are public in both modes but scoped: unauthenticated callers see the demo channel only (in-memory sim runs + file-store demo systems, `org_id "demo"`); authenticated callers see their org's data: `GET /api/actions`, `GET /api/runs`, `GET /api/runs/{id}`, `GET /api/gate/decisions`, `GET /api/systems*` (all sub-paths). And the public demo stays clickable: `POST approve/disapprove` on a demo-channel run (in-memory sim runs, never DB org runs) needs no auth in either mode; on an org run it needs session/device auth. All other mutations need auth in hosted mode.

Ingest keys (`ta_live_*`) and device tokens (`ta_dev_*`, stored hashed) resolve org via connection → system → org (ingest) and `device_tokens` (device routes + approve/disapprove/pause/execute-option on org runs). `CONNECT_ACCESS_CODE` and `MOBILE_API_TOKEN` stay for self-hosted only. Tests use a local HS256 test issuer (`tests/commerce_auth.py`) — no network, no provider keys.

**Roles (frozen matrix).** `owner`: everything incl. delete org, transfer ownership, grant owner. `admin`: connect, arm, approve, invite/remove (non-owner), revoke devices. `member`: view + approve/disapprove. `viewer`: read-only. Approve from a `viewer` → 403; removed member's session + device tokens die immediately (membership checked per request, nothing cached).

**Secrets (envelope, frozen).** Algorithm: Fernet (`cryptography` package) with a 32-byte master key from `COMMERCE_MASTER_KEY` (Railway secret; dev via env, never committed). One random data key per org, wrapped by the master key, stored in `orgs.data_key_enc`. Connection secrets encrypted with the org's data key, decrypted only in the calling process. Hints stay `****` + last 4.

```python
# core/commerce/crypto.py (James)
def encrypt_for_org(org_id: str, plaintext: str) -> str: ...
def decrypt_for_org(org_id: str, blob: str) -> str: ...
```

**Live events.** `EventHub` keeps clients per org; `/api/ws?token=<session JWT or device token>` joins that org's channel only. `broadcast(org_id, event)` — no global broadcast for customer events. (Sim/demo events broadcast to an open demo channel that needs no token.)

### 8.4 Frozen contracts: allowance, usage, routes

```python
# core/commerce/allowance.py (Jude owns; James calls before spending)
@dataclass
class AllowanceStatus:
    allowed_fix_run: bool
    reason: str = ""            # e.g. "free allowance reached: 30/30 fix runs"
    fix_runs_remaining: int = 0
    cost_remaining_usd: float = 0.0
    systems_remaining: int = 0
    devices_remaining: int = 0
def allowance(org_id: str) -> AllowanceStatus: ...
```

Called before a fix run starts, before a mitigation executes, and at system/device creation. When not allowed: skip the spend, record a gate-style decision (`"free allowance reached"`), notify the owner. Monitoring and alerts continue. Phase 4 later swaps this for paid-plan entitlements without touching callers.

```python
# core/commerce/usage.py (Jude owns; James's hooks call record_usage)
COST_TABLE: dict = ...         # provider/model token prices, Modal $/s (our costs, not prices)
def record_usage(org_id: str, kind: str, quantity: float = 1, unit: str = "count",
    system_id: str | None = None, run_id: str | None = None,
    provider: str = "", model: str = "", language: str | None = None,
    cost_estimate_usd: float | None = None) -> dict: ...
def usage_summary(org_id: str, period: str = "month") -> dict: ...
def admin_cost_overview() -> dict: ...
def provider_credit_status() -> list[dict]: ...
```

Hook points (James wires, Jude's functions record): model calls (`core/infer/analyzer.py` failover chain, `core/repo_fix/generate.py`, `core/infer/baseten_client.py`, Meta direct calls), sandbox time (`core/verify/sandbox.py`, `core/repo_fix/run.py`), fix run start/finish, PR opened/commented, mitigation executed (done only), ingest lines, daily active systems/devices snapshot. `record_usage` fills `cost_estimate_usd` from `COST_TABLE` when not given and bumps the `allowances` counters in the same transaction.

**New API routes (frozen JSON; James builds, John mirrors in TS):**

```jsonc
// Orgs (all session-authed; org from membership, never from the client alone)
POST /api/orgs {"name": "Acme"} → {"org": {"id": "org_…", "name": "Acme", "role": "owner", "created_at": 0}}
GET  /api/orgs → {"orgs": [{"id": "org_…", "name": "Acme", "role": "admin"}]}
GET  /api/orgs/{id} → {"org": {…}, "role": "member"}
DELETE /api/orgs/{id} → {"deleted": true, "grace_until": 0}            // owner only; grace + export
GET  /api/orgs/{id}/members → {"members": [{"user_id": "usr_…", "email": "a@x.co", "name": "A", "role": "admin"}]}
POST /api/orgs/{id}/invites {"email": "b@x.co", "role": "member"} → {"invite": {"token": "…", "expires_at": 0}}
POST /api/invites/{token}/accept → {"org_id": "org_…", "role": "member"}
DELETE /api/orgs/{id}/members/{uid} → {"removed": true}
POST /api/orgs/{id}/transfer {"user_id": "usr_…"} → {"ok": true}        // owner only
// Phones per user (pair on web authed, claim on phone, token shown once)
POST /api/orgs/{id}/devices/pair {"label": "A's Pixel"} → {"code": "123-456", "expires_at": 0}
POST /api/devices/claim {"code": "123-456"} → {"device_token": "ta_dev_…", "org_id": "org_…"}
GET  /api/orgs/{id}/devices → {"devices": [{"id": "dev_…", "label": "…", "created_at": 0, "last_used_at": 0, "revoked": false}]}
POST /api/orgs/{id}/devices/{dev}/revoke → {"revoked": true}
// Usage (no prices anywhere)
GET /api/orgs/{id}/usage?period=month → {"fix_runs_used": 3, "fix_runs_limit": 30,
  "cost_used_usd": 1.2, "cost_ceiling_usd": 25.0, "systems_used": 1, "systems_limit": 3,
  "devices_used": 1, "devices_limit": 5, "by_language": {"python": {"fix_runs": 3, "cost_usd": 1.2}}}
// Internal (COMMERCE_ADMIN_EMAILS only, else 403)
GET /api/admin/costs → {"by_org": […], "by_language": {…}, "top_spenders": […],
  "provider_credit": [{"provider": "baseten", "remaining_usd": 71.0, "pct_used": 29}]}
```

Device-token auth: `Authorization: Bearer ta_dev_…` on approve/disapprove/pause/execute-option + `/api/actions` + `/api/runs*`. Session JWT: `Authorization: Bearer <Clerk JWT>` everywhere else non-public. Existing connection/ingest/device-key shapes unchanged.

### 8.5 Operating rules (from languages §6.0, adapted)

| | James | John | Jude |
|---|---|---|---|
| Worktree | `../telemetry-agent-james` | `../telemetry-agent-john` | `../telemetry-agent-jude` |
| Branch | `com/james` | `com/john` | `com/jude` |
| API port | 8101 | 8201 (web 3201) | 8301 |
| Data dir | `TA_DATA_DIR=/tmp/ta-james` | `TA_DATA_DIR=/tmp/ta-john` | `TA_DATA_DIR=/tmp/ta-jude` |
| Dev DB | `ta_james` | `ta_john` | `ta_jude` (all on `localhost:5432`, else `TEST_DATABASE_URL`) |
| Status file | `status/com-james.md` | `status/com-john.md` | `status/com-jude.md` |

- Fresh worktree: `git fetch origin && git worktree add ../telemetry-agent-<name> -b com/<name> origin/main`. Existing worktrees: `git fetch origin && git switch -c com/<name> origin/main`.
- **Never** use ports 8001, 8002, 3000 (Akingbade's live demo) or another agent's ports; never stop processes you didn't start.
- Secrets: `set -a; . ../telemetry-agent/.env; set +a`. Never print, log, echo, commit or paste a secret; never write `.env`. No real auth-provider production keys — test/dev mode only; list needed keys under NEEDS.
- **Model budget:** unit tests mock every model and GitHub call. Live model runs only through `scripts/lang_e2e.sh --live`, at most **3 live runs per language per agent per day**.

**Merge procedure (each checkpoint; your own branch only):**
```bash
git fetch origin
git rebase origin/main            # conflict in a file you don't own → git rebase --abort, note it under BLOCKED, keep working
./scripts/check.sh                # must exit 0 (runs with DATABASE_URL unset: sim route proof)
git push --force-with-lease origin HEAD:com/<name>
git push origin HEAD:main         # fast-forward only; if rejected, start again from git fetch
```
- Never `--force` to `main`. Keep the configured git identity; **no `Co-authored-by` or AI trailers**; prefix messages with the block id (`C-J1: postgres …`).
- Real GitHub writes only to `maximuskay2/telemetryAgent-demo`; close any PR you open while testing. No Railway deploys, no new repos, no publishing — list them under NEEDS.
- `check.sh` runs the suite with `DATABASE_URL` unset (sim proof) AND set against the test DB (DB proof) — C-J1 wires the second leg; until then the DB leg is a local `TEST_DATABASE_URL=… unittest` run noted in status.

**Status file (`status/com-<name>.md`, yours only; commit at every checkpoint):**
```markdown
# <Name> status (commercial)
Current block: …
Done: C-?1 (sha), …
Decisions: …
Contract changes requested: …
Live runs (lang · result · seconds · model): …
NEEDS FROM AKINGBADE: …
BLOCKED: …
```

**Working style:** autonomous to the end of your list; ambiguity → choose what fits this roadmap (safety first, then §8.1 rules), note it under *Decisions*, continue. Test-first for each acceptance row. **Done** = your acceptance rows pass, `check.sh` green on `main`, status complete, docs written.

### 8.6 Build blocks

### 👷 James: backend core

| Block | Work | Acceptance (automated unless noted) |
|---|---|---|
| **C-J0** H0 team plan | This §8 + tag `commercial-contracts-in` | Tag on `main`; John + Jude confirm the §8 contracts in their status files |
| **C-J1** Phase 0 foundations | Postgres repo + `schema.sql` + boot select (DB vs file); encrypted secrets; staging/prod config; `docs/ops-backups.md` | API boots against Postgres; full suite green with the DB fixture; `smoke_demo.sh` green with `DATABASE_URL` unset; secrets-at-rest test (ciphertext in DB, hint only via API) |
| **C-J2** Phase 1 API | JWT session auth + middleware (§8.3) + org/member/invite/device routes (§8.4); per-user device tokens; self-hosted fallback | Signup→org→invite→remove flow tests; removed member's session + phone token dead immediately; viewer approve → 403; pair/claim/revoke tests |
| **C-J3** Phase 2 isolation | `org_id` everywhere; RLS on; org-scoped EventHub + WS token; per-org pause/rate/fingerprints; `scripts/commerce-migrate.py` legacy import | All org tables RLS-enforced (direct-SQL bypass test); cross-org WS gets nothing; pause in A leaves B running; legacy JSON imports into `legacy` org |
| **C-J4** Isolation suite | `tests/test_com_isolation.py`: two-org matrix over every endpoint + WS (read/list/test/delete/approve, ID guessing, key cross-use) | Suite green in CI; pen-test-style checklist in status |
| **C-J5** Phase-5 fit | Org export + deletion API; retention sweep for logs/snapshots; restore-drill record | Export round-trips; deleted org's rows gone; drill log in `docs/ops-backups.md` |

### 👷 John: sales look + screens

| Block | Work | Acceptance |
|---|---|---|
| **C-N1** Sales look, web | Light default + dark toggle (persisted), Optimistic-first type, Meta surfaces on welcome/demo/Mission Control/shop/setup/connect, "Built with Muse Spark", no logos/ownership claims | Fresh browser opens light; toggle survives reload; fallback stack without Optimistic; checklist + screenshots in status |
| **C-N2** Sales look, phone | Phone matches the web pass | Same checklist on device |
| **C-N3** Phase 1 web | Sign-in, org switcher, members, devices pages against §8.4 JSON | Route tests with mocked API incl. 403-viewer case |
| **C-N4** Phase 1 app | Sign-in, devices, approve flow against §8.4 JSON | `flutter test` widget tests incl. revoked-token case |
| **C-N5** Usage + help | Customer Usage page (no prices) + `docs/USAGE.md` accounts/usage help | Component test shows allowance + why-blocked; doc checklist |

### 👷 Jude: usage + allowance (Baseten)

| Block | Work | Acceptance |
|---|---|---|
| **C-D1** Usage recorder | `costs.py` (cost table) + `record_usage` + `usage_summary` vs the §8.3 shape, coded to §8.4 before the repo lands | Unit tests on a fake repo: every §3 kind records with language + cost |
| **C-D2** Allowance | `allowance(org_id)` + abuse guards (ingest lines/min, runs/hour) + reached-allowance gate decision | Unit tests: over-allowance org blocked with reason; monitoring path untouched |
| **C-D3** Admin data | `admin_cost_overview` + `provider_credit_status` (50/80/95 % alerts) | Unit tests on fixture events incl. credit thresholds |
| **C-D4** Wire-in proof | After C-J3: real fix run carries cost; test org over allowance gets no runs and sees why | E2E (mocked models): cost on run; blocked run decision logged |

### 🤝 Together

| Block | Work | Acceptance |
|---|---|---|
| **T-C1** Gate | C-J4 suite green on `main` after everyone's last merge; Phase-5-fit leftovers | Isolation suite green; first real (free) customer drill recorded (NEEDS Akingbade) |

### 8.7 Log (fill in while building)
