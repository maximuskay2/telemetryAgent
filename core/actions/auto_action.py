"""Server-owned auto-action windows (M0): 20-second veto for verified fixes.

The phone only displays the countdown and sends a decision; the server acts
at the deadline even if no device ever responds. Only verified actions open
windows: software PASS runs with fail-to-pass evidence on the real target,
and appliance PASS runs whose runbook cleared `validate_runbook`.
"""

from __future__ import annotations

import os
from typing import Literal, Optional

from pydantic import BaseModel, Field

ActionState = Literal[
    "pending", "approved", "disapproved", "auto_applied", "expired", "failed"
]


class PendingAction(BaseModel):
    run_id: str
    domain: Literal["software", "appliance"]
    action: str = Field(description="Human summary of what auto-apply will do")
    opened_at: float = Field(description="Epoch seconds when the window opened")
    deadline: float = Field(description="Epoch seconds when the server acts")
    state: ActionState = "pending"
    decided_by: Optional[str] = Field(
        default=None, description="Device label that decided, if any"
    )
    resolved_at: Optional[float] = None
    detail: str = Field(default="", description="Apply outcome or failure reason")
    auto_apply: bool = Field(
        default=True,
        description="False means the window expires unless explicitly approved",
    )
    ready: bool = Field(
        default=True,
        description="False while the fix is still verifying: nothing applies and the countdown has not started",
    )


def window_seconds() -> float:
    """Countdown length; `AUTO_ACTION_SECONDS=20` by default."""
    try:
        return max(1.0, float(os.environ.get("AUTO_ACTION_SECONDS", "20")))
    except ValueError:
        return 20.0


def auto_enabled() -> bool:
    """Kill switch: `AUTO_ACTION_ENABLED=false` makes every window expire."""
    return os.environ.get("AUTO_ACTION_ENABLED", "true").lower() != "false"


def mobile_token() -> str:
    """Shared secret for decide/apply calls; empty means open (dev mode)."""
    return os.environ.get("MOBILE_API_TOKEN", "")


def auto_apply_for(entry: dict, policy_allowed: Optional[bool]) -> bool:
    """True when a due window may apply itself (P6).

    Runs that never passed the gate keep the legacy behaviour (auto-apply).
    Gate-started runs auto-apply only when the gate decision was `act` and
    the profile policy allows auto-fix; otherwise the window needs an
    explicit Approve and expires untouched.
    """
    gate = entry.get("gate")
    if not gate:
        return True
    if policy_allowed is not True:
        return False
    return gate.get("decision") == "act"


def action_summary_for(domain: str, entry: dict) -> Optional[str]:
    """Human summary when a stored run is eligible; None when it isn't."""
    result = entry.get("result")
    if result is None or getattr(result, "status", None) != "PASS":
        return None
    if domain == "software":
        if not getattr(result, "patch_code", None):
            return None
        if entry.get("target") != "inventory":
            return None
        return "Deploy the verified inventory patch to the shop"
    if domain == "appliance":
        runbook = getattr(result, "runbook", None)
        if runbook is None:
            return None
        steps = getattr(runbook, "steps", []) or []
        first = steps[0] if steps else "runbook"
        extra = f" (+{len(steps) - 1} more)" if len(steps) > 1 else ""
        return f"Apply runbook: {first}{extra}"
    return None
