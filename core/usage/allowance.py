"""Free fair-use allowance: the gate before a fix run spends anything.

FREE for now: generous limits from config, no payments. After the
commercial-contracts-in tag this is checked at the top of the fix-run
path — monitoring and alerts keep working when the allowance is hit,
only spending stops.

Limits (all overridable via env):
  systems / devices on the org:      3 / 5
  fix runs per calendar month (UTC): 30
  estimated provider cost / month:   $25
Abuse guards (per org, sliding windows):
  ingest lines per minute:           10_000
  fix runs started per hour:         10
Per-run sanity caps (for the runner, enforced post-tag):
  sandbox wall time:                 30 minutes
  model tokens (in + out):           500_000
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from core.usage.events import Kind, UsageStore


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------

def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


@dataclass(frozen=True)
class AllowanceLimits:
    systems: int = 3
    devices: int = 5
    fix_runs_per_month: int = 30
    monthly_cost_usd: float = 25.0
    ingest_lines_per_minute: int = 10_000
    fix_runs_per_hour: int = 10
    max_sandbox_minutes_per_run: int = 30
    max_tokens_per_run: int = 500_000


def load_limits() -> AllowanceLimits:
    return AllowanceLimits(
        systems=_env_int("TA_FREE_SYSTEMS", 3),
        devices=_env_int("TA_FREE_DEVICES", 5),
        fix_runs_per_month=_env_int("TA_FREE_FIX_RUNS_PER_MONTH", 30),
        monthly_cost_usd=_env_float("TA_FREE_MONTHLY_COST_USD", 25.0),
        ingest_lines_per_minute=_env_int("TA_ABUSE_INGEST_LINES_PER_MIN", 10_000),
        fix_runs_per_hour=_env_int("TA_ABUSE_FIX_RUNS_PER_HOUR", 10),
        max_sandbox_minutes_per_run=_env_int("TA_MAX_SANDBOX_MINUTES_PER_RUN", 30),
        max_tokens_per_run=_env_int("TA_MAX_TOKENS_PER_RUN", 500_000),
    )


# ---------------------------------------------------------------------------
# allowance check
# ---------------------------------------------------------------------------

def month_start(now: Optional[float] = None) -> float:
    """Epoch of the current calendar-month start (UTC)."""
    dt = datetime.fromtimestamp(time.time() if now is None else now,
                                tz=timezone.utc)
    return datetime(dt.year, dt.month, 1, tzinfo=timezone.utc).timestamp()


def month_end(now: Optional[float] = None) -> float:
    """Epoch of the next calendar-month start (UTC)."""
    dt = datetime.fromtimestamp(time.time() if now is None else now,
                                tz=timezone.utc)
    year = dt.year + (1 if dt.month == 12 else 0)
    month = dt.month % 12 + 1
    return datetime(year, month, 1, tzinfo=timezone.utc).timestamp()


_COMPLETED_RUN_UNITS = frozenset({"run_pass", "run_draft", "run_failed"})


@dataclass(frozen=True)
class AllowanceDecision:
    allowed: bool
    reason: str  # "" when allowed; "free allowance reached: ..." otherwise
    used: dict = field(default_factory=dict)      # what the org consumed
    limits: dict = field(default_factory=dict)    # the limits applied
    remaining: dict = field(default_factory=dict)  # limits minus used


def _latest_snapshot(store: UsageStore, org_id: str, kind: str) -> Optional[float]:
    rows = store.query(org_id=org_id, kinds=[kind])
    if not rows:
        return None
    return max(rows, key=lambda e: e.at).quantity


def allowance(org_id: str,
              store: UsageStore,
              *,
              systems: Optional[int] = None,
              devices: Optional[int] = None,
              now: Optional[float] = None,
              limits: Optional[AllowanceLimits] = None) -> AllowanceDecision:
    """Can this org start a fix run? Pure read of the usage store.

    `systems` / `devices`: live counts when the caller knows them;
    otherwise the latest *_snapshot events are used, and the check is
    skipped when neither exists.
    """
    lim = limits or load_limits()
    ts = time.time() if now is None else now
    start, end = month_start(ts), month_end(ts)

    runs = store.query(org_id=org_id, kinds=[Kind.FIX_RUN],
                       since=start, until=end)
    fix_runs_used = sum(1 for e in runs if e.unit in _COMPLETED_RUN_UNITS)

    spend_rows = store.query(org_id=org_id, since=start, until=end)
    cost_used = round(sum(e.cost_estimate_usd for e in spend_rows), 6)

    sys_count = (systems if systems is not None
                 else _latest_snapshot(store, org_id, Kind.SYSTEMS))
    dev_count = (devices if devices is not None
                 else _latest_snapshot(store, org_id, Kind.DEVICES))

    used = {"fix_runs": fix_runs_used, "cost_usd": cost_used}
    lims = {"fix_runs": lim.fix_runs_per_month,
            "cost_usd": lim.monthly_cost_usd}
    if sys_count is not None:
        used["systems"] = int(sys_count)
        lims["systems"] = lim.systems
    if dev_count is not None:
        used["devices"] = int(dev_count)
        lims["devices"] = lim.devices
    remaining = {k: round(lims[k] - used[k], 6) for k in used}

    def blocked(reason: str) -> AllowanceDecision:
        return AllowanceDecision(
            allowed=False,
            reason=f"free allowance reached: {reason}",
            used=used, limits=lims, remaining=remaining)

    if fix_runs_used >= lim.fix_runs_per_month:
        return blocked(f"{fix_runs_used}/{lim.fix_runs_per_month} fix runs "
                       f"used this month")
    if cost_used >= lim.monthly_cost_usd:
        return blocked(f"${cost_used:.2f}/${lim.monthly_cost_usd:.2f} "
                       f"estimated provider cost used this month")
    if sys_count is not None and int(sys_count) >= lim.systems:
        return blocked(f"{int(sys_count)}/{lim.systems} systems connected")
    if dev_count is not None and int(dev_count) >= lim.devices:
        return blocked(f"{int(dev_count)}/{lim.devices} devices connected")
    return AllowanceDecision(allowed=True, reason="",
                             used=used, limits=lims, remaining=remaining)


# ---------------------------------------------------------------------------
# abuse guards (sliding windows, per org)
# ---------------------------------------------------------------------------

def check_ingest_rate(org_id: str,
                      store: UsageStore,
                      lines: int = 1,
                      *,
                      now: Optional[float] = None,
                      limits: Optional[AllowanceLimits] = None) -> tuple[bool, str]:
    """True unless this batch would burst the per-minute ingest cap."""
    lim = limits or load_limits()
    ts = time.time() if now is None else now
    try:
        n = max(0, int(lines))
    except (TypeError, ValueError):
        n = 0
    recent = store.query(org_id=org_id, kinds=[Kind.INGEST], since=ts - 60.0)
    total = sum(e.quantity for e in recent) + n
    if total > lim.ingest_lines_per_minute:
        return False, (f"ingest burst guard: {int(total)} lines/min > "
                       f"{lim.ingest_lines_per_minute}")
    return True, ""


def check_fix_run_rate(org_id: str,
                       store: UsageStore,
                       *,
                       now: Optional[float] = None,
                       limits: Optional[AllowanceLimits] = None) -> tuple[bool, str]:
    """True unless the org started too many fix runs in the last hour."""
    lim = limits or load_limits()
    ts = time.time() if now is None else now
    recent = store.query(org_id=org_id, kinds=[Kind.FIX_RUN], since=ts - 3600.0)
    started = sum(1 for e in recent if e.unit == "run_started")
    if started >= lim.fix_runs_per_hour:
        return False, (f"fix-run burst guard: {started} starts/hour >= "
                       f"{lim.fix_runs_per_hour}")
    return True, ""
