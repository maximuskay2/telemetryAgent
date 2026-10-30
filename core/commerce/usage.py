"""Commercial §8.4: usage recorder + summaries (Jude owns).

Frozen surface: `COST_TABLE`, `record_usage`, `usage_summary`,
`admin_cost_overview`, `provider_credit_status`. James's pipeline
hooks call `record_usage`; his routes serve the summaries to John's
pages. Engine: `core.usage` (file store default); James's Postgres
repo plugs in later via `configure_usage_store` (same `UsageStore`
interface, so the frozen functions don't change).

Kind/unit vocabulary (§8.4 doesn't freeze the strings; hooks should
import `Kind` from here so both sides stay in sync):

    Kind.MODEL_CALL   "model_call"    units "tokens_in" | "tokens_out"
    Kind.SANDBOX_TIME "sandbox_time"  unit "seconds" (provider = backend)
    Kind.FIX_RUN      "fix_run"       units "run_started" | "run_pass" |
                                      "run_draft" | "run_failed"
    Kind.PR           "pr"            units "pr_opened" | "pr_comment"
    Kind.MITIGATION   "mitigation"    unit "action:<action>"
    Kind.INGEST       "ingest"        unit "lines"
    Kind.SYSTEMS      "systems"       unit "count" (daily snapshot)
    Kind.DEVICES      "devices"       unit "count" (daily snapshot)

Costs: `record_usage` fills `cost_estimate_usd` from COST_TABLE for
model calls and sandbox time when the caller doesn't pass one;
everything else defaults to 0. Recording never raises — a usage
hook must not break the pipeline it measures.
"""

from __future__ import annotations

import time
from typing import Optional

from core.commerce.costs import COST_TABLE  # noqa: F401  (frozen §8.4 name)
from core.commerce import costs as _costs
from core.usage import alerts as _alerts
from core.usage.allowance import (
    load_limits as _load_limits,
    month_end as _month_end,
    month_start as _month_start,
)
from core.usage.events import (
    JsonlUsageStore,
    Kind,
    MemoryUsageStore,  # noqa: F401 (re-exported for fakes/tests)
    UsageEvent,
    UsageStore,
)

__all__ = [
    "COST_TABLE",
    "Kind",
    "MemoryUsageStore",
    "UsageEvent",
    "UsageStore",
    "admin_cost_overview",
    "allowance_limits",
    "configure_usage_store",
    "provider_credit_status",
    "record_usage",
    "reset_usage_store",
    "usage_summary",
]


# ---------------------------------------------------------------------------
# backend (module-global: the frozen signatures take no store)
# ---------------------------------------------------------------------------

_configured_store: Optional[UsageStore] = None


def configure_usage_store(store: UsageStore) -> None:
    """Plug a backend (tests use MemoryUsageStore; James's repo later)."""
    global _configured_store
    _configured_store = store


def reset_usage_store() -> None:
    """Back to the default file store (TA_DATA_DIR-aware per call)."""
    global _configured_store
    _configured_store = None


def _store() -> UsageStore:
    if _configured_store is not None:
        return _configured_store
    return JsonlUsageStore()


def allowance_limits() -> dict:
    """Current free-allowance numbers (config; John's pages mirror them)."""
    lim = _load_limits()
    return {
        "systems_limit": lim.systems,
        "devices_limit": lim.devices,
        "fix_runs_limit": lim.fix_runs_per_month,
        "cost_ceiling_usd": lim.monthly_cost_usd,
    }


# ---------------------------------------------------------------------------
# record
# ---------------------------------------------------------------------------

_COMPLETED_RUN_UNITS = frozenset({"run_pass", "run_draft", "run_failed"})


def _to_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def record_usage(org_id: str,
                 kind: str,
                 quantity: float = 1,
                 unit: str = "count",
                 system_id: str | None = None,
                 run_id: str | None = None,
                 provider: str = "",
                 model: str = "",
                 language: str | None = None,
                 cost_estimate_usd: float | None = None) -> dict:
    """Record one usage event (§8.3 shape). Never raises.

    `cost_estimate_usd` is computed from COST_TABLE for model calls
    (tokens_in/out × provider+model rate) and sandbox time (seconds ×
    backend rate) when not given; other kinds default to 0. Returns
    the recorded event as a dict.
    """
    try:
        qty = max(0.0, _to_float(quantity))
    except Exception:
        qty = 0.0
    kind_s, unit_s = str(kind or ""), str(unit or "count")
    provider_s, model_s = str(provider or ""), str(model or "")
    if cost_estimate_usd is None:
        try:
            if kind_s == Kind.MODEL_CALL and unit_s == "tokens_in":
                rate = _costs.rate_for(provider_s, model_s)
                cost = qty / 1_000_000 * rate.input_usd_per_1m
            elif kind_s == Kind.MODEL_CALL and unit_s == "tokens_out":
                rate = _costs.rate_for(provider_s, model_s)
                cost = qty / 1_000_000 * rate.output_usd_per_1m
            elif kind_s == Kind.SANDBOX_TIME:
                cost = _costs.cost_of_sandbox(provider_s, qty)
            else:
                cost = 0.0
        except Exception:
            cost = 0.0
    else:
        cost = max(0.0, _to_float(cost_estimate_usd))
    try:
        event = _store().record(UsageEvent(
            org_id=str(org_id or ""),
            system_id=str(system_id or ""),
            run_id=str(run_id or ""),
            kind=kind_s,
            quantity=qty,
            unit=unit_s,
            provider=provider_s,
            language=str(language or ""),
            cost_estimate_usd=cost,
            at=time.time(),
            model=model_s,
        ))
        return event.to_dict()
    except Exception:
        # Storage failure must not break the measured pipeline.
        return {
            "org_id": str(org_id or ""), "system_id": str(system_id or ""),
            "run_id": str(run_id or ""), "kind": kind_s,
            "quantity": qty, "unit": unit_s, "provider": provider_s,
            "model": model_s, "language": str(language or ""),
            "cost_estimate_usd": cost, "at": time.time(),
            "store_error": True,
        }


