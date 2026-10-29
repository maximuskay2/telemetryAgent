"""Production connections: which systems are real customers (§3.3).

Demo systems keep the exact current path. Production systems — those whose
profile carries `environment["mode"] == "production"`, set only by
`/connect` — go through the repo-fix pipeline and the options/commands
routes. This helper is used only inside the new routes, so demo code never
sees it.
"""

from __future__ import annotations

from typing import Any


def is_production(profile: Any) -> bool:
    """True only for `/connect`-created production systems."""
    environment = getattr(profile, "environment", None) or {}
    return environment.get("mode") == "production"
