"""Org-scoped storage: Postgres when configured, files otherwise (C-J1).

`get_store()` picks the backend: `DATABASE_URL` set → PostgresBackend,
else FileBackend (today's single-tenant behaviour, plus JSON for the new
org entities). The simulation/demo routes always use FileBackend, even when
the database is configured. Bind request scope with `.scoped(org_id,
user_id)`; Postgres applies it as the RLS `app.org_id`/`app.user_id`
settings per transaction (one connection per call, no pool yet).

All methods are sync (async callers use `asyncio.to_thread`) and return
plain JSON-shaped dicts with epoch-float timestamps.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.commerce import db as db_module
from core.commerce import models


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _row_to_dict(cur, row) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for index, col in enumerate(cur.description):
        value = row[index]
        if hasattr(value, "timestamp") and not isinstance(value, (int, float)):
            try:
                value = float(value.timestamp())
            except (OverflowError, OSError, ValueError):
                value = 0.0
        out[col.name] = value
    return out


class CommerceStoreError(RuntimeError):
    """A store call failed (missing row, duplicate, unreachable backend)."""


class BaseStore:
    """Backend contract (both backends implement every method)."""

    # -- scope ---------------------------------------------------------
    def scoped(self, org_id: str = "", user_id: str = "") -> "BaseStore":
        raise NotImplementedError

    # -- orgs / users / memberships ------------------------------------
    def create_org(self, name: str, user_id: str) -> Dict[str, Any]:
        """Create the org with `user_id` as its owner; returns the org row."""
        raise NotImplementedError

    def get_org(self, org_id: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def list_orgs_for_user(self) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def soft_delete_org(self, org_id: str, grace_until: float) -> bool:
        raise NotImplementedError

    def org_data_key(self, org_id: str) -> bytes:
        """Raw 32-byte org data key, creating + storing it wrapped."""
        raise NotImplementedError

    def create_user(
        self, external_id: str, email: str, name: str
    ) -> Dict[str, Any]:
        raise NotImplementedError

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def get_user_by_external(
        self, external_id: str
    ) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def touch_login(self, user_id: str) -> None:
        raise NotImplementedError

    def add_membership(
        self, org_id: str, user_id: str, role: str
    ) -> Dict[str, Any]:
        raise NotImplementedError

    def get_membership(
        self, org_id: str, user_id: str
    ) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def list_members(self, org_id: str) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def set_role(self, org_id: str, user_id: str, role: str) -> bool:
        raise NotImplementedError

    def remove_membership(self, org_id: str, user_id: str) -> bool:
        raise NotImplementedError

    # -- device tokens / pairing / invites ------------------------------
    def create_device_token(
        self, org_id: str, user_id: str, label: str
    ) -> tuple:
        """(row dict, token shown once)."""
        raise NotImplementedError

    def get_device_token_by_hash(
        self, token_hash: str
    ) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def list_device_tokens(self, org_id: str) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def revoke_device_token(self, token_id: str, org_id: str) -> bool:
        raise NotImplementedError

    def touch_device_token(self, token_id: str) -> None:
        raise NotImplementedError

    def create_pairing_code(
        self, org_id: str, user_id: str, label: str, ttl_s: int = 600
    ) -> tuple:
        """(row dict, code shown once, e.g. "123-456")."""
        raise NotImplementedError

    def claim_pairing_code(self, code: str) -> Optional[Dict[str, Any]]:
        """Row when the code is live; marks it used."""
        raise NotImplementedError

    def create_invite(
        self, org_id: str, email: str, role: str, ttl_s: int = 7 * 86400
    ) -> tuple:
        """(row dict, token shown once)."""
        raise NotImplementedError

    def get_invite_by_hash(
        self, token_hash: str
    ) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def mark_invite_accepted(self, token_hash: str) -> bool:
        raise NotImplementedError

    # -- systems / connections -------------------------------------------
    def create_system(
        self, org_id: str, profile: Dict[str, Any]
    ) -> Dict[str, Any]:
        raise NotImplementedError

    def get_system(
        self, org_id: str, system_id: str
    ) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def list_systems(self, org_id: str) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def save_system(
        self, org_id: str, profile: Dict[str, Any]
    ) -> Dict[str, Any]:
        raise NotImplementedError

    def delete_system(self, org_id: str, system_id: str) -> bool:
        raise NotImplementedError

    def create_connection(
        self,
        org_id: str,
        system_id: str,
        kind: str,
        config: Dict[str, Any],
        secret: Optional[str],
    ) -> tuple:
        """(public dict, key-or-None shown once)."""
        raise NotImplementedError

    def get_connection(
        self, org_id: str, connection_id: str
    ) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def list_connections(
        self, org_id: str, system_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def delete_connection(self, org_id: str, connection_id: str) -> bool:
        raise NotImplementedError

    def mark_connection_seen(
        self, org_id: str, connection_id: str,
        status: str = "ok", detail: str = "",
    ) -> None:
        raise NotImplementedError

    def get_connection_secret(
        self, org_id: str, connection_id: str
    ) -> str:
        """Plaintext third-party secret for outbound calls (never via API)."""
        raise NotImplementedError

    def find_record_for_key(
        self, key: str, kind: str
    ) -> Optional[Dict[str, Any]]:
        """Connection record + org_id for an ingest/device `ta_live_` key."""
        raise NotImplementedError

    # -- pause / rate / audit / runs --------------------------------------
    def get_pause(self, org_id: str) -> Dict[str, Any]:
        raise NotImplementedError

    def set_pause(
        self, org_id: str, paused: bool, by_user: str = ""
    ) -> Dict[str, Any]:
        raise NotImplementedError

    def get_rate(self, org_id: str, system_id: str) -> float:
        raise NotImplementedError

    def stamp_rate(self, org_id: str, system_id: str) -> None:
        raise NotImplementedError

    def audit(self, org_id: str, entry: Dict[str, Any]) -> None:
        raise NotImplementedError

    def list_audit(
        self, org_id: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def create_run(self, org_id: str, run: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    def update_run(
        self, org_id: str, run_id: str, fields: Dict[str, Any]
    ) -> bool:
        raise NotImplementedError

    def get_run(
        self, org_id: str, run_id: str
    ) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def find_run_by_fingerprint(
        self, org_id: str, fingerprint: str
    ) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    # -- usage / allowances (Jude's usage.py builds on these) --------------
    def record_usage_event(
        self,
        org_id: str,
        kind: str,
        quantity: float = 1,
        unit: str = "count",
        system_id: Optional[str] = None,
        run_id: Optional[str] = None,
        provider: str = "",
        model: str = "",
        language: Optional[str] = None,
        cost_estimate_usd: float = 0.0,
        consume_fix_run: bool = False,
    ) -> Dict[str, Any]:
        """Insert the event + bump allowance counters, atomically."""
        raise NotImplementedError

    def list_usage(
        self, org_id: str, since: float = 0.0, kind: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def get_allowance(self, org_id: str) -> Dict[str, Any]:
        """Row, creating it from FREE_ALLOWANCE when missing."""
        raise NotImplementedError

    def reset_allowance_counters(
        self, org_id: str, period_month: str
    ) -> Dict[str, Any]:
        raise NotImplementedError


class PostgresBackend(BaseStore):
    """Postgres store; scope binds the per-transaction RLS settings."""

    def __init__(
        self, url: Optional[str] = None,
        org_id: str = "", user_id: str = "", external_id: str = "",
    ) -> None:
        self._url = db_module.database_url(url)
        self._org_id = org_id
        self._user_id = user_id
        self._external_id = external_id

    def scoped(
        self, org_id: str = "", user_id: str = "", external_id: str = ""
    ) -> "PostgresBackend":
        return PostgresBackend(self._url, org_id, user_id, external_id)

    def _txn(self):
        return db_module.transaction(
            self._org_id, self._user_id, self._url, self._external_id
        )

    # -- orgs / users / memberships ------------------------------------
    def create_org(self, name: str, user_id: str) -> Dict[str, Any]:
        org_id = models.new_org_id()
        user_scope = self.scoped("", user_id)
        with user_scope._txn() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO orgs (id, name) VALUES (%s, %s)",
                (org_id, name),
            )
        org_scope = self.scoped(org_id, user_id)
        org_scope.add_membership(org_id, user_id, "owner")
        row = org_scope.get_org(org_id)
        assert row is not None
        return row

    def get_org(self, org_id: str) -> Optional[Dict[str, Any]]:
        with self._txn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, name, created_at, deleted_at FROM orgs "
                "WHERE id = %s",
                (org_id,),
            )
            found = cur.fetchone()
            return _row_to_dict(cur, found) if found else None

    def list_orgs_for_user(self) -> List[Dict[str, Any]]:
        with self._txn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT o.id, o.name, o.created_at, o.deleted_at, "
                "m.role FROM orgs o "
                "JOIN memberships m ON m.org_id = o.id "
                "WHERE m.user_id = %s AND o.deleted_at IS NULL "
                "ORDER BY o.created_at",
                (self._user_id,),
            )
            return [_row_to_dict(cur, row) for row in cur.fetchall()]

    def soft_delete_org(self, org_id: str, grace_until: float) -> bool:
        import datetime

        when = datetime.datetime.fromtimestamp(
            grace_until, tz=datetime.timezone.utc
        )
        with self._txn() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE orgs SET deleted_at = %s WHERE id = %s",
                (when, org_id),
            )
            return cur.rowcount > 0

    def org_data_key(self, org_id: str) -> bytes:
        from core.commerce import crypto as crypto_module

        with self._txn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT data_key_enc FROM orgs WHERE id = %s", (org_id,)
            )
            found = cur.fetchone()
            if found is None:
                raise CommerceStoreError(f"unknown org {org_id}")
            blob = found[0] or ""
            if blob:
                return crypto_module.unwrap_data_key(blob)
            raw = crypto_module.new_data_key()
            cur.execute(
                "UPDATE orgs SET data_key_enc = %s WHERE id = %s",
                (crypto_module.wrap_data_key(raw), org_id),
            )
            return raw

    def create_user(
        self, external_id: str, email: str, name: str
    ) -> Dict[str, Any]:
        user_id = models.new_user_id()
        scoped = self.scoped(self._org_id, user_id)
        with scoped._txn() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (id, external_id, email, name) "
                "VALUES (%s, %s, %s, %s)",
                (user_id, external_id, email, name),
            )
        row = scoped.get_user(user_id)
        assert row is not None
        return row

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        with self._txn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, external_id, email, name, created_at, "
                "last_login FROM users WHERE id = %s",
                (user_id,),
            )
            found = cur.fetchone()
            return _row_to_dict(cur, found) if found else None

    def get_user_by_external(
        self, external_id: str
    ) -> Optional[Dict[str, Any]]:
        # The app sets app.external_id from the verified JWT sub, which is
        # what the users SELECT policy matches at login time.
        scoped = self.scoped(self._org_id, self._user_id, external_id)
        with scoped._txn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, external_id, email, name, created_at, "
                "last_login FROM users WHERE external_id = %s",
                (external_id,),
            )
            found = cur.fetchone()
            return _row_to_dict(cur, found) if found else None

    def touch_login(self, user_id: str) -> None:
        with self._txn() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET last_login = now() WHERE id = %s",
                (user_id,),
            )

    def add_membership(
        self, org_id: str, user_id: str, role: str
    ) -> Dict[str, Any]:
        with self._txn() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO memberships (org_id, user_id, role) "
                "VALUES (%s, %s, %s) "
                "ON CONFLICT (org_id, user_id) DO UPDATE SET role = %s",
                (org_id, user_id, role, role),
            )
        row = self.get_membership(org_id, user_id)
        assert row is not None
        return row

    def get_membership(
        self, org_id: str, user_id: str
    ) -> Optional[Dict[str, Any]]:
        with self._txn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT org_id, user_id, role, created_at FROM memberships "
                "WHERE org_id = %s AND user_id = %s",
                (org_id, user_id),
            )
            found = cur.fetchone()
            return _row_to_dict(cur, found) if found else None

    def list_members(self, org_id: str) -> List[Dict[str, Any]]:
        with self._txn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT m.user_id, u.email, u.name, m.role, m.created_at "
                "FROM memberships m JOIN users u ON u.id = m.user_id "
                "WHERE m.org_id = %s ORDER BY m.created_at",
                (org_id,),
            )
            return [_row_to_dict(cur, row) for row in cur.fetchall()]

    def set_role(self, org_id: str, user_id: str, role: str) -> bool:
        with self._txn() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE memberships SET role = %s "
                "WHERE org_id = %s AND user_id = %s",
                (role, org_id, user_id),
            )
            return cur.rowcount > 0

    def remove_membership(self, org_id: str, user_id: str) -> bool:
        with self._txn() as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM memberships WHERE org_id = %s AND user_id = %s",
                (org_id, user_id),
            )
            return cur.rowcount > 0

    # -- device tokens / pairing / invites ------------------------------
    def create_device_token(
        self, org_id: str, user_id: str, label: str
    ) -> tuple:
        from core.connections import store as connection_store

        token = f"{models.DEVICE_KEY_PREFIX}{secrets.token_urlsafe(24)}"
        token_id = models.new_device_id()
        with self._txn() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO device_tokens "
                "(id, org_id, user_id, token_hash, label) "
                "VALUES (%s, %s, %s, %s, %s)",
                (
                    token_id, org_id, user_id,
                    connection_store.hash_key(token), label,
                ),
            )
        rows = self.list_device_tokens(org_id)
        row = next(item for item in rows if item["id"] == token_id)
        return row, token

    def get_device_token_by_hash(
        self, token_hash: str
    ) -> Optional[Dict[str, Any]]:
        with self._txn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM resolve_device_token(%s)", (token_hash,)
            )
            found = cur.fetchone()
            return _row_to_dict(cur, found) if found else None

    def list_device_tokens(self, org_id: str) -> List[Dict[str, Any]]:
        with self._txn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, org_id, user_id, label, created_at, "
                "last_used_at, revoked_at FROM device_tokens "
                "WHERE org_id = %s ORDER BY created_at",
                (org_id,),
            )
            return [_row_to_dict(cur, row) for row in cur.fetchall()]

    def revoke_device_token(self, token_id: str, org_id: str) -> bool:
        with self._txn() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE device_tokens SET revoked_at = now() "
                "WHERE id = %s AND org_id = %s",
                (token_id, org_id),
            )
            return cur.rowcount > 0

    def touch_device_token(self, token_id: str) -> None:
        with self._txn() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE device_tokens SET last_used_at = now() "
                "WHERE id = %s",
                (token_id,),
            )

    def create_pairing_code(
        self, org_id: str, user_id: str, label: str, ttl_s: int = 600
    ) -> tuple:
        import datetime

        code = f"{secrets.randbelow(1000):03d}-{secrets.randbelow(1000):03d}"
        expires = datetime.datetime.now(
            tz=datetime.timezone.utc
        ) + datetime.timedelta(seconds=ttl_s)
        with self._txn() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO pairing_codes "
                "(code_hash, org_id, user_id, label, expires_at) "
                "VALUES (%s, %s, %s, %s, %s)",
                (_sha256(code), org_id, user_id, label, expires),
            )
        return {"org_id": org_id, "label": label}, code

    def claim_pairing_code(self, code: str) -> Optional[Dict[str, Any]]:
        with self._txn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM claim_pairing_code_fn(%s)", (_sha256(code),)
            )
            found = cur.fetchone()
            return _row_to_dict(cur, found) if found else None

    def create_invite(
        self, org_id: str, email: str, role: str, ttl_s: int = 7 * 86400
    ) -> tuple:
        import datetime

        token = secrets.token_urlsafe(24)
        expires = datetime.datetime.now(
            tz=datetime.timezone.utc
        ) + datetime.timedelta(seconds=ttl_s)
        with self._txn() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO invites "
                "(token_hash, org_id, email, role, expires_at) "
                "VALUES (%s, %s, %s, %s, %s)",
                (_sha256(token), org_id, email, role, expires),
            )
        return {"org_id": org_id, "email": email, "role": role}, token

    def get_invite_by_hash(
        self, token_hash: str
    ) -> Optional[Dict[str, Any]]:
        with self._txn() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM resolve_invite(%s)", (token_hash,))
            found = cur.fetchone()
            return _row_to_dict(cur, found) if found else None

    def mark_invite_accepted(self, token_hash: str) -> bool:
        with self._txn() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE invites SET accepted_at = now() "
                "WHERE token_hash = %s AND accepted_at IS NULL",
                (token_hash,),
            )
            return cur.rowcount > 0

    # -- systems / connections -------------------------------------------
    def create_system(
        self, org_id: str, profile: Dict[str, Any]
    ) -> Dict[str, Any]:
        import json as json_module

        system_id = str(profile.get("system_id", ""))
        status = str(profile.get("status", "draft"))
        with self._txn() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO systems (id, org_id, profile, status, version) "
                "VALUES (%s, %s, %s::jsonb, %s, 1)",
                (system_id, org_id, json_module.dumps(profile), status),
            )
            cur.execute(
                "INSERT INTO systems_versions (system_id, version, profile) "
                "VALUES (%s, 1, %s::jsonb)",
                (system_id, json_module.dumps(profile)),
            )
        row = self.get_system(org_id, system_id)
        assert row is not None
        return row

    def get_system(
        self, org_id: str, system_id: str
    ) -> Optional[Dict[str, Any]]:
        with self._txn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, org_id, profile, status, version, created_at, "
                "updated_at FROM systems "
                "WHERE id = %s AND org_id = %s AND deleted_at IS NULL",
                (system_id, org_id),
            )
            found = cur.fetchone()
            return _row_to_dict(cur, found) if found else None

    def list_systems(self, org_id: str) -> List[Dict[str, Any]]:
        with self._txn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, org_id, profile, status, version, created_at, "
                "updated_at FROM systems "
                "WHERE org_id = %s AND deleted_at IS NULL ORDER BY id",
                (org_id,),
            )
            return [_row_to_dict(cur, row) for row in cur.fetchall()]

    def save_system(
        self, org_id: str, profile: Dict[str, Any]
    ) -> Dict[str, Any]:
        import json as json_module

        system_id = str(profile.get("system_id", ""))
        status = str(profile.get("status", "draft"))
        with self._txn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT version FROM systems "
                "WHERE id = %s AND org_id = %s",
                (system_id, org_id),
            )
            found = cur.fetchone()
            version = int(found[0]) + 1 if found else 1
            cur.execute(
                "INSERT INTO systems (id, org_id, profile, status, version,"
                " updated_at) VALUES (%s, %s, %s::jsonb, %s, %s, now()) "
                "ON CONFLICT (id) DO UPDATE SET profile = %s::jsonb, "
                "status = %s, version = %s, updated_at = now()",
                (
                    system_id, org_id, json_module.dumps(profile),
                    status, version, json_module.dumps(profile),
                    status, version,
                ),
            )
            cur.execute(
                "INSERT INTO systems_versions (system_id, version, profile) "
                "VALUES (%s, %s, %s::jsonb) "
                "ON CONFLICT (system_id, version) DO NOTHING",
                (system_id, version, json_module.dumps(profile)),
            )
        row = self.get_system(org_id, system_id)
        assert row is not None
        return row

    def delete_system(self, org_id: str, system_id: str) -> bool:
        with self._txn() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE systems SET deleted_at = now() "
                "WHERE id = %s AND org_id = %s",
                (system_id, org_id),
            )
            return cur.rowcount > 0

    def create_connection(
        self,
        org_id: str,
        system_id: str,
        kind: str,
        config: Dict[str, Any],
        secret: Optional[str],
    ) -> tuple:
        import json as json_module

        from core.commerce import crypto as crypto_module
        from core.connections import store as connection_store

        connection_id = connection_store.new_connection_id()
        key_hash = ""
        secret_enc = ""
        hint = ""
        shown_once: Optional[str] = None
        if kind in connection_store.GENERATED_KEY_KINDS:
            shown_once = connection_store.new_live_key()
            key_hash = connection_store.hash_key(shown_once)
            hint = connection_store.secret_hint(shown_once)
        elif secret:
            data_key = self.org_data_key(org_id)
            secret_enc = crypto_module.seal(data_key, secret)
            hint = connection_store.secret_hint(secret)
        with self._txn() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO connections (id, org_id, system_id, kind,"
                " config, secret_enc, secret_hint, key_hash) "
                "VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s)",
                (
                    connection_id, org_id, system_id, kind,
                    json_module.dumps(config), secret_enc, hint, key_hash,
                ),
            )
        row = self.get_connection(org_id, connection_id)
        assert row is not None
        return row, shown_once

    def get_connection(
        self, org_id: str, connection_id: str
    ) -> Optional[Dict[str, Any]]:
        with self._txn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, org_id, system_id, kind, config, secret_hint,"
                " key_hash, status, detail, last_seen, created_at "
                "FROM connections WHERE id = %s AND org_id = %s",
                (connection_id, org_id),
            )
            found = cur.fetchone()
            return _row_to_dict(cur, found) if found else None

    def list_connections(
        self, org_id: str, system_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        with self._txn() as conn, conn.cursor() as cur:
            if system_id is None:
                cur.execute(
                    "SELECT id, org_id, system_id, kind, config, secret_hint,"
                    " key_hash, status, detail, last_seen, created_at "
                    "FROM connections WHERE org_id = %s ORDER BY id",
                    (org_id,),
                )
            else:
                cur.execute(
                    "SELECT id, org_id, system_id, kind, config, secret_hint,"
                    " key_hash, status, detail, last_seen, created_at "
                    "FROM connections "
                    "WHERE org_id = %s AND system_id = %s ORDER BY id",
                    (org_id, system_id),
                )
            return [_row_to_dict(cur, row) for row in cur.fetchall()]

    def delete_connection(self, org_id: str, connection_id: str) -> bool:
        with self._txn() as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM connections WHERE id = %s AND org_id = %s",
                (connection_id, org_id),
            )
            return cur.rowcount > 0

    def mark_connection_seen(
        self, org_id: str, connection_id: str,
        status: str = "ok", detail: str = "",
    ) -> None:
        with self._txn() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE connections SET last_seen = now(), status = %s,"
                " detail = %s WHERE id = %s AND org_id = %s",
                (status, detail, connection_id, org_id),
            )

    def get_connection_secret(
        self, org_id: str, connection_id: str
    ) -> str:
        from core.commerce import crypto as crypto_module

        with self._txn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT secret_enc FROM connections "
                "WHERE id = %s AND org_id = %s",
                (connection_id, org_id),
            )
            found = cur.fetchone()
            if found is None or not found[0]:
                return ""
            data_key = self.org_data_key(org_id)
            return crypto_module.open_seal(data_key, found[0])

    def find_record_for_key(
        self, key: str, kind: str
    ) -> Optional[Dict[str, Any]]:
        from core.connections import store as connection_store

        digest = connection_store.hash_key(key)
        with self._txn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM resolve_connection_key(%s, %s)",
                (digest, kind),
            )
            found = cur.fetchone()
            return _row_to_dict(cur, found) if found else None

    # -- pause / rate / audit / runs --------------------------------------
    def get_pause(self, org_id: str) -> Dict[str, Any]:
        with self._txn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT org_id, paused, at, by_user FROM pause_state "
                "WHERE org_id = %s",
                (org_id,),
            )
            found = cur.fetchone()
            if found:
                return _row_to_dict(cur, found)
            return {"org_id": org_id, "paused": False, "at": 0.0, "by_user": ""}

    def set_pause(
        self, org_id: str, paused: bool, by_user: str = ""
    ) -> Dict[str, Any]:
        with self._txn() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO pause_state (org_id, paused, at, by_user) "
                "VALUES (%s, %s, now(), %s) "
                "ON CONFLICT (org_id) DO UPDATE SET paused = %s, "
                "at = now(), by_user = %s",
                (org_id, paused, by_user, paused, by_user),
            )
        return self.get_pause(org_id)

    def get_rate(self, org_id: str, system_id: str) -> float:
        with self._txn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT at FROM rate_stamps WHERE org_id = %s AND system_id = %s",
                (org_id, system_id),
            )
            found = cur.fetchone()
            if not found or found[0] is None:
                return 0.0
            try:
                return float(found[0].timestamp())
            except (OverflowError, OSError, ValueError):
                return 0.0

    def stamp_rate(self, org_id: str, system_id: str) -> None:
        with self._txn() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO rate_stamps (org_id, system_id, at) "
                "VALUES (%s, %s, now()) "
                "ON CONFLICT (org_id, system_id) DO UPDATE SET at = now()",
                (org_id, system_id),
            )

    def audit(self, org_id: str, entry: Dict[str, Any]) -> None:
        import json as json_module

        actor = str(entry.get("actor", ""))
        action = str(entry.get("action", ""))
        detail = {
            key: value
            for key, value in entry.items()
            if key not in ("actor", "action")
        }
        with self._txn() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO audit (org_id, actor, action, detail) "
                "VALUES (%s, %s, %s, %s::jsonb)",
                (org_id, actor, action, json_module.dumps(detail)),
            )

    def list_audit(
        self, org_id: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        with self._txn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, org_id, actor, action, detail, at FROM audit "
                "WHERE org_id = %s ORDER BY id DESC LIMIT %s",
                (org_id, limit),
            )
            return [_row_to_dict(cur, row) for row in cur.fetchall()]

    def create_run(self, org_id: str, run: Dict[str, Any]) -> Dict[str, Any]:
        import json as json_module

        run_id = str(run.get("id", "")) or f"run_{secrets.token_hex(6)}"
        with self._txn() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO runs (id, org_id, system_id, domain, kind,"
                " status, language, fingerprint, pr_url, result) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)",
                (
                    run_id, org_id, run.get("system_id"),
                    str(run.get("domain", "")), str(run.get("kind", "")),
                    str(run.get("status", "")), run.get("language"),
                    str(run.get("fingerprint", "")),
                    str(run.get("pr_url", "")),
                    json_module.dumps(run.get("result", {})),
                ),
            )
        row = self.get_run(org_id, run_id)
        assert row is not None
        return row

    def update_run(
        self, org_id: str, run_id: str, fields: Dict[str, Any]
    ) -> bool:
        import json as json_module

        allowed = {
            "status", "language", "pr_url", "result", "cost_estimate_usd",
            "finished", "system_id", "domain", "kind", "fingerprint",
        }
        sets = []
        params: list = []
        for key, value in fields.items():
            if key not in allowed:
                continue
            if key == "finished" and value:
                sets.append("finished_at = now()")
                continue
            if key == "result":
                sets.append("result = %s::jsonb")
                params.append(json_module.dumps(value))
                continue
            sets.append(f"{key} = %s")
            params.append(value)
        if not sets:
            return False
        params.extend([run_id, org_id])
        with self._txn() as conn, conn.cursor() as cur:
            cur.execute(
                f"UPDATE runs SET {', '.join(sets)} "  # noqa: S608
                "WHERE id = %s AND org_id = %s",
                params,
            )
            return cur.rowcount > 0

    def get_run(
        self, org_id: str, run_id: str
    ) -> Optional[Dict[str, Any]]:
        with self._txn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, org_id, system_id, domain, kind, status,"
                " language, fingerprint, pr_url, result, cost_estimate_usd,"
                " started_at, finished_at FROM runs "
                "WHERE id = %s AND org_id = %s",
                (run_id, org_id),
            )
            found = cur.fetchone()
            return _row_to_dict(cur, found) if found else None

    def find_run_by_fingerprint(
        self, org_id: str, fingerprint: str
    ) -> Optional[Dict[str, Any]]:
        with self._txn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, org_id, system_id, domain, kind, status,"
                " language, fingerprint, pr_url, result, cost_estimate_usd,"
                " started_at, finished_at FROM runs "
                "WHERE org_id = %s AND fingerprint = %s "
                "ORDER BY started_at DESC LIMIT 1",
                (org_id, fingerprint),
            )
            found = cur.fetchone()
            return _row_to_dict(cur, found) if found else None

    # -- usage / allowances ------------------------------------------------
    def record_usage_event(
        self,
        org_id: str,
        kind: str,
        quantity: float = 1,
        unit: str = "count",
        system_id: Optional[str] = None,
        run_id: Optional[str] = None,
        provider: str = "",
        model: str = "",
        language: Optional[str] = None,
        cost_estimate_usd: float = 0.0,
        consume_fix_run: bool = False,
    ) -> Dict[str, Any]:
        with self._txn() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO usage_events (org_id, system_id, run_id, kind,"
                " quantity, unit, provider, model, language,"
                " cost_estimate_usd) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "RETURNING id",
                (
                    org_id, system_id, run_id, kind, quantity, unit,
                    provider, model, language, cost_estimate_usd,
                ),
            )
            event_id = cur.fetchone()[0]
            self._ensure_allowance_row(cur, org_id)
            if consume_fix_run:
                cur.execute(
                    "UPDATE allowances SET fix_runs_used = fix_runs_used + 1,"
                    " cost_used_usd = cost_used_usd + %s, updated_at = now() "
                    "WHERE org_id = %s",
                    (cost_estimate_usd, org_id),
                )
            elif cost_estimate_usd:
                cur.execute(
                    "UPDATE allowances SET cost_used_usd = cost_used_usd + %s,"
                    " updated_at = now() WHERE org_id = %s",
                    (cost_estimate_usd, org_id),
                )
        return {"id": event_id, "org_id": org_id, "kind": kind}

    def _ensure_allowance_row(self, cur, org_id: str) -> None:
        import datetime

        period = datetime.datetime.now(tz=datetime.timezone.utc).strftime(
            "%Y-%m"
        )
        cur.execute(
            "INSERT INTO allowances (org_id, systems_limit, devices_limit,"
            " fix_runs_limit, cost_ceiling_usd, period_month) "
            "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (org_id) DO NOTHING",
            (
                org_id,
                models.FREE_ALLOWANCE["systems_limit"],
                models.FREE_ALLOWANCE["devices_limit"],
                models.FREE_ALLOWANCE["fix_runs_limit"],
                models.FREE_ALLOWANCE["cost_ceiling_usd"],
                period,
            ),
        )

    def list_usage(
        self, org_id: str, since: float = 0.0, kind: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        import datetime

        moment = datetime.datetime.fromtimestamp(
            since, tz=datetime.timezone.utc
        )
        with self._txn() as conn, conn.cursor() as cur:
            if kind is None:
                cur.execute(
                    "SELECT id, org_id, system_id, run_id, kind, quantity,"
                    " unit, provider, model, language, cost_estimate_usd, at "
                    "FROM usage_events WHERE org_id = %s AND at >= %s "
                    "ORDER BY id",
                    (org_id, moment),
                )
            else:
                cur.execute(
                    "SELECT id, org_id, system_id, run_id, kind, quantity,"
                    " unit, provider, model, language, cost_estimate_usd, at "
                    "FROM usage_events "
                    "WHERE org_id = %s AND at >= %s AND kind = %s ORDER BY id",
                    (org_id, moment, kind),
                )
            return [_row_to_dict(cur, row) for row in cur.fetchall()]

    def get_allowance(self, org_id: str) -> Dict[str, Any]:
        with self._txn() as conn, conn.cursor() as cur:
            self._ensure_allowance_row(cur, org_id)
            cur.execute(
                "SELECT org_id, systems_limit, devices_limit, fix_runs_limit,"
                " cost_ceiling_usd, fix_runs_used, cost_used_usd,"
                " period_month, updated_at FROM allowances WHERE org_id = %s",
                (org_id,),
            )
            found = cur.fetchone()
            assert found is not None
            return _row_to_dict(cur, found)

    def reset_allowance_counters(
        self, org_id: str, period_month: str
    ) -> Dict[str, Any]:
        with self._txn() as conn, conn.cursor() as cur:
            self._ensure_allowance_row(cur, org_id)
            cur.execute(
                "UPDATE allowances SET fix_runs_used = 0, cost_used_usd = 0,"
                " period_month = %s, updated_at = now() WHERE org_id = %s",
                (period_month, org_id),
            )
        return self.get_allowance(org_id)


class FileBackend(BaseStore):
    """File store: existing systems/connections stores + JSON org entities.

    Single-tenant: `org_id` arguments are accepted for interface parity but
    everything lives in one `TA_DATA_DIR`. Used when `DATABASE_URL` is unset
    (self-hosted) and always for the simulation/demo routes.
    """

    def __init__(
        self, root: Optional[Path] = None,
        org_id: str = "", user_id: str = "",
    ) -> None:
        from core.setup.store import data_root

        self._root = root if root is not None else data_root() / "commerce"
        self._org_id = org_id
        self._user_id = user_id

    def scoped(self, org_id: str = "", user_id: str = "") -> "FileBackend":
        return FileBackend(self._root, org_id, user_id)

    # -- JSON helpers ----------------------------------------------------
    def _path(self, name: str) -> Path:
        return self._root / f"{name}.json"

    def _load(self, name: str, default):
        path = self._path(name)
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return default

    def _save(self, name: str, payload, private: bool = False) -> None:
        path = self._path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        if private:
            fd = os.open(
                str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle, indent=2)
            except BaseException:
                try:
                    os.close(fd)
                except OSError:
                    pass
                raise
            os.chmod(path, 0o600)
        else:
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # -- orgs / users / memberships ---------------------------------------
    def create_org(self, name: str, user_id: str) -> Dict[str, Any]:
        orgs = self._load("orgs", {})
        org_id = models.new_org_id()
        orgs[org_id] = {
            "id": org_id,
            "name": name,
            "data_key_enc": "",
            "created_at": time.time(),
            "deleted_at": None,
        }
        self._save("orgs", orgs, private=True)
        self.add_membership(org_id, user_id, "owner")
        row = self.get_org(org_id)
        assert row is not None
        return row

    def get_org(self, org_id: str) -> Optional[Dict[str, Any]]:
        orgs = self._load("orgs", {})
        row = orgs.get(org_id)
        if row is None:
            return None
        return {
            key: row.get(key)
            for key in ("id", "name", "created_at", "deleted_at")
        }

    def list_orgs_for_user(self) -> List[Dict[str, Any]]:
        memberships = self._load("memberships", [])
        mine = [
            item for item in memberships
            if item.get("user_id") == self._user_id
        ]
        out = []
        for item in mine:
            row = self.get_org(str(item.get("org_id", "")))
            if row is not None and not row.get("deleted_at"):
                out.append({**row, "role": item.get("role", "")})
        return sorted(out, key=lambda row: row.get("created_at", 0.0))

    def soft_delete_org(self, org_id: str, grace_until: float) -> bool:
        orgs = self._load("orgs", {})
        if org_id not in orgs:
            return False
        orgs[org_id]["deleted_at"] = grace_until
        self._save("orgs", orgs, private=True)
        return True

    def org_data_key(self, org_id: str) -> bytes:
        from core.commerce import crypto as crypto_module

        orgs = self._load("orgs", {})
        if org_id not in orgs:
            raise CommerceStoreError(f"unknown org {org_id}")
        blob = orgs[org_id].get("data_key_enc", "")
        if blob:
            return crypto_module.unwrap_data_key(blob)
        raw = crypto_module.new_data_key()
        orgs[org_id]["data_key_enc"] = crypto_module.wrap_data_key(raw)
        self._save("orgs", orgs, private=True)
        return raw

    def create_user(
        self, external_id: str, email: str, name: str
    ) -> Dict[str, Any]:
        users = self._load("users", {})
        user_id = models.new_user_id()
        users[user_id] = {
            "id": user_id,
            "external_id": external_id,
            "email": email,
            "name": name,
            "created_at": time.time(),
            "last_login": None,
        }
        self._save("users", users)
        row = self.get_user(user_id)
        assert row is not None
        return row

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        users = self._load("users", {})
        row = users.get(user_id)
        return dict(row) if row is not None else None

    def get_user_by_external(
        self, external_id: str
    ) -> Optional[Dict[str, Any]]:
        users = self._load("users", {})
        for row in users.values():
            if row.get("external_id") == external_id:
                return dict(row)
        return None

    def touch_login(self, user_id: str) -> None:
        users = self._load("users", {})
        if user_id in users:
            users[user_id]["last_login"] = time.time()
            self._save("users", users)

    def add_membership(
        self, org_id: str, user_id: str, role: str
    ) -> Dict[str, Any]:
        memberships = self._load("memberships", [])
        memberships = [
            item for item in memberships
            if not (
                item.get("org_id") == org_id
                and item.get("user_id") == user_id
            )
        ]
        row = {
            "org_id": org_id,
            "user_id": user_id,
            "role": role,
            "created_at": time.time(),
        }
        memberships.append(row)
        self._save("memberships", memberships)
        return dict(row)

    def get_membership(
        self, org_id: str, user_id: str
    ) -> Optional[Dict[str, Any]]:
        memberships = self._load("memberships", [])
        for row in memberships:
            if (
                row.get("org_id") == org_id
                and row.get("user_id") == user_id
            ):
                return dict(row)
        return None

    def list_members(self, org_id: str) -> List[Dict[str, Any]]:
        memberships = self._load("memberships", [])
        out = []
        for item in memberships:
            if item.get("org_id") != org_id:
                continue
            user = self.get_user(str(item.get("user_id", ""))) or {}
            out.append(
                {
                    "user_id": item.get("user_id", ""),
                    "email": user.get("email", ""),
                    "name": user.get("name", ""),
                    "role": item.get("role", ""),
                    "created_at": item.get("created_at", 0.0),
                }
            )
        return sorted(out, key=lambda row: row.get("created_at", 0.0))

    def set_role(self, org_id: str, user_id: str, role: str) -> bool:
        memberships = self._load("memberships", [])
        changed = False
        for row in memberships:
            if (
                row.get("org_id") == org_id
                and row.get("user_id") == user_id
            ):
                row["role"] = role
                changed = True
        if changed:
            self._save("memberships", memberships)
        return changed

    def remove_membership(self, org_id: str, user_id: str) -> bool:
        memberships = self._load("memberships", [])
        kept = [
            item for item in memberships
            if not (
                item.get("org_id") == org_id
                and item.get("user_id") == user_id
            )
        ]
        if len(kept) == len(memberships):
            return False
        self._save("memberships", kept)
        return True

    # -- device tokens / pairing / invites --------------------------------
    def create_device_token(
        self, org_id: str, user_id: str, label: str
    ) -> tuple:
        from core.connections import store as connection_store

        tokens = self._load("device_tokens", {})
        token = f"{models.DEVICE_KEY_PREFIX}{secrets.token_urlsafe(24)}"
        token_id = models.new_device_id()
        tokens[token_id] = {
            "id": token_id,
            "org_id": org_id,
            "user_id": user_id,
            "token_hash": connection_store.hash_key(token),
            "label": label,
            "created_at": time.time(),
            "last_used_at": None,
            "revoked_at": None,
        }
        self._save("device_tokens", tokens, private=True)
        rows = self.list_device_tokens(org_id)
        row = next(item for item in rows if item["id"] == token_id)
        return row, token

    def get_device_token_by_hash(
        self, token_hash: str
    ) -> Optional[Dict[str, Any]]:
        tokens = self._load("device_tokens", {})
        for row in tokens.values():
            if row.get("token_hash") == token_hash:
                return {
                    key: row.get(key)
                    for key in (
                        "id", "org_id", "user_id", "label", "created_at",
                        "last_used_at", "revoked_at",
                    )
                }
        return None

    def list_device_tokens(self, org_id: str) -> List[Dict[str, Any]]:
        tokens = self._load("device_tokens", {})
        out = [
            {
                key: row.get(key)
                for key in (
                    "id", "org_id", "user_id", "label", "created_at",
                    "last_used_at", "revoked_at",
                )
            }
            for row in tokens.values()
            if row.get("org_id") == org_id
        ]
        return sorted(out, key=lambda row: row.get("created_at", 0.0))

    def revoke_device_token(self, token_id: str, org_id: str) -> bool:
        tokens = self._load("device_tokens", {})
        row = tokens.get(token_id)
        if row is None or row.get("org_id") != org_id:
            return False
        row["revoked_at"] = time.time()
        self._save("device_tokens", tokens, private=True)
        return True

    def touch_device_token(self, token_id: str) -> None:
        tokens = self._load("device_tokens", {})
        if token_id in tokens:
            tokens[token_id]["last_used_at"] = time.time()
            self._save("device_tokens", tokens, private=True)

    def create_pairing_code(
        self, org_id: str, user_id: str, label: str, ttl_s: int = 600
    ) -> tuple:
        codes = self._load("pairing_codes", {})
        code = f"{secrets.randbelow(1000):03d}-{secrets.randbelow(1000):03d}"
        codes[_sha256(code)] = {
            "org_id": org_id,
            "user_id": user_id,
            "label": label,
            "expires_at": time.time() + ttl_s,
            "used_at": None,
        }
        self._save("pairing_codes", codes)
        return {"org_id": org_id, "label": label}, code

    def claim_pairing_code(self, code: str) -> Optional[Dict[str, Any]]:
        codes = self._load("pairing_codes", {})
        row = codes.get(_sha256(code))
        if row is None or row.get("used_at") is not None:
            return None
        if float(row.get("expires_at", 0.0)) <= time.time():
            return None
        row["used_at"] = time.time()
        self._save("pairing_codes", codes)
        return {
            key: row.get(key) for key in ("org_id", "user_id", "label")
        }

    def create_invite(
        self, org_id: str, email: str, role: str, ttl_s: int = 7 * 86400
    ) -> tuple:
        invites = self._load("invites", {})
        token = secrets.token_urlsafe(24)
        invites[_sha256(token)] = {
            "org_id": org_id,
            "email": email,
            "role": role,
            "created_at": time.time(),
            "expires_at": time.time() + ttl_s,
            "accepted_at": None,
        }
        self._save("invites", invites)
        return {"org_id": org_id, "email": email, "role": role}, token

    def get_invite_by_hash(
        self, token_hash: str
    ) -> Optional[Dict[str, Any]]:
        invites = self._load("invites", {})
        row = invites.get(token_hash)
        return dict(row) if row is not None else None

    def mark_invite_accepted(self, token_hash: str) -> bool:
        invites = self._load("invites", {})
        row = invites.get(token_hash)
        if row is None or row.get("accepted_at") is not None:
            return False
        row["accepted_at"] = time.time()
        self._save("invites", invites)
        return True

    # -- systems / connections (delegate to the existing stores) -----------
    def create_system(
        self, org_id: str, profile: Dict[str, Any]
    ) -> Dict[str, Any]:
        from core.schemas.profile import SystemProfile
        from core.setup import store as setup_store

        _ = org_id
        stored = setup_store.save_profile(
            SystemProfile.model_validate(profile)
        )
        return self._profile_row(stored)

    def get_system(
        self, org_id: str, system_id: str
    ) -> Optional[Dict[str, Any]]:
        from core.setup import store as setup_store

        _ = org_id
        profile = setup_store.get_profile(system_id)
        return self._profile_row(profile) if profile else None

    def list_systems(self, org_id: str) -> List[Dict[str, Any]]:
        from core.setup import store as setup_store

        _ = org_id
        return [
            self._profile_row(profile)
            for profile in setup_store.list_profiles()
        ]

    def save_system(
        self, org_id: str, profile: Dict[str, Any]
    ) -> Dict[str, Any]:
        return self.create_system(org_id, profile)

    def delete_system(self, org_id: str, system_id: str) -> bool:
        from core.setup import store as setup_store

        _ = org_id
        try:
            setup_store.profile_path(system_id).unlink()
        except FileNotFoundError:
            return False
        return True

    @staticmethod
    def _profile_row(profile) -> Dict[str, Any]:
        dumped = profile.model_dump(mode="json")
        return {
            "id": dumped.get("system_id", ""),
            "org_id": models.SELF_ORG_ID,
            "profile": dumped,
            "status": dumped.get("status", "draft"),
            "version": dumped.get("version", 1),
            "created_at": 0.0,
            "updated_at": 0.0,
        }

    def create_connection(
        self,
        org_id: str,
        system_id: str,
        kind: str,
        config: Dict[str, Any],
        secret: Optional[str],
    ) -> tuple:
        from core.connections import store as connection_store

        _ = org_id
        connection, shown = connection_store.create_connection(
            system_id, kind, config, secret
        )
        return self._connection_row(connection), shown

    def get_connection(
        self, org_id: str, connection_id: str
    ) -> Optional[Dict[str, Any]]:
        from core.connections import store as connection_store

        _ = org_id
        connection = connection_store.get_connection(connection_id)
        return self._connection_row(connection) if connection else None

    def list_connections(
        self, org_id: str, system_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        from core.connections import store as connection_store

        _ = org_id
        return [
            self._connection_row(connection)
            for connection in connection_store.list_connections(system_id)
        ]

    def delete_connection(self, org_id: str, connection_id: str) -> bool:
        from core.connections import store as connection_store

        _ = org_id
        return connection_store.delete_connection(connection_id)

    def mark_connection_seen(
        self, org_id: str, connection_id: str,
        status: str = "ok", detail: str = "",
    ) -> None:
        from core.connections import store as connection_store

        _ = org_id
        connection_store.mark_seen(connection_id, status, detail)

    def get_connection_secret(
        self, org_id: str, connection_id: str
    ) -> str:
        from core.connections import store as connection_store

        _ = org_id
        return connection_store.get_secret(connection_id)

    def find_record_for_key(
        self, key: str, kind: str
    ) -> Optional[Dict[str, Any]]:
        from core.connections import store as connection_store

        record = connection_store.find_record_for_key(key, kind)
        if record is None:
            return None
        return {"org_id": models.SELF_ORG_ID, **record}

    @staticmethod
    def _connection_row(connection) -> Dict[str, Any]:
        dumped = connection.model_dump(mode="json")
        dumped["org_id"] = models.SELF_ORG_ID
        return dumped

    # -- pause / rate / audit / runs --------------------------------------
    def get_pause(self, org_id: str) -> Dict[str, Any]:
        _ = org_id
        state = self._load("pause", {})
        return {
            "org_id": models.SELF_ORG_ID,
            "paused": bool(state.get("paused", False)),
            "at": float(state.get("at", 0.0)),
            "by_user": str(state.get("by_user", "")),
        }

    def set_pause(
        self, org_id: str, paused: bool, by_user: str = ""
    ) -> Dict[str, Any]:
        _ = org_id
        self._save(
            "pause",
            {"paused": paused, "at": time.time(), "by_user": by_user},
        )
        return self.get_pause(models.SELF_ORG_ID)

    def get_rate(self, org_id: str, system_id: str) -> float:
        _ = org_id
        stamps = self._load("rate_stamps", {})
        try:
            return float(stamps.get(system_id, 0.0))
        except (TypeError, ValueError):
            return 0.0

    def stamp_rate(self, org_id: str, system_id: str) -> None:
        _ = org_id
        stamps = self._load("rate_stamps", {})
        stamps[system_id] = time.time()
        self._save("rate_stamps", stamps)

    def audit(self, org_id: str, entry: Dict[str, Any]) -> None:
        _ = org_id
        items = self._load("audit", [])
        items.append({"ts": time.time(), **entry})
        self._save("audit", items[-500:])

    def list_audit(
        self, org_id: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        _ = org_id
        items = self._load("audit", [])
        return list(reversed(items[-limit:]))

    def create_run(self, org_id: str, run: Dict[str, Any]) -> Dict[str, Any]:
        runs = self._load("runs", {})
        run_id = str(run.get("id", "")) or f"run_{secrets.token_hex(6)}"
        row = {
            "id": run_id,
            "org_id": org_id,
            "system_id": run.get("system_id"),
            "domain": str(run.get("domain", "")),
            "kind": str(run.get("kind", "")),
            "status": str(run.get("status", "")),
            "language": run.get("language"),
            "fingerprint": str(run.get("fingerprint", "")),
            "pr_url": str(run.get("pr_url", "")),
            "result": run.get("result", {}),
            "cost_estimate_usd": 0.0,
            "started_at": time.time(),
            "finished_at": None,
        }
        runs[run_id] = row
        self._save("runs", runs)
        return dict(row)

    def update_run(
        self, org_id: str, run_id: str, fields: Dict[str, Any]
    ) -> bool:
        runs = self._load("runs", {})
        row = runs.get(run_id)
        if row is None or row.get("org_id") != org_id:
            return False
        for key, value in fields.items():
            if key == "finished" and value:
                row["finished_at"] = time.time()
            elif key in row:
                row[key] = value
        self._save("runs", runs)
        return True

    def get_run(
        self, org_id: str, run_id: str
    ) -> Optional[Dict[str, Any]]:
        runs = self._load("runs", {})
        row = runs.get(run_id)
        if row is None or row.get("org_id") != org_id:
            return None
        return dict(row)

    def find_run_by_fingerprint(
        self, org_id: str, fingerprint: str
    ) -> Optional[Dict[str, Any]]:
        runs = self._load("runs", {})
        matches = [
            row for row in runs.values()
            if row.get("org_id") == org_id
            and row.get("fingerprint") == fingerprint
        ]
        if not matches:
            return None
        matches.sort(key=lambda row: row.get("started_at", 0.0))
        return dict(matches[-1])

    # -- usage / allowances ------------------------------------------------
    def record_usage_event(
        self,
        org_id: str,
        kind: str,
        quantity: float = 1,
        unit: str = "count",
        system_id: Optional[str] = None,
        run_id: Optional[str] = None,
        provider: str = "",
        model: str = "",
        language: Optional[str] = None,
        cost_estimate_usd: float = 0.0,
        consume_fix_run: bool = False,
    ) -> Dict[str, Any]:
        events = self._load("usage_events", [])
        event = {
            "id": len(events) + 1,
            "org_id": org_id,
            "system_id": system_id,
            "run_id": run_id,
            "kind": kind,
            "quantity": quantity,
            "unit": unit,
            "provider": provider,
            "model": model,
            "language": language,
            "cost_estimate_usd": cost_estimate_usd,
            "at": time.time(),
        }
        events.append(event)
        self._save("usage_events", events)
        allowance = self.get_allowance(org_id)
        if consume_fix_run:
            allowance["fix_runs_used"] += 1
        allowance["cost_used_usd"] += cost_estimate_usd
        self._save_allowance(org_id, allowance)
        return {"id": event["id"], "org_id": org_id, "kind": kind}

    def list_usage(
        self, org_id: str, since: float = 0.0, kind: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        events = self._load("usage_events", [])
        return [
            dict(event) for event in events
            if event.get("org_id") == org_id
            and float(event.get("at", 0.0)) >= since
            and (kind is None or event.get("kind") == kind)
        ]

    def get_allowance(self, org_id: str) -> Dict[str, Any]:
        allowances = self._load("allowances", {})
        row = allowances.get(org_id)
        if row is None:
            import datetime

            row = {
                "org_id": org_id,
                **dict(models.FREE_ALLOWANCE),
                "fix_runs_used": 0,
                "cost_used_usd": 0.0,
                "period_month": datetime.datetime.now(
                    tz=datetime.timezone.utc
                ).strftime("%Y-%m"),
                "updated_at": time.time(),
            }
            allowances[org_id] = row
            self._save("allowances", allowances)
        return dict(row)

    def reset_allowance_counters(
        self, org_id: str, period_month: str
    ) -> Dict[str, Any]:
        allowance = self.get_allowance(org_id)
        allowance["fix_runs_used"] = 0
        allowance["cost_used_usd"] = 0.0
        allowance["period_month"] = period_month
        self._save_allowance(org_id, allowance)
        return dict(allowance)

    def _save_allowance(self, org_id: str, row: Dict[str, Any]) -> None:
        allowances = self._load("allowances", {})
        row["updated_at"] = time.time()
        allowances[org_id] = row
        self._save("allowances", allowances)


def get_store(url: Optional[str] = None) -> BaseStore:
    """Backend for this process: Postgres when configured, else files."""
    if db_module.using_postgres(url):
        return PostgresBackend(url)
    return FileBackend()
