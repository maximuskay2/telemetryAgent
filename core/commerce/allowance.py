"""Commercial §8.4: free allowance gate (Jude owns; James calls it).

`allowance(org_id)` is the one function the pipeline checks before a
fix run starts, before a mitigation executes, and at system/device
creation. Over allowance → skip the spend, record a gate-style
decision ("free allowance reached: ..."), notify the owner.
Monitoring and alerts continue. Phase 4 later swaps this for
paid-plan entitlements without touching callers.

Reads the same backend `core.commerce.usage` writes (configured via
`configure_usage_store`; default file store). Counts come from usage
events alone: completed fix runs + spend in the calendar month,
latest systems/devices snapshots (missing snapshot = nothing
recorded = full remaining).
"""

from __future__ import annotations

from dataclasses import dataclass

from core.commerce import usage as _usage
from core.usage.allowance import (
    allowance as _engine_allowance,
    check_fix_run_rate as _engine_fix_run_rate,
    check_ingest_rate as _engine_ingest_rate,
    load_limits as _load_limits,
)


@dataclass
class AllowanceStatus:
    allowed_fix_run: bool
    reason: str = ""            # e.g. "free allowance reached: 30/30 fix runs"
    fix_runs_remaining: int = 0
    cost_remaining_usd: float = 0.0
    systems_remaining: int = 0
    devices_remaining: int = 0


def allowance(org_id: str) -> AllowanceStatus:
    """Can this org spend on a fix run / mitigation / new system?"""
    store = _usage._store()  # same backend the recorder writes to
    lim = _load_limits()
    decision = _engine_allowance(org_id, store)
    remaining = decision.remaining
    return AllowanceStatus(
        allowed_fix_run=decision.allowed,
        reason=decision.reason,
        fix_runs_remaining=max(0, int(remaining.get(
            "fix_runs", lim.fix_runs_per_month))),
        cost_remaining_usd=max(0.0, round(float(remaining.get(
            "cost_usd", lim.monthly_cost_usd)), 4)),
        systems_remaining=max(0, int(remaining.get(
            "systems", lim.systems))),
        devices_remaining=max(0, int(remaining.get(
            "devices", lim.devices))),
    )


def check_ingest_rate(org_id: str, lines: int = 1) -> tuple[bool, str]:
    """Abuse guard: False when this batch bursts the per-minute cap."""
    allowed, reason = _engine_ingest_rate(
        org_id, _usage._store(), lines=lines)
    return allowed, reason


def check_fix_run_rate(org_id: str) -> tuple[bool, str]:
    """Abuse guard: False when the org started too many runs this hour."""
    allowed, reason = _engine_fix_run_rate(org_id, _usage._store())
    return allowed, reason
