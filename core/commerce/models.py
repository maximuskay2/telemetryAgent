"""Shared commerce constants + id helpers (C-J1)."""

from __future__ import annotations

from uuid import uuid4

#: Implicit org for self-hosted installs (no DATABASE_URL).
SELF_ORG_ID = "self"

#: Channel for in-memory sim runs + file-store demo systems (public reads).
DEMO_ORG_ID = "demo"

#: Org id for the one-off JSON import (scripts/commerce-migrate.py, C-J3).
LEGACY_ORG_ID = "legacy"

#: Roles, weakest last (commercial-roadmap §8.3 matrix).
ROLES = ("owner", "admin", "member", "viewer")

#: Free fair-use allowance defaults (roadmap §3.2 config shape).
FREE_ALLOWANCE = {
    "systems_limit": 3,
    "devices_limit": 5,
    "fix_runs_limit": 30,
    "cost_ceiling_usd": 25.0,
}

DEVICE_KEY_PREFIX = "ta_dev_"


def new_org_id() -> str:
    return f"org_{uuid4().hex[:12]}"


def new_user_id() -> str:
    return f"usr_{uuid4().hex[:12]}"


def new_device_id() -> str:
    return f"dev_{uuid4().hex[:12]}"
