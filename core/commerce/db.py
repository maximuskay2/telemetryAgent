"""Postgres plumbing for the commercial backend (C-J1).

Sync `psycopg` connections; async callers wrap these in `asyncio.to_thread`,
matching the rest of the codebase. One connection per call (no pool yet —
a pool is a later optimization, not a C-J1 need).

Every transaction sets `app.org_id` (+ `app.user_id` when a user acts) via
`SET LOCAL` so the §8.3 RLS policies apply. With no setting the policies
match nothing: fail closed.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path
from typing import Iterator, Optional

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def database_url(url: Optional[str] = None) -> str:
    """Postgres URL, or "" when the file store runs the show."""
    if url is not None:
        return url.strip()
    return os.environ.get("DATABASE_URL", "").strip()


def using_postgres(url: Optional[str] = None) -> bool:
    return bool(database_url(url))


def connect(url: Optional[str] = None):
    """Open a connection (caller owns commit/rollback/close)."""
    import psycopg

    dsn = database_url(url)
    if not dsn:
        raise CommerceDBError("DATABASE_URL is not set")
    try:
        return psycopg.connect(dsn)
    except Exception as exc:
        raise CommerceDBError(f"cannot reach Postgres: {exc}") from exc


class CommerceDBError(RuntimeError):
    """Postgres unreachable, or the schema failed to apply."""


@contextlib.contextmanager
def transaction(
    org_id: str = "",
    user_id: str = "",
    url: Optional[str] = None,
    external_id: str = "",
) -> Iterator:
    """Yield a connection with the RLS settings applied; commit on exit."""
    conn = connect(url)
    try:
        with conn.cursor() as cur:
            # SET takes no bind params; set_config(..., true) is SET LOCAL.
            cur.execute(
                "SELECT set_config('app.org_id', %s, true)", (org_id,)
            )
            cur.execute(
                "SELECT set_config('app.user_id', %s, true)", (user_id,)
            )
            cur.execute(
                "SELECT set_config('app.external_id', %s, true)",
                (external_id,),
            )
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def ensure_schema(url: Optional[str] = None) -> None:
    """Apply schema.sql idempotently (boot + tests + migration script).

    The file's sha256 is tracked in schemaversions: a matching hash is a
    no-op, so the least-privilege app role (no DDL rights) boots fine. A
    fresh or changed schema needs DDL rights — the bootstrap superuser in
    tests and deploys; the error says so.
    """
    import hashlib

    dsn = database_url(url)
    if not dsn:
        return
    script = SCHEMA_PATH.read_text(encoding="utf-8")
    digest = hashlib.sha256(script.encode("utf-8")).hexdigest()
    try:
        conn = connect(dsn)
    except CommerceDBError as exc:
        raise CommerceDBError(
            f"ensure_schema: {exc} "
            "(local dev: docker run -d --name ta-postgres "
            "-e POSTGRES_PASSWORD=postgres -p 5432:5432 postgres:16)"
        ) from exc
    try:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM schemaversions WHERE hash = %s", (digest,)
                )
                if cur.fetchone() is not None:
                    conn.commit()
                    return
                conn.rollback()
        except Exception:
            # Fresh database (no schemaversions yet): fall through and apply.
            conn.rollback()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(script)
                    cur.execute(
                        "INSERT INTO schemaversions (hash) VALUES (%s) "
                        "ON CONFLICT DO NOTHING",
                        (digest,),
                    )
        except Exception as exc:
            name = type(exc).__name__
            if "Privilege" in name or "permission denied" in str(exc):
                raise CommerceDBError(
                    "commerce schema is missing or stale and this role"
                    " cannot apply it; run ensure_schema once as the"
                    " bootstrap superuser"
                ) from exc
            raise
    finally:
        conn.close()


def ensure_app_role(
    role: str, password: str, url: Optional[str] = None
) -> None:
    """Create the least-privilege app role and grant it the schema.

    Superusers bypass RLS, so the API must never connect as the bootstrap
    superuser: production uses `ta_app`, local dev uses `ta_app` on its own
    database, tests use `ta_test` (see tests/commerce_db.py). Re-run after
    schema changes (grants cover existing tables + sequences).
    """
    import psycopg
    from psycopg import sql

    if not role.replace("_", "").isalnum() or not role[0].isalpha():
        raise CommerceDBError(f"refusing odd role name {role!r}")
    dsn = database_url(url)
    if not dsn:
        raise CommerceDBError("DATABASE_URL is not set")
    conn = psycopg.connect(dsn)
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)
            )
            if cur.fetchone() is None:
                cur.execute(
                    sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                        sql.Identifier(role), password
                    )
                )
            else:
                cur.execute(
                    sql.SQL("ALTER ROLE {} LOGIN PASSWORD {}").format(
                        sql.Identifier(role), password
                    )
                )
            cur.execute(
                sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                    sql.Identifier(conn.info.dbname), sql.Identifier(role)
                )
            )
            cur.execute("GRANT USAGE ON SCHEMA public TO {}".format(role))
            cur.execute(
                "GRANT ALL ON ALL TABLES IN SCHEMA public TO {}".format(role)
            )
            cur.execute(
                "GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO {}".format(
                    role
                )
            )
    finally:
        conn.close()
