"""Provider-credit alerts: 50 / 80 / 95 % of the hackathon pools.

Burn-down of OUR credits (Baseten $100, Modal $100 — env-overridable),
computed from recorded usage events across ALL orgs. The admin page
polls credit_alerts() and pages the team at 80/95; model-call sites
keep working — alerts never gate traffic.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from core.usage.events import Kind, UsageStore

# (provider, default credit USD, env override)
_CREDITS: tuple[tuple[str, float, str], ...] = (
    ("baseten", 100.0, "TA_CREDIT_BASETEN_USD"),
    ("modal", 100.0, "TA_CREDIT_MODAL_USD"),
)

ALERT_LEVELS: tuple[float, ...] = (50.0, 80.0, 95.0)


@dataclass(frozen=True)
class CreditAlert:
    provider: str
    spent_usd: float
    credit_usd: float
    pct: float    # spent / credit * 100
    level: float  # highest breached ALERT_LEVEL


def _credit_usd(provider: str, default: float, env: str) -> float:
    try:
        return float(os.environ.get(env, "").strip() or default)
    except ValueError:
        return default


def provider_spend(store: UsageStore, provider: str) -> float:
    """Total recorded USD for a provider, all orgs, all time.

    Model calls carry provider=<provider>; sandbox time carries
    provider=<backend> ("modal"/"docker"), so Modal spend is the sum
    of its model-call events (none today — Modal only hosts sandboxes)
    and its sandbox-time events.
    """
    provider = (provider or "").lower()
    rows = store.query(provider=provider)
    kinds = {Kind.MODEL_CALL, Kind.SANDBOX_TIME}
    return round(sum(e.cost_estimate_usd for e in rows
                     if e.kind in kinds), 6)


def credit_alerts(store: UsageStore) -> list[CreditAlert]:
    """One alert per provider at/above 50%, else none. Sorted by provider."""
    out: list[CreditAlert] = []
    for provider, default, env in _CREDITS:
        credit = _credit_usd(provider, default, env)
        if credit <= 0:
            continue
        spent = provider_spend(store, provider)
        pct = spent / credit * 100.0
        breached: Optional[float] = None
        for level in ALERT_LEVELS:
            if pct >= level:
                breached = level
        if breached is not None:
            out.append(CreditAlert(
                provider=provider,
                spent_usd=round(spent, 2),
                credit_usd=round(credit, 2),
                pct=round(pct, 2),
                level=breached))
    return sorted(out, key=lambda a: a.provider)
