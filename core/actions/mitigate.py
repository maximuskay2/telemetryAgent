"""Safe production mitigations (H0 stub; real logic lands in J-R4).

Allowlist: `rollback` and `restart` ONLY — never stop, scale to zero,
delete, or power off. John's options router calls `software_options()` and
`execute()`; the device command queue refuses new commands while
`is_paused()`.
"""

from __future__ import annotations

from typing import Any


def software_options(run: dict) -> list:
    """Open_pr / rollback / restart options for a software run (H0: none)."""
    _ = run
    return []


def execute(system_id: str, action: str, run_id: str) -> dict:
    """Run one allowlisted mitigation (H0 stub: refuses everything)."""
    return {
        "status": "refused",
        "system_id": system_id,
        "action": action,
        "run_id": run_id,
        "reason": "mitigations land in J-R4",
    }


def is_paused() -> bool:
    """Global pause switch (H0 stub: never paused)."""
    return False
