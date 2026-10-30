# Jude status (commercial)

Current block: C-D4 Wire-in proof (waits on James C-J3; hooks are his files)

Done: pre-tag `core/usage/` engine (cb0be7c on main), C-D1 (usage recorder vs §8.3), C-D2 (allowance gate + abuse guards), C-D3 (admin data) — this commit

Decisions:
- §8 contracts CONFIRMED (C-J0 acceptance): building `core/commerce/{usage,allowance,costs}.py` to the frozen §8.4 signatures; `usage_events` carries `model` per §8.3; no `core/commerce/__init__.py` (James's file) — namespace package, verified importable, survives his later `__init__`.
- Kind/unit strings are not frozen in §8.4, so hooks import the vocabulary: `from core.commerce.usage import Kind` (model_call/tokens_in|out, sandbox_time/seconds, fix_run/run_started|pass|draft|failed, pr/pr_opened|comment, mitigation/action:<a>, ingest/lines, systems|devices/count). James: please use these constants in the hook calls.
- `record_usage` never raises (coerces junk, returns `store_error` dict on storage failure); cost auto-fill for model/sandbox only, else 0 unless given.
- `allowance()` remaining for systems/devices with no snapshot = FULL limit (nothing recorded = nothing used); over-allowance clamps remaining at 0, reason keeps the frozen "free allowance reached: …" shape.
- `usage_summary` periods: "month" (default) + "all"; snapshots are current-state (latest overall, not period-bound).
- `provider_credit_status` skips providers with no positive credit (avoids div-by-zero); `admin_cost_overview` shows raw remaining (may go negative past 100%).
- Backend is module-global via `configure_usage_store` (frozen sigs take no store); default file JSONL, TA_DATA_DIR-aware per call. James's Postgres repo plugs the same `UsageStore` interface later.
- e2e php NO_ACTION flake analyzed: transient in-sandbox `composer install` network failures (25 fresh dists, no cache), not order-dependent (fails isolated too, matrix 7/7 alone green); image + flags verified healthy (6/6 manual). No adapter change (prod-path risk); gate green on retry per session pattern.

Contract changes requested: none (§8 frozen stands; Kind import is a coordination note, not a change)

Live runs (lang · result · seconds · model): none this round (mocked + unit only)

NEEDS FROM AKINGBADE:
- Baseten/Modal remaining hackathon credit numbers (alerts currently assume $100 pools; see also James's NEEDS).
- (James) hook calls import Kind from core.commerce.usage (see Decisions).

BLOCKED: C-D4 proof waits on James C-J3 (pipeline hooks + org keying are his files)
