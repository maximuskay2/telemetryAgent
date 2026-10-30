"""Commercial Phase 3: usage tracking, free allowance, provider alerts.

Pure code (no DB, no network): James's Phase 0 Postgres work swaps the
store backend later; the event SHAPE here is the contract.
"""

from core.usage.alerts import CreditAlert, credit_alerts, provider_spend
from core.usage.allowance import (
    AllowanceDecision,
    allowance,
    check_fix_run_rate,
    check_ingest_rate,
)
from core.usage.costs import (
    cost_of_sandbox,
    cost_of_tokens,
    rate_for,
)
from core.usage.events import (
    JsonlUsageStore,
    Kind,
    MemoryUsageStore,
    UsageEvent,
    UsageStore,
    record_fix_run,
    record_ingest,
    record_mitigation,
    record_model_call,
    record_pr,
    record_sandbox_time,
    record_snapshot,
)

__all__ = [
    "AllowanceDecision",
    "CreditAlert",
    "JsonlUsageStore",
    "Kind",
    "MemoryUsageStore",
    "UsageEvent",
    "UsageStore",
    "allowance",
    "check_fix_run_rate",
    "check_ingest_rate",
    "cost_of_sandbox",
    "cost_of_tokens",
    "credit_alerts",
    "provider_spend",
    "rate_for",
    "record_fix_run",
    "record_ingest",
    "record_mitigation",
    "record_model_call",
    "record_pr",
    "record_sandbox_time",
    "record_snapshot",
]