# ---------------------------------------------------------------------------
# summaries
# ---------------------------------------------------------------------------

def _period_window(period: str) -> tuple[float | None, float | None]:
    if period == "all":
        return None, None
    now = time.time()
    return _month_start(now), _month_end(now)


def _latest_snapshot(store: UsageStore, org_id: str, kind: str) -> float:
    rows = store.query(org_id=org_id, kinds=[kind])
    if not rows:
        return 0.0
    return max(rows, key=lambda e: e.at).quantity


def _by_language(rows: list[UsageEvent]) -> dict:
    per_lang: dict[str, dict[str, float]] = {}
    for e in rows:
        if not e.language:
            continue
        slot = per_lang.setdefault(e.language, {"fix_runs": 0, "cost_usd": 0.0})
        if e.kind == Kind.FIX_RUN and e.unit in _COMPLETED_RUN_UNITS:
            slot["fix_runs"] += 1
        slot["cost_usd"] += e.cost_estimate_usd
    return {lang: {"fix_runs": int(v["fix_runs"]),
                   "cost_usd": round(v["cost_usd"], 4)}
            for lang, v in sorted(per_lang.items())}


def usage_summary(org_id: str, period: str = "month") -> dict:
    """Customer Usage page data (no prices anywhere).

    `period`: "month" (current calendar month, UTC) or "all".
    systems/devices come from the latest snapshot events (0 until
    the snapshot job runs).
    """
    store = _store()
    since, until = _period_window(period)
    rows = store.query(org_id=org_id, since=since, until=until)
    lim = _load_limits()
    fix_runs = sum(1 for e in rows
                   if e.kind == Kind.FIX_RUN
                   and e.unit in _COMPLETED_RUN_UNITS)
    cost = round(sum(e.cost_estimate_usd for e in rows), 4)
    return {
        "fix_runs_used": fix_runs,
        "fix_runs_limit": lim.fix_runs_per_month,
        "cost_used_usd": cost,
        "cost_ceiling_usd": lim.monthly_cost_usd,
        "systems_used": int(_latest_snapshot(store, org_id, Kind.SYSTEMS)),
        "systems_limit": lim.systems,
        "devices_used": int(_latest_snapshot(store, org_id, Kind.DEVICES)),
        "devices_limit": lim.devices,
        "by_language": _by_language(rows),
    }


def admin_cost_overview() -> dict:
    """Internal admin data: cost per org + language, top spenders, credit."""
    store = _store()
    rows = store.query()
    by_org: dict[str, dict[str, float]] = {}
    for e in rows:
        slot = by_org.setdefault(e.org_id, {"fix_runs": 0, "cost_usd": 0.0})
        if e.kind == Kind.FIX_RUN and e.unit in _COMPLETED_RUN_UNITS:
            slot["fix_runs"] += 1
        slot["cost_usd"] += e.cost_estimate_usd
    org_rows = [{"org_id": org, "fix_runs": int(v["fix_runs"]),
                 "cost_usd": round(v["cost_usd"], 2)}
                for org, v in sorted(by_org.items())]
    top = sorted(org_rows, key=lambda r: r["cost_usd"], reverse=True)[:10]
    credit = [
        {"provider": c["provider"],
         "remaining_usd": round(c["credit_usd"] - c["spent_usd"], 2),
         "pct_used": round(c["pct"], 1)}
        for c in provider_credit_status()
    ]
    return {
        "by_org": org_rows,
        "by_language": _by_language(rows),
        "top_spenders": [{"org_id": r["org_id"], "cost_usd": r["cost_usd"]}
                         for r in top],
        "provider_credit": credit,
    }


def provider_credit_status() -> list[dict]:
    """Our hackathon pools: spent vs credit per provider.

    `level` is the highest breached alert (50/80/95) or None below 50.
    Providers with no positive credit configured are skipped.
    """
    store = _store()
    out = []
    for provider, credit in sorted(_alerts.provider_credits().items()):
        if credit <= 0:
            continue
        spent = _alerts.provider_spend(store, provider)
        pct = spent / credit * 100.0
        level = None
        for mark in _alerts.ALERT_LEVELS:
            if pct >= mark:
                level = mark
        out.append({
            "provider": provider,
            "spent_usd": round(spent, 2),
            "credit_usd": round(credit, 2),
            "pct": round(pct, 2),
            "level": level,
        })
    return out
