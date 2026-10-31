"""One-off JSON → `legacy` org import (C-J3, §8.3 migration).

Reads today's file store (`TA_DATA_DIR`: profiles, connections, pause +
mitigation state) and copies it into Postgres under the fixed `legacy`
org id. Demo systems (`environment.demo == "true"`) stay in the file
store — the simulation route never touches the database. Re-runs are
idempotent: systems upsert, connections skip existing ids, memberships
upsert, and the audit log imports once (guarded by its import marker).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from core.commerce import models as models_module


def _load_json(path: Path, default: Any) -> Any:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default
    return loaded


def ensure_legacy_org(store, owner_external_id: str, email: str = "",
                      name: str = "") -> Dict[str, Any]:
    """Claim the `legacy` org for the owner (idempotent)."""
    user = store.get_user_by_external(owner_external_id)
    if user is None:
        user = store.create_user(owner_external_id, email, name)
    org_store = store.scoped(models_module.LEGACY_ORG_ID, user["id"])
    org = org_store.get_org(models_module.LEGACY_ORG_ID)
    if org is None:
        org_store.create_org(
            "Legacy import", user["id"], models_module.LEGACY_ORG_ID
        )
        org = org_store.get_org(models_module.LEGACY_ORG_ID)
        assert org is not None
    org_store.add_membership(org["id"], user["id"], "owner")
    return {"org": org, "user": user}


def migrate_profiles(store, data_dir: Path) -> Dict[str, int]:
    """Copy non-demo profiles → systems. Returns {imported, skipped}."""
    scoped = store.scoped(models_module.LEGACY_ORG_ID)
    imported = 0
    skipped = 0
    root = data_dir / "profiles"
    if not root.is_dir():
        return {"imported": 0, "skipped": 0}
    for path in sorted(root.glob("*.json")):
        profile = _load_json(path, None)
        if not isinstance(profile, dict):
            skipped += 1
            continue
        environment = profile.get("environment") or {}
        if environment.get("demo") == "true":
            skipped += 1
            continue
        profile.setdefault("system_id", path.stem)
        scoped.save_system(models_module.LEGACY_ORG_ID, profile)
        imported += 1
    return {"imported": imported, "skipped": skipped}


def migrate_connections(store, data_dir: Path) -> Dict[str, int]:
    """Copy connection records (key hashes preserved)."""
    scoped = store.scoped(models_module.LEGACY_ORG_ID)
    imported = 0
    skipped = 0
    root = data_dir / "connections"
    if not root.is_dir():
        return {"imported": 0, "skipped": 0}
    for path in sorted(root.glob("*.json")):
        record = _load_json(path, None)
        if not isinstance(record, dict) or not record.get("id"):
            skipped += 1
            continue
        row = scoped.import_connection(models_module.LEGACY_ORG_ID, record)
        if row is None:
            skipped += 1
        else:
            imported += 1
    return {"imported": imported, "skipped": skipped}


def migrate_controls(store, data_dir: Path) -> Dict[str, Any]:
    """Copy pause + rate stamps + audit log. Returns counts + paused."""
    scoped = store.scoped(models_module.LEGACY_ORG_ID)
    pause = _load_json(data_dir / "pause.json", {})
    paused = bool(pause.get("paused", False))
    scoped.set_pause(models_module.LEGACY_ORG_ID, paused)
    state = _load_json(data_dir / "mitigations.json", {})
    last = state.get("last") or {}
    stamped = 0
    for system_id, _at in last.items():
        # Continuity stamps "now" (conservative: briefly rate-limited
        # after cutover rather than replaying stale timestamps).
        scoped.stamp_rate(models_module.LEGACY_ORG_ID, str(system_id))
        stamped += 1
    log = [i for i in (state.get("log") or []) if isinstance(i, dict)]
    audited = 0
    audit_skipped = 0
    already = [
        row for row in scoped.list_audit(models_module.LEGACY_ORG_ID, 1000)
        if row.get("actor") == "legacy-import"
    ]
    if already:
        audit_skipped = len(log)
    else:
        for item in log:
            scoped.audit(
                models_module.LEGACY_ORG_ID,
                {
                    "actor": "legacy-import",
                    "action": str(item.get("action", "")),
                    "imported": item,
                },
            )
            audited += 1
    return {
        "paused": paused,
        "rate_stamps": stamped,
        "audit": audited,
        "audit_skipped": audit_skipped,
    }


def migrate(data_dir: Optional[Path] = None,
            owner_external_id: str = "", email: str = "",
            name: str = "", url: str = "") -> Dict[str, Any]:
    """Run the full import; returns per-stage counts.

    Requires Postgres (`DATABASE_URL` or `url`): the file store is the
    migration SOURCE, never its target.
    """
    from core.commerce import db as db_module
    from core.commerce import repo as repo_module

    target = url or db_module.database_url()
    if not target:
        raise RuntimeError(
            "migration needs Postgres: set DATABASE_URL (nothing to"
            " import into otherwise)"
        )
    if not owner_external_id:
        raise RuntimeError("migration needs --owner (Clerk user id)")
    root = data_dir or Path(
        os.environ.get("TA_DATA_DIR", "").strip()
        or Path(__file__).resolve().parent.parent.parent / "data"
    )
    db_module.ensure_schema(target)
    store = repo_module.PostgresBackend(target)
    claimed = ensure_legacy_org(store, owner_external_id, email, name)
    profiles = migrate_profiles(store, root)
    connections = migrate_connections(store, root)
    controls = migrate_controls(store, root)
    return {
        "org_id": claimed["org"]["id"],
        "owner_id": claimed["user"]["id"],
        "profiles": profiles,
        "connections": connections,
        "controls": controls,
    }
