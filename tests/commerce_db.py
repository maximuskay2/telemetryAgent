"""Postgres fixture for commerce tests (C-J1, shared with Jude's C-D*).

`TEST_DATABASE_URL` points at the bootstrap superuser database (default
`postgresql://postgres:postgres@localhost:5432/telemetry_test`). `fixture()`
ensures the schema + the `ta_test` app role once per process, then wipes all
commerce tables before each use and yields a URL for the `ta_test` role — so
tests exercise the real RLS policies, never a superuser bypass.

DB tests skip when Postgres is unreachable (same rule as Docker-dependent
tests). Local dev: `docker run -d --name ta-postgres
-e POSTGRES_PASSWORD=postgres -p 5432:5432 postgres:16`, then
`CREATE DATABASE telemetry_test;`.

Jude: `from tests.commerce_db import fixture` + `repo.PostgresBackend(url)`.
"""

from __future__ import annotations

import contextlib
import os
from typing import Iterator
from urllib.parse import urlparse, urlunparse

TEST_ROLE = "ta_test"
TEST_PASSWORD = "ta_test_pw"

TABLES_IN_ORDER = (
    "usage_events",
    "audit",
    "runs",
    "rate_stamps",
    "pause_state",
    "allowances",
    "connections",
    "systems_versions",
    "systems",
    "device_tokens",
    "pairing_codes",
    "invites",
    "memberships",
    "users",
    "orgs",
)


def bootstrap_url() -> str:
    return os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/telemetry_test",
    )


def app_url() -> str:
    """Same database, least-privilege test role (RLS enforced)."""
    parts = urlparse(bootstrap_url())
    netloc = f"{TEST_ROLE}:{TEST_PASSWORD}@{parts.hostname or 'localhost'}"
    if parts.port:
        netloc += f":{parts.port}"
    return urlunparse(
        (parts.scheme, netloc, parts.path, "", "", "")
    )


def db_available() -> bool:
    try:
        from core.commerce import db as db_module

        conn = db_module.connect(bootstrap_url())
    except Exception:
        return False
    try:
        conn.close()
    except Exception:
        pass
    return True


@contextlib.contextmanager
def fixture() -> Iterator[str]:
    """Yield the ta_test URL for a wiped commerce schema."""
    from core.commerce import db as db_module

    url = bootstrap_url()
    db_module.ensure_schema(url)
    db_module.ensure_app_role(TEST_ROLE, TEST_PASSWORD, url)
    conn = db_module.connect(url)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "TRUNCATE {} RESTART IDENTITY CASCADE".format(
                        ", ".join(TABLES_IN_ORDER)
                    )
                )
    finally:
        conn.close()
    yield app_url()
