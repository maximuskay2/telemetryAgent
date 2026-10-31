"""Org lifecycle: export/restore/purge + retention sweep (C-J5).

Postgres via the tests/commerce_db.py fixture (ta_test role); skips
when unreachable. A bootstrap (superuser) connection verifies row
absence after purge — reads only, never app logic.
"""

from __future__ import annotations

import os
import time
import unittest
from unittest import mock

from tests.commerce_auth import mint, test_env
from tests.commerce_db import bootstrap_url, db_available, fixture


def _headers(sub: str, email: str, org_id: str = "") -> dict:
    headers = {"Authorization": f"Bearer {mint(sub, email)}"}
    if org_id:
        headers["X-Org-Id"] = org_id
    return headers


def _pg_count(url: str, table: str, org_id: str) -> int:
    from core.commerce import db as db_module

    conn = db_module.connect(url)
    try:
        with conn.cursor() as cur:
            if table == "systems_versions":
                cur.execute(
                    "SELECT COUNT(*) FROM systems_versions WHERE system_id"
                    " IN (SELECT id FROM systems WHERE org_id = %s)",
                    (org_id,),
                )
            elif table == "orgs":
                cur.execute(
                    "SELECT COUNT(*) FROM orgs WHERE id = %s", (org_id,)
                )
            else:
                cur.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE org_id = %s",
                    (org_id,),
                )
            found = cur.fetchone()
            return int(found[0]) if found else 0
    finally:
        conn.close()


class LifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        if not db_available():
            self.skipTest("no postgres (TEST_DATABASE_URL)")
        self._fix = fixture()
        url = self._fix.__enter__()
        self.addCleanup(self._fix.__exit__, None, None, None)
        patcher = mock.patch.dict(
            os.environ, {"DATABASE_URL": url, **test_env()}
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        from fastapi.testclient import TestClient

        from apps.api.main import app

        self.client = TestClient(app)
        self._client_ctx = self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.org = self.client.post(
            "/api/orgs", json={"name": "Lifecycle Co"},
            headers=_headers("u-life", "owner@x.co"),
        ).json()["org"]["id"]
        self.hdrs = _headers("u-life", "owner@x.co", self.org)
        self.system_id = self.client.post(
            "/api/systems",
            json={"name": "Keep", "kind": "software"},
            headers=self.hdrs,
        ).json()["system_id"]
        created = self.client.post(
            "/api/connections",
            json={"system_id": self.system_id, "kind": "device",
                  "config": {}},
            headers=self.hdrs,
        ).json()
        self.conn_id = created["connection"]["id"]
        self.device_key = created["key"]

    def test_export_purge_restore_round_trip(self) -> None:
        from core.commerce import repo as repo_module

        boot = bootstrap_url()
        # Second member via invite so the round-trip covers members.
        invite = self.client.post(
            f"/api/orgs/{self.org}/invites",
            json={"email": "member@x.co", "role": "member"},
            headers=self.hdrs,
        ).json()["invite"]
        joined = self.client.post(
            f"/api/invites/{invite['token']}/accept",
            headers=_headers("u-life-2", "member@x.co"),
        )
        self.assertEqual(joined.status_code, 200, joined.text)

        blob = self.client.get(
            f"/api/orgs/{self.org}/export", headers=self.hdrs
        )
        self.assertEqual(blob.status_code, 200, blob.text)
        blob = blob.json()
        self.assertEqual(blob["export_version"], 1)
        self.assertEqual(len(blob["members"]), 2)
        self.assertEqual(
            [s["id"] for s in blob["systems"]], [self.system_id]
        )
        self.assertEqual(
            [c["id"] for c in blob["connections"]], [self.conn_id]
        )
        # Hashes travel (keys keep working); token hashes don't.
        self.assertTrue(blob["connections"][0]["key_hash"])
        self.assertNotIn(
            "token_hash", json_keys(blob["device_tokens"])
        )

        # Purge refuses inside the grace window ...
        self.assertEqual(
            self.client.post(
                f"/api/orgs/{self.org}/purge", headers=self.hdrs
            ).status_code, 409,
        )
        deleted = self.client.delete(
            f"/api/orgs/{self.org}", headers=self.hdrs
        )
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(
            self.client.post(
                f"/api/orgs/{self.org}/purge", headers=self.hdrs
            ).status_code, 409,
        )
        # ... and wipes every org-owned row once grace elapses.
        store = repo_module.PostgresBackend(
            os.environ["DATABASE_URL"]
        ).scoped(self.org, "u-life")
        store.soft_delete_org(self.org, time.time() - 1)
        purged = self.client.post(
            f"/api/orgs/{self.org}/purge", headers=self.hdrs
        )
        self.assertEqual(purged.status_code, 200, purged.text)
        for table in (
            "orgs", "memberships", "systems", "systems_versions",
            "connections", "device_tokens", "pairing_codes",
            "invites", "audit", "runs", "rate_stamps", "pause_state",
            "usage_events", "allowances",
        ):
            self.assertEqual(
                _pg_count(boot, table, self.org), 0, table
            )

        # Restore rebuilds from the blob; keys keep working.
        back = self.client.post(
            "/api/orgs/restore", json=blob,
            headers=_headers("u-life", "owner@x.co"),
        )
        self.assertEqual(back.status_code, 200, back.text)
        body = back.json()
        self.assertEqual(body["org_id"], self.org)
        self.assertEqual(body["restored"]["systems"], 1)
        self.assertEqual(body["restored"]["connections"], 1)
        self.assertEqual(body["skipped_users"], [])
        kept = self.client.get(
            "/api/connections", headers=self.hdrs
        ).json()["connections"]
        self.assertEqual([c["id"] for c in kept], [self.conn_id])
        record = repo_module.PostgresBackend(
            os.environ["DATABASE_URL"]
        ).find_record_for_key(self.device_key, "device")
        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record["org_id"], self.org)
        members = self.client.get(
            f"/api/orgs/{self.org}/members", headers=self.hdrs
        ).json()["members"]
        self.assertEqual(
            sorted(m["role"] for m in members), ["member", "owner"]
        )
        # Restoring twice collides on the org id.
        again = self.client.post(
            "/api/orgs/restore", json=blob,
            headers=_headers("u-life", "owner@x.co"),
        )
        self.assertEqual(again.status_code, 409)

    def test_lifecycle_needs_owner(self) -> None:
        other = self.client.post(
            "/api/orgs", json={"name": "Other"},
            headers=_headers("u-stranger", "s@x.co"),
        ).json()["org"]["id"]
        foreign = _headers("u-stranger", "s@x.co", other)
        self.assertEqual(
            self.client.get(
                f"/api/orgs/{self.org}/export", headers=foreign
            ).status_code, 403,
        )
        self.assertEqual(
            self.client.post(
                f"/api/orgs/{self.org}/purge", headers=foreign
            ).status_code, 403,
        )

    def test_restore_rejects_garbage(self) -> None:
        bad = self.client.post(
            "/api/orgs/restore", json={"nope": True},
            headers=_headers("u-life", "owner@x.co"),
        )
        self.assertEqual(bad.status_code, 400)


