"""Connection records for the production route (J-R0).

One JSON file per connection at `data/connections/<id>.json`, always mode
`0o600`. `ta_live_*` keys we generate (logs/sentry/device kinds) are stored
only as SHA-256 hashes and shown once, on create. Third-party secrets the
customer pastes (github/railway tokens, webhook signing secret) must stay
recoverable for outbound calls, so they rest in the 600 file and are never
returned by the API — only `secret_hint` (`****` + last 4) leaves the box.

`TA_DATA_DIR` overrides the root, like the profile store.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path
from typing import Optional
from uuid import uuid4

from core.schemas.production import Connection
from core.setup.store import data_root

#: Kinds that get a generated `ta_live_` key (vs a customer-pasted secret).
GENERATED_KEY_KINDS = ("logs", "sentry", "device")

KEY_PREFIX = "ta_live_"


def connections_dir() -> Path:
    return data_root() / "connections"


def connection_path(connection_id: str) -> Path:
    return connections_dir() / f"{connection_id}.json"


def _write_private(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
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


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def key_matches(key: str, digest: str) -> bool:
    return hmac.compare_digest(hash_key(key), digest)


def new_connection_id() -> str:
    return f"con_{uuid4().hex[:12]}"


def new_live_key() -> str:
    return f"{KEY_PREFIX}{secrets.token_urlsafe(24)}"


def secret_hint(secret: str) -> str:
    tail = secret.strip()[-4:] if secret.strip() else ""
    return f"****{tail}" if tail else ""


def _record_to_connection(record: dict) -> Connection:
    return Connection(
        id=record["id"],
        system_id=record["system_id"],
        kind=record["kind"],
        config=dict(record.get("config", {})),
        secret_hint=record.get("secret_hint", ""),
        status=record.get("status", "waiting"),
        detail=record.get("detail", ""),
        last_seen=float(record.get("last_seen", 0.0)),
    )


def create_connection(
    system_id: str, kind: str, config: dict, secret: Optional[str]
) -> tuple[Connection, Optional[str]]:
    """Persist a connection; returns (public connection, key-or-None).

    The key is returned ONLY here — callers show it once and drop it.
    """
    connection_id = new_connection_id()
    record = {
        "id": connection_id,
        "system_id": system_id,
        "kind": kind,
        "config": dict(config),
        "secret_hint": "",
        "status": "waiting",
        "detail": "",
        "last_seen": 0.0,
        "created_at": time.time(),
        "key_hash": "",
        "secret": "",
    }
    shown_once: Optional[str] = None
    if kind in GENERATED_KEY_KINDS:
        shown_once = new_live_key()
        record["key_hash"] = hash_key(shown_once)
        record["secret_hint"] = secret_hint(shown_once)
    elif secret:
        record["secret"] = secret
        record["secret_hint"] = secret_hint(secret)
    _write_private(connection_path(connection_id), record)
    return _record_to_connection(record), shown_once


def get_record(connection_id: str) -> Optional[dict]:
    path = connection_path(connection_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def get_connection(connection_id: str) -> Optional[Connection]:
    record = get_record(connection_id)
    if record is None:
        return None
    return _record_to_connection(record)


def list_connections(system_id: Optional[str] = None) -> list[Connection]:
    root = connections_dir()
    if not root.exists():
        return []
    found = []
    for path in sorted(root.glob("con_*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if system_id is not None and record.get("system_id") != system_id:
            continue
        try:
            found.append(_record_to_connection(record))
        except ValueError:
            continue
    return found


def delete_connection(connection_id: str) -> bool:
    """Delete; the key fails immediately (nothing is cached)."""
    path = connection_path(connection_id)
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    return True


def find_system_for_key(key: str, kind: str) -> Optional[str]:
    """System id whose stored hash matches `key` for `kind`, else None."""
    if not key:
        return None
    root = connections_dir()
    if not root.exists():
        return None
    for path in sorted(root.glob("con_*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if record.get("kind") != kind or not record.get("key_hash"):
            continue
        if key_matches(key, record["key_hash"]):
            return str(record.get("system_id"))
    return None


def find_record_for_key(key: str, kind: str) -> Optional[dict]:
    """Full record for `key` (for last-seen updates), else None."""
    if not key:
        return None
    root = connections_dir()
    if not root.exists():
        return None
    for path in sorted(root.glob("con_*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if record.get("kind") != kind or not record.get("key_hash"):
            continue
        if key_matches(key, record["key_hash"]):
            return record
    return None


def mark_seen(connection_id: str, status: str = "ok", detail: str = "") -> None:
    """Stamp last_seen (+status) when a connection delivers (J-R1)."""
    record = get_record(connection_id)
    if record is None:
        return
    record["last_seen"] = time.time()
    record["status"] = status
    record["detail"] = detail
    _write_private(connection_path(connection_id), record)


def get_secret(connection_id: str) -> str:
    """Recoverable third-party secret for outbound calls (never via API)."""
    record = get_record(connection_id)
    if record is None:
        return ""
    return str(record.get("secret", ""))
