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
