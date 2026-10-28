"""Deterministic runbook safety validator (Day 6, profile-aware in P6).

No physics simulation: hard bounds only. A runbook that violates any bound
fails verification, and the violations feed back to the model exactly like
pytest output. The hard-coded bounds below stay as defaults; a setup
profile only ever adds constraints, never loosens them.
"""

from __future__ import annotations

import re
from typing import Any

from core.schemas.remediation import Runbook

SAFE_TARGET_C = {"fridge": (0.0, 5.0), "freezer": (-25.0, -15.0)}
MIN_COMPRESSOR_RESTART_DELAY_S = 180
MAX_POWER_OFF_MINUTES = {"fridge": 60, "freezer": 120}
_TEMP_METRICS = {"temp_c", "temp", "temperature"}


def _profile_temp_ceiling(forbidden: str) -> float | None:
    """Ceiling from 'never set above 5 C' style policy text, if parseable."""
    match = re.search(r"above\s*(\d+(?:\.\d+)?)", forbidden.lower())
    if match:
        return float(match.group(1))
    return None


def _profile_violations(runbook: Runbook, profile: Any) -> list[str]:
    out = []
    for limit in profile.hard_limits:
        if limit.metric not in _TEMP_METRICS:
            continue
        target = runbook.target_temperature_c
        breached = (
            target > limit.threshold
            if limit.op == ">"
            else target < limit.threshold
        )
        if breached:
            out.append(
                f"Target {target}°C breaches profile hard limit "
                f"{limit.metric} {limit.op} {limit.threshold:g}°C"
            )
    for forbidden in profile.policy.forbidden_actions:
        text = forbidden.lower()
        ceiling = _profile_temp_ceiling(forbidden)
        if (
            ceiling is not None
            and runbook.target_temperature_c > ceiling
        ):
            out.append(
                f"Runbook violates profile policy: {forbidden!r} "
                f"(target {runbook.target_temperature_c}°C)"
            )
        if "disable" in text and runbook.disables_protection:
            out.append(
                f"Runbook violates profile policy: {forbidden!r}"
            )
        if (
            ("power off" in text or "power-off" in text or "poweroff" in text)
            and runbook.power_off_minutes > 0
        ):
            out.append(
                f"Runbook violates profile policy: {forbidden!r}"
            )
    return out


def validate_runbook(
    runbook: Runbook, appliance_type: str, profile: Any = None
) -> list[str]:
    """Return the list of safety violations; empty means the runbook is safe."""
    violations = []
    bounds = SAFE_TARGET_C.get(appliance_type)
    if bounds is None:
        return [f"Unknown appliance type {appliance_type!r}"]
    low, high = bounds
    if not low <= runbook.target_temperature_c <= high:
        violations.append(
            f"Target {runbook.target_temperature_c}°C is outside {low}..{high}°C"
        )
    if runbook.restart_delay_s < MIN_COMPRESSOR_RESTART_DELAY_S:
        violations.append(
            f"Restart delay must be at least {MIN_COMPRESSOR_RESTART_DELAY_S}s"
        )
    if runbook.power_off_minutes > MAX_POWER_OFF_MINUTES[appliance_type]:
        violations.append("Power-off window risks stock spoilage")
    if runbook.disables_protection:
        violations.append("Runbook must not disable voltage or thermal protection")
    if not runbook.steps:
        violations.append("Runbook has no actionable steps")
    if profile is not None:
        violations.extend(_profile_violations(runbook, profile))
    return violations