def json_keys(rows) -> set:
    out: set = set()
    for row in rows or []:
        out.update(row.keys())
    return out


class SweepTests(unittest.TestCase):
    def setUp(self) -> None:
        if not db_available():
            self.skipTest("no postgres (TEST_DATABASE_URL)")

    def test_audit_sweep_keeps_recent(self) -> None:
        from core.commerce import db as db_module
        from core.commerce import repo as repo_module

        with fixture() as url:
            store = repo_module.PostgresBackend(url)
            user = store.create_user("test|sweep", "s@x.co", "S")
            org = store.create_org("Sweep Co", user["id"])["id"]
            scoped = store.scoped(org, user["id"])
            for index in range(3):
                scoped.audit(org, {"actor": "t", "action": f"a{index}"})
            conn = db_module.connect(bootstrap_url())
            try:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "UPDATE audit SET at = now() - INTERVAL"
                            " '100 days' WHERE org_id = %s AND action = 'a0'",
                            (org,),
                        )
            finally:
                conn.close()
            removed = repo_module.PostgresBackend(url).sweep_audit(90)
            self.assertEqual(removed, 1)
            self.assertEqual(len(scoped.list_audit(org, 100)), 2)
            # The 7-day floor holds even when asked for 1.
            removed = repo_module.PostgresBackend(url).sweep_audit(1)
            self.assertEqual(removed, 0)
            self.assertEqual(len(scoped.list_audit(org, 100)), 2)

    def test_version_sweep_keeps_latest(self) -> None:
        from core.commerce import repo as repo_module

        with fixture() as url:
            store = repo_module.PostgresBackend(url)
            user = store.create_user("test|sweep2", "s@x.co", "S")
            org = store.create_org("Sweep Co", user["id"])["id"]
            scoped = store.scoped(org, user["id"])
            for index in range(8):
                scoped.save_system(
                    org,
                    {"system_id": "sys-v", "status": "draft",
                     "name": f"v{index}"},
                )
            removed = repo_module.PostgresBackend(url).sweep_versions(5)
            self.assertEqual(removed, 3)
            current = scoped.get_system(org, "sys-v")
            assert current is not None
            self.assertEqual(current["profile"]["name"], "v7")
            # Floor: keep=1 still keeps 5.
            removed = repo_module.PostgresBackend(url).sweep_versions(1)
            self.assertEqual(removed, 0)


if __name__ == "__main__":
    unittest.main()
