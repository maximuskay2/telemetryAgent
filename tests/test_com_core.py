"""Commerce core: schema, stores, crypto, boot select (C-J1).

Postgres tests use the tests/commerce_db.py fixture (ta_test role, so RLS
is really enforced) and skip when Postgres is unreachable. FileBackend
tests run everywhere under a tmp TA_DATA_DIR.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

from tests.commerce_db import app_url, bootstrap_url, db_available, fixture


def _master_env():
    from cryptography.fernet import Fernet

    return {"COMMERCE_MASTER_KEY": Fernet.generate_key().decode("ascii")}


class StoreSelectTests(unittest.TestCase):
    def test_file_store_without_database_url(self) -> None:
        from core.commerce import repo as repo_module

        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DATABASE_URL", None)
            store = repo_module.get_store()
        self.assertIsInstance(store, repo_module.FileBackend)

    def test_postgres_store_with_database_url(self) -> None:
        from core.commerce import repo as repo_module

        with mock.patch.dict(
            os.environ, {"DATABASE_URL": "postgresql://x/y"}
        ):
            store = repo_module.get_store()
        self.assertIsInstance(store, repo_module.PostgresBackend)


class SchemaTests(unittest.TestCase):
    def test_ensure_schema_is_idempotent(self) -> None:
        if not db_available():
            self.skipTest("no postgres (TEST_DATABASE_URL)")
        from core.commerce import db as db_module

        db_module.ensure_schema(bootstrap_url())
        db_module.ensure_schema(bootstrap_url())
        conn = db_module.connect(bootstrap_url())
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema = 'public' "
                    "AND table_name IN ('orgs', 'usage_events', 'allowances')"
                )
                self.assertEqual(cur.fetchone()[0], 3)
        finally:
            conn.close()


class PostgresStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        if not db_available():
            self.skipTest("no postgres (TEST_DATABASE_URL)")
        self._env = mock.patch.dict(os.environ, _master_env())
        self._env.start()
        self.addCleanup(self._env.stop)
        self._fix = fixture()
        self.url = self._fix.__enter__()
        self.addCleanup(self._fix.__exit__, None, None, None)
        from core.commerce import repo as repo_module

        self.repo_module = repo_module

    def _org_with_owner(self, name="Acme"):
        store = self.repo_module.PostgresBackend(self.url)
        user = store.create_user("clerk|1", "a@x.co", "A")
        org = store.scoped("", user["id"]).create_org(name, user["id"])
        return store.scoped(org["id"], user["id"]), org, user

    def test_org_user_membership_lifecycle(self) -> None:
        store, org, owner = self._org_with_owner()
        other = store.create_user("clerk|2", "b@x.co", "B")
        store.add_membership(org["id"], other["id"], "member")

        mine = store.scoped("", owner["id"]).list_orgs_for_user()
        self.assertEqual([item["id"] for item in mine], [org["id"]])
        self.assertEqual(mine[0]["role"], "owner")

        members = store.list_members(org["id"])
        self.assertEqual(len(members), 2)

        self.assertTrue(store.set_role(org["id"], other["id"], "admin"))
        row = store.get_membership(org["id"], other["id"])
        assert row is not None
        self.assertEqual(row["role"], "admin")

        self.assertTrue(store.remove_membership(org["id"], other["id"]))
        self.assertIsNone(store.get_membership(org["id"], other["id"]))

    def test_user_lookup_by_external_id(self) -> None:
        store = self.repo_module.PostgresBackend(self.url)
        user = store.create_user("clerk|9", "z@x.co", "Z")
        found = store.get_user_by_external("clerk|9")
        assert found is not None
        self.assertEqual(found["id"], user["id"])
        self.assertIsNone(store.get_user_by_external("clerk|nope"))

    def test_device_token_lifecycle(self) -> None:
        store, org, user = self._org_with_owner()
        row, token = store.create_device_token(
            org["id"], user["id"], "A's Pixel"
        )
        self.assertTrue(token.startswith("ta_dev_"))
        self.assertNotIn("token_hash", row)

        from core.connections import store as connection_store

        found = store.get_device_token_by_hash(
            connection_store.hash_key(token)
        )
        assert found is not None
        self.assertEqual(found["id"], row["id"])
        self.assertEqual(found["org_id"], org["id"])

        store.touch_device_token(row["id"])
        listed = store.list_device_tokens(org["id"])
        self.assertEqual(len(listed), 1)
        self.assertTrue(listed[0]["last_used_at"] > 0)

        self.assertTrue(store.revoke_device_token(row["id"], org["id"]))
        listed = store.list_device_tokens(org["id"])
        self.assertTrue(listed[0]["revoked_at"] > 0)

    def test_pairing_code_claim_once(self) -> None:
        store, org, user = self._org_with_owner()
        _, code = store.create_pairing_code(org["id"], user["id"], "Pixel")
        self.assertRegex(code, r"^\d{3}-\d{3}$")
        claimed = store.claim_pairing_code(code)
        assert claimed is not None
        self.assertEqual(claimed["org_id"], org["id"])
        self.assertIsNone(store.claim_pairing_code(code))
        self.assertIsNone(store.claim_pairing_code("000-000"))

    def test_invite_resolve_and_accept(self) -> None:
        import hashlib

        store, org, _user = self._org_with_owner()
        _, token = store.create_invite(org["id"], "b@x.co", "member")
        digest = hashlib.sha256(token.encode()).hexdigest()
        found = store.get_invite_by_hash(digest)
        assert found is not None
        self.assertEqual(found["email"], "b@x.co")
        self.assertTrue(store.mark_invite_accepted(digest))
        self.assertFalse(store.mark_invite_accepted(digest))

    def test_systems_versioned(self) -> None:
        store, org, _user = self._org_with_owner()
        profile = {
            "system_id": "shop-1",
            "name": "shop",
            "kind": "software",
            "status": "draft",
        }
        created = store.create_system(org["id"], profile)
        self.assertEqual(created["version"], 1)
        profile["status"] = "armed"
        saved = store.save_system(org["id"], profile)
        self.assertEqual(saved["version"], 2)
        self.assertEqual(saved["profile"]["status"], "armed")
        self.assertEqual(len(store.list_systems(org["id"])), 1)
        self.assertTrue(store.delete_system(org["id"], "shop-1"))
        self.assertEqual(store.list_systems(org["id"]), [])

    def test_connections_generated_key_and_pasted_secret(self) -> None:
        store, org, _user = self._org_with_owner()
        store.create_system(
            org["id"],
            {"system_id": "shop-1", "name": "s", "kind": "software"},
        )
        row, key = store.create_connection(
            org["id"], "shop-1", "logs", {"service": "api"}, None
        )
        assert key is not None
        self.assertTrue(key.startswith("ta_live_"))
        self.assertTrue(row["secret_hint"].startswith("****"))

        resolved = store.find_record_for_key(key, "logs")
        assert resolved is not None
        self.assertEqual(resolved["org_id"], org["id"])
        self.assertIsNone(store.find_record_for_key(key, "sentry"))

        grow, shown = store.create_connection(
            org["id"], "shop-1", "github",
            {"repo": "acme/api"}, "ghp_pasted_secret",
        )
        self.assertIsNone(shown)
        self.assertEqual(grow["secret_hint"], "****cret")
        self.assertNotIn("secret", grow)
        self.assertNotIn("secret_enc", grow)
        self.assertEqual(
            store.get_connection_secret(org["id"], grow["id"]),
            "ghp_pasted_secret",
        )
        # At rest the DB holds ciphertext, never the pasted secret.
        from core.commerce import db as db_module

        conn = db_module.connect(bootstrap_url())
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT secret_enc FROM connections WHERE id = %s",
                    (grow["id"],),
                )
                blob = cur.fetchone()[0]
        finally:
            conn.close()
        self.assertTrue(blob)
        self.assertNotIn("ghp_pasted_secret", blob)

        store.mark_connection_seen(org["id"], row["id"], "ok", "first")
        seen = store.get_connection(org["id"], row["id"])
        assert seen is not None
        self.assertEqual(seen["status"], "ok")
        self.assertTrue(store.delete_connection(org["id"], row["id"]))

    def test_pause_rate_audit_runs(self) -> None:
        store, org, user = self._org_with_owner()
        self.assertFalse(store.get_pause(org["id"])["paused"])
        paused = store.set_pause(org["id"], True, user["id"])
        self.assertTrue(paused["paused"])
        self.assertEqual(paused["by_user"], user["id"])

        self.assertEqual(store.get_rate(org["id"], "shop-1"), 0.0)
        store.stamp_rate(org["id"], "shop-1")
        self.assertGreater(store.get_rate(org["id"], "shop-1"), 0.0)

        store.audit(org["id"], {"actor": user["id"], "action": "pause"})
        items = store.list_audit(org["id"])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["action"], "pause")

        run = store.create_run(
            org["id"],
            {
                "system_id": "shop-1",
                "domain": "software",
                "kind": "repo_fix",
                "status": "running",
                "fingerprint": "abc123",
            },
        )
        self.assertTrue(
            store.update_run(
                org["id"], run["id"],
                {"status": "PASS", "finished": True},
            )
        )
        found = store.find_run_by_fingerprint(org["id"], "abc123")
        assert found is not None
        self.assertEqual(found["status"], "PASS")
        self.assertTrue(found["finished_at"] > 0)

    def test_usage_events_bump_allowance_atomically(self) -> None:
        store, org, _user = self._org_with_owner()
        before = store.get_allowance(org["id"])
        self.assertEqual(before["fix_runs_limit"], 30)
        store.record_usage_event(
            org["id"], "fix_run", system_id="shop-1", run_id="run_1",
            provider="baseten", model="muse-spark", language="go",
            cost_estimate_usd=1.5, consume_fix_run=True,
        )
        after = store.get_allowance(org["id"])
        self.assertEqual(after["fix_runs_used"], 1)
        self.assertAlmostEqual(after["cost_used_usd"], 1.5)
        events = store.list_usage(org["id"])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["language"], "go")
        reset = store.reset_allowance_counters(org["id"], "2026-11")
        self.assertEqual(reset["fix_runs_used"], 0)
        self.assertEqual(reset["period_month"], "2026-11")

    def test_rls_org_b_sees_nothing_of_org_a(self) -> None:
        store_a, org_a, user_a = self._org_with_owner("OrgA")
        store = self.repo_module.PostgresBackend(self.url)
        user_b = store.create_user("clerk|b", "b@x.co", "B")
        org_b = store.scoped("", user_b["id"]).create_org("OrgB", user_b["id"])
        store_b = store.scoped(org_b["id"], user_b["id"])

        store_a.create_system(
            org_a["id"],
            {"system_id": "a-1", "name": "a", "kind": "software"},
        )
        store_a.create_run(org_a["id"], {"status": "PASS"})
        store_a.record_usage_event(org_a["id"], "fix_run")

        self.assertEqual(store_b.list_systems(org_b["id"]), [])
        self.assertIsNone(store_b.get_system(org_b["id"], "a-1"))
        self.assertEqual(store_b.list_connections(org_b["id"]), [])
        self.assertEqual(store_b.list_usage(org_b["id"]), [])
        self.assertEqual(store_b.list_members(org_b["id"]), [
            {
                "user_id": user_b["id"],
                "email": "b@x.co",
                "name": "B",
                "role": "owner",
                "created_at": store_b.list_members(org_b["id"])[0][
                    "created_at"
                ],
            }
        ])
        # Unscoped reads with no settings see nothing (fail closed).
        bare = self.repo_module.PostgresBackend(self.url)
        self.assertEqual(bare.list_systems(""), [])
        self.assertIsNone(bare.get_user(user_a["id"]))

    def test_crypto_round_trip_and_wrong_key(self) -> None:
        from core.commerce import crypto as crypto_module

        store, org, _user = self._org_with_owner()
        sealed = crypto_module.encrypt_for_org(org["id"], "s3cret", store)
        self.assertNotIn("s3cret", sealed)
        self.assertEqual(
            crypto_module.decrypt_for_org(org["id"], sealed, store), "s3cret"
        )
        other = _master_env()["COMMERCE_MASTER_KEY"]
        with mock.patch.dict(os.environ, {"COMMERCE_MASTER_KEY": other}):
            with self.assertRaises(crypto_module.CommerceCryptoError):
                crypto_module.decrypt_for_org(org["id"], sealed, store)


class FileBackendTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.mkdtemp(prefix="ta-com-file-")
        self.addCleanup(
            lambda: __import__("shutil").rmtree(tmp, ignore_errors=True)
        )
        env = {"TA_DATA_DIR": tmp, **_master_env()}
        env_patch = mock.patch.dict(os.environ, env)
        env_patch.start()
        self.addCleanup(env_patch.stop)
        from core.commerce import repo as repo_module

        self.store = repo_module.FileBackend()

    def test_org_user_membership_device_invite(self) -> None:
        user = self.store.create_user("ext|1", "a@x.co", "A")
        org = self.store.create_org("Acme", user["id"])
        row = self.store.get_membership(org["id"], user["id"])
        assert row is not None
        self.assertEqual(row["role"], "owner")
        self.assertEqual(len(self.store.list_members(org["id"])), 1)

        _, token = self.store.create_device_token(
            org["id"], user["id"], "Pixel"
        )
        from core.connections import store as connection_store

        found = self.store.get_device_token_by_hash(
            connection_store.hash_key(token)
        )
        assert found is not None
        self.assertTrue(
            self.store.revoke_device_token(found["id"], org["id"])
        )

        _, code = self.store.create_pairing_code(
            org["id"], user["id"], "Pixel"
        )
        self.assertIsNotNone(self.store.claim_pairing_code(code))
        self.assertIsNone(self.store.claim_pairing_code(code))

        _, invite = self.store.create_invite(org["id"], "b@x.co", "member")
        import hashlib

        digest = hashlib.sha256(invite.encode()).hexdigest()
        self.assertIsNotNone(self.store.get_invite_by_hash(digest))
        self.assertTrue(self.store.mark_invite_accepted(digest))

    def test_systems_and_connections_delegate(self) -> None:
        created = self.store.create_system(
            "self",
            {"system_id": "shop-1", "name": "s", "kind": "software"},
        )
        self.assertEqual(created["org_id"], "self")
        row = self.store.get_system("self", "shop-1")
        assert row is not None
        self.assertEqual(row["profile"]["name"], "s")
        self.assertEqual(len(self.store.list_systems("self")), 1)

        conn, key = self.store.create_connection(
            "self", "shop-1", "logs", {}, None
        )
        assert key is not None
        resolved = self.store.find_record_for_key(key, "logs")
        assert resolved is not None
        self.assertEqual(resolved["org_id"], "self")
        self.assertTrue(self.store.delete_connection("self", conn["id"]))
        self.assertTrue(self.store.delete_system("self", "shop-1"))

    def test_pause_rate_audit_runs_usage(self) -> None:
        self.store.set_pause("self", True, "usr_1")
        self.assertTrue(self.store.get_pause("self")["paused"])
        self.store.stamp_rate("self", "s")
        self.assertGreater(self.store.get_rate("self", "s"), 0.0)
        self.store.audit("self", {"action": "x"})
        self.assertEqual(len(self.store.list_audit("self")), 1)

        run = self.store.create_run("self", {"status": "running"})
        self.store.update_run("self", run["id"], {"status": "PASS"})
        found = self.store.find_run_by_fingerprint(
            "self", run["fingerprint"]
        )
        assert found is not None
        self.assertEqual(found["status"], "PASS")

        self.store.record_usage_event(
            "self", "fix_run", cost_estimate_usd=2.0, consume_fix_run=True
        )
        allowance = self.store.get_allowance("self")
        self.assertEqual(allowance["fix_runs_used"], 1)
        self.assertEqual(len(self.store.list_usage("self")), 1)

    def test_crypto_round_trip_file_backend(self) -> None:
        from core.commerce import crypto as crypto_module

        user = self.store.create_user("ext|9", "c@x.co", "C")
        org = self.store.create_org("Acme", user["id"])
        sealed = crypto_module.encrypt_for_org(
            org["id"], "s3cret", self.store
        )
        self.assertEqual(
            crypto_module.decrypt_for_org(org["id"], sealed, self.store),
            "s3cret",
        )


class BootTests(unittest.TestCase):
    def test_api_boots_against_postgres(self) -> None:
        if not db_available():
            self.skipTest("no postgres (TEST_DATABASE_URL)")
        from fastapi.testclient import TestClient

        with fixture():
            with mock.patch.dict(os.environ, {"DATABASE_URL": app_url()}):
                from apps.api.main import app

                with TestClient(app) as client:
                    response = client.get("/api/health")
        self.assertEqual(response.status_code, 200)

    def test_api_boots_without_database(self) -> None:
        from fastapi.testclient import TestClient

        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DATABASE_URL", None)
            from apps.api.main import app

            with TestClient(app) as client:
                response = client.get("/api/health")
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
