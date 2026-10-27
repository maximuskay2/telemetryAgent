"""Deterministic runbook safety validator (Day 6).

No physics simulation: hard bounds only. A runbook that violates any bound
fails verification, and the violations feed back to the model exactly like
pytest output.
"""

from __future__ import annotations

from core.schemas.remediation import Runbook

SAFE_TARGET_C = {"fridge": (0.0, 5.0), "freezer": (-25.0, -15.0)}
MIN_COMPRESSOR_RESTART_DELAY_S = 180
MAX_POWER_OFF_MINUTES = {"fridge": 60, "freezer": 120}


def validate_runbook(runbook: Runbook, appliance_type: str) -> list[str]:
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
    return violations
