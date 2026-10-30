# Jude status (commercial — Phase 3 usage + free allowance)

Current block: pre-tag pure code (cost table, recorder, allowance, credit alerts)

Branch: com/jude (from origin/main 89e8bdd). No `commercial-*` tag yet — building tag-free per the roadmap order (pure modules + tests, no integration edits until James's contracts land).

Done: pre-tag pure package `core/usage/` (costs.py: Baseten/Meta/Fireworks token rates + Modal/docker sandbox rates, all with provenance, env-overridable; events.py: UsageEvent 10-field contract + record_* helpers + Memory/JsonlUsageStore; allowance.py: free limits 3 systems / 5 devices / 30 runs/mo / $25/mo + burst guards; alerts.py: Baseten/Modal credit alerts at 50/80/95) + tests/test_usage.py (41 tests OK). No integration edits yet — still awaiting `commercial-contracts-in` (checked: no commercial tag).

Plan:
1. `core/usage/` package: `costs.py` (provider/model/sandbox price table → cost_estimate_usd), `store.py` (usage-event recorder, file-backed JSONL + in-memory; shape is the contract, Postgres comes from James Phase 0), `allowance.py` (free fair-use limits + remaining/blocked check), `alerts.py` (provider credit 50/80/95%).
2. `tests/test_usage*.py` for all of it (no DB, no network).
3. After `commercial-contracts-in`: hook the §3 table (analyzer, generate, baseten/meta clients, sandbox exec, runs, PRs, mitigations, ingest, snapshots), gate fix runs on allowance ("free allowance reached", monitoring/alerts unaffected), per-org abuse guards, usage + admin APIs for John.
4. NEVER Phase 4: no prices shown, no checkout, no Stripe.

Live runs (commercial): none (no model calls in pre-tag work)

NEEDS FROM AKINGBADE: none

BLOCKED: post-tag wiring waits on James's contracts tag (expected; building tag-free meanwhile)
