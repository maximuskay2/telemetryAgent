"""Legacy JSON → `legacy` org migration (C-J3).

Postgres tests use the tests/commerce_db.py fixture (ta_test role, so
RLS is really enforced) and skip when Postgres is unreachable. Guard
tests (no DB / no owner) run everywhere.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.commerce_db import db_available, fixture

OWNER = "user_legacy_owner"


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _seed(data_dir: Path) -> dict:
    from core.connections import store as connection_store

    device_key = connection_store.new_live_key()
    _write(
        data_dir / "profiles" / "shop.json",
        {
            "system_id": "shop",
            "kind": "software",
            "status": "active",
            "name": "Shop",
            "environment": {"region": "eu"},
        },
    )
    _write(
        data_dir / "profiles" / "demo1.json",
        {
            "system_id": "demo1",
            "kind": "software",
            "status": "active",
            "name": "Demo",
            "environment": {"demo": "true"},
        },
    )
    _write(
        data_dir / "connections" / "conn_dev.json",
        {
            "id": "conn_dev",
            "system_id": "shop",
            "kind": "device",
            "config": {},
            "secret_hint": connection_store.secret_hint(device_key),
            "key_hash": connection_store.hash_key(device_key),
            "secret": "",
            "status": "ok",
            "detail": "",
            "last_seen": 1700000000.0,
            "created_at": 1699999999.0,
        },
    )
    _write(
        data_dir / "connections" / "conn_gh.json",
        {
            "id": "conn_gh",
            "system_id": "shop",
            "kind": "github",
            "config": {"repo": "acme/shop"},
            "secret_hint": "ghp_…",
            "key_hash": "",
            "secret": "ghp_test_secret",
            "status": "ok",
            "detail": "",
            "last_seen": 0.0,
            "created_at": 1699999999.0,
        },
    )
    _write(data_dir / "pause.json", {"paused": True, "at": 1700000001.0})
    _write(
        data_dir / "mitigations.json",
        {
            "last": {"shop": 1700000002.0},
            "log": [
                {
                    "actor": "phone",
                    "action": "restart",
                    "system_id": "shop",
                }
            ],
        },
    )
    return {"device_key": device_key}


class GuardTests(unittest.TestCase):
    def test_requires_postgres(self) -> None:
        from core.commerce import migrate as migrate_module

        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DATABASE_URL", None)
            with self.assertRaises(RuntimeError):
                migrate_module.migrate(
                    data_dir=Path(tempfile.mkdtemp()),
                    owner_external_id=OWNER,
                )

    def test_requires_owner(self) -> None:
        from core.commerce import migrate as migrate_module

        with self.assertRaises(RuntimeError):
            migrate_module.migrate(
                data_dir=Path(tempfile.mkdtemp()),
                owner_external_id="",
                url="postgresql://x/y",
            )


class MigrateTests(unittest.TestCase):
    def setUp(self) -> None:
        if not db_available():
            self.skipTest("no postgres (TEST_DATABASE_URL)")
        from cryptography.fernet import Fernet

        self._env = mock.patch.dict(
            os.environ,
            {"COMMERCE_MASTER_KEY": Fernet.generate_key().decode("ascii")},
        )
        self._env.start()
        self.addCleanup(self._env.stop)

    def test_full_import(self) -> None:
        from core.commerce import migrate as migrate_module
        from core.commerce import models as models_module
        from core.commerce import repo as repo_module

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            seed = _seed(root)
            with fixture() as url:
                result = migrate_module.migrate(
                    data_dir=root,
                    owner_external_id=OWNER,
                    email="owner@example.com",
                    url=url,
                )
                self.assertEqual(result["org_id"], models_module.LEGACY_ORG_ID)
                self.assertEqual(
                    result["profiles"], {"imported": 1, "skipped": 1}
                )
                self.assertEqual(
                    result["connections"], {"imported": 2, "skipped": 0}
                )
                self.assertTrue(result["controls"]["paused"])
                self.assertEqual(result["controls"]["rate_stamps"], 1)
                self.assertEqual(result["controls"]["audit"], 1)

                store = repo_module.PostgresBackend(url).scoped(
                    models_module.LEGACY_ORG_ID, result["owner_id"]
                )
                membership = store.get_membership(
                    models_module.LEGACY_ORG_ID, result["owner_id"]
                )
                assert membership is not None
                self.assertEqual(membership["role"], "owner")
                systems = store.list_systems(models_module.LEGACY_ORG_ID)
                self.assertEqual([s["id"] for s in systems], ["shop"])
                self.assertEqual(
                    systems[0]["profile"]["name"], "Shop"
                )
                # Device keys keep working: the hash resolves to legacy.
                record = store.find_record_for_key(
                    seed["device_key"], "device"
                )
                assert record is not None
                self.assertEqual(
                    record["org_id"], models_module.LEGACY_ORG_ID
                )
                self.assertEqual(record["system_id"], "shop")
                # Plaintext secrets are re-sealed, not copied raw.
                self.assertEqual(
                    store.get_connection_secret(
                        models_module.LEGACY_ORG_ID, "conn_gh"
                    ),
                    "ghp_test_secret",
                )
                self.assertTrue(
                    store.get_pause(models_module.LEGACY_ORG_ID)["paused"]
                )
                self.assertGreater(
                    store.get_rate(models_module.LEGACY_ORG_ID, "shop"), 0.0
                )
                rows = store.list_audit(models_module.LEGACY_ORG_ID)
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["actor"], "legacy-import")

    def test_rerun_is_idempotent(self) -> None:
        from core.commerce import migrate as migrate_module
        from core.commerce import models as models_module
        from core.commerce import repo as repo_module

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed(root)
            with fixture() as url:
                migrate_module.migrate(
                    data_dir=root, owner_external_id=OWNER, url=url
                )
                second = migrate_module.migrate(
                    data_dir=root, owner_external_id=OWNER, url=url
                )
                self.assertEqual(
                    second["connections"], {"imported": 0, "skipped": 2}
                )
                self.assertEqual(second["controls"]["audit"], 0)
                self.assertEqual(second["controls"]["audit_skipped"], 1)
                store = repo_module.PostgresBackend(url).scoped(
                    models_module.LEGACY_ORG_ID, second["owner_id"]
                )
                systems = store.list_systems(models_module.LEGACY_ORG_ID)
                self.assertEqual(len(systems), 1)
                rows = store.list_audit(models_module.LEGACY_ORG_ID)
                self.assertEqual(len(rows), 1)
                members = store.list_members(models_module.LEGACY_ORG_ID)
                self.assertEqual(len(members), 1)

    def test_empty_store_migrates_org_only(self) -> None:
        from core.commerce import migrate as migrate_module
        from core.commerce import models as models_module

        with tempfile.TemporaryDirectory() as tmp:
            with fixture() as url:
                result = migrate_module.migrate(
                    data_dir=Path(tmp), owner_external_id=OWNER, url=url
                )
                self.assertEqual(result["org_id"], models_module.LEGACY_ORG_ID)
                self.assertEqual(
                    result["profiles"], {"imported": 0, "skipped": 0}
                )
                self.assertEqual(
                    result["connections"], {"imported": 0, "skipped": 0}
                )
                self.assertFalse(result["controls"]["paused"])


if __name__ == "__main__":
    unittest.main()
