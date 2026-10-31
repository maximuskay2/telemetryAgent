# Jude status (commercial)

Current block: C-D4 merged to main — next: T-C1 gate (waits on James C-J4 + team's last merges)

Done: pre-tag `core/usage/` engine (cb0be7c on main), C-D1 (usage recorder vs §8.3), C-D2 (allowance gate + abuse guards), C-D3 (admin data) — all on main (4820876); C-D4 wire-in proof (`tests/test_com_wirein.py`, mocked-models E2E: cost on PASS run, blocked-with-reason over allowance) — merged to main; full suite 1050 green; synced to origin/main a0e4352 (John C-N8)

Decisions:
- §8 contracts CONFIRMED (C-J0 acceptance): building `core/commerce/{usage,allowance,costs}.py` to the frozen §8.4 signatures; `usage_events` carries `model` per §8.3; no `core/commerce/__init__.py` (James's file) — namespace package, verified importable, survives his later `__init__`.
- Kind/unit strings are not frozen in §8.4, so hooks import the vocabulary: `from core.commerce.usage import Kind` (model_call/tokens_in|out, sandbox_time/seconds, fix_run/run_started|run_pass|run_draft|run_failed, pr/pr_opened|comment, mitigation/action:<a>, ingest/lines, systems|devices/count). James: please use these constants in the hook calls.
- `record_usage` never raises (coerces junk, returns `store_error` dict on storage failure); cost auto-fill for model/sandbox only, else 0 unless given.
- `allowance()` remaining for systems/devices with no snapshot = FULL limit (nothing recorded = nothing used); over-allowance clamps remaining at 0, reason keeps the frozen "free allowance reached: …" shape.
- `usage_summary` periods: "month" (default) + "all"; snapshots are current-state (latest overall, not period-bound).
- `provider_credit_status` skips providers with no positive credit (avoids div-by-zero); `admin_cost_overview` shows raw remaining (may go negative past 100%).
- Backend is module-global via `configure_usage_store` (frozen sigs take no store); default file JSONL, TA_DATA_DIR-aware per call. James's Postgres repo plugs the same `UsageStore` interface later.
- e2e php NO_ACTION flake analyzed: transient in-sandbox `composer install` network failures (25 fresh dists, no cache), not order-dependent (fails isolated too, matrix 7/7 alone green); image + flags verified healthy (6/6 manual). No adapter change (prod-path risk); gate green on retry per session pattern.
- Setup 31 Oct (Akingbade): Baseten credit finished — on Meta Muse login like James/John; `scripts/muse-baseten.sh` retired (absent from tree); no live Baseten runs (`lang_e2e.sh --live`, live proofs) without asking Akingbade first; generation falls back to Muse Wonder. No C-D4 impact (acceptance is mocked-models E2E).
- C-J3 hook contract verified vs c89c60e (read-only, no stack): hooks call `core.commerce.usage.record_usage` + `allowance` with matching shapes — fix_run completion units run_pass/run_draft/run_failed match `_COMPLETED_RUN_UNITS`; sandbox_time auto-costs via provider; over-allowance blocks in `maybe_trigger` + `_record_blocked`. Store loop closes through the engine store (`configure_usage_store`) — PG persist-through not needed for the mocked E2E proof. Gaps for James (his files): model_call unhooked (LLM spend invisible; run cost = sandbox_time only); raw kind/unit strings, not Kind constants (match today — drift risk).
- C-D4 proof design: hosted mode faked with unreachable DATABASE_URL (PG calls fail safe into fast warnings); usage/allowance real on MemoryUsageStore; fake-backend sandbox rate pinned via `TA_COST_FAKE_SANDBOX_S` (deterministic cost wiring proof); blocked test stubs only the PG profile/connection reads; frozen "free allowance reached" reason asserted on the real `gate_decisions` record. 2 new tests, 137 commerce+pipeline green, full discover 1050 green.

Contract changes requested: none (§8 frozen stands; Kind import is a coordination note, not a change)

Live runs (lang · result · seconds · model): none this round (mocked + unit only)

NEEDS FROM AKINGBADE:
- Modal remaining hackathon credit numbers (Baseten leg dropped — credit finished per Akingbade 31 Oct; alerts still assume $100 pools; see also James's NEEDS).
- (James) hook calls import Kind from core.commerce.usage (see Decisions); model_call hook in the generate path (LLM spend currently invisible to usage/cost).

BLOCKED: none
