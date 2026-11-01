"""J-R0 acceptance: real connections store + ta_live_ keys (James)."""

import json
import os
import stat
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from apps.api.main import app
from core.connections import auth as key_auth
from core.connections import store as connection_store
from core.schemas.profile import SystemProfile
from core.setup import store as setup_store


def _tmp_data() -> str:
    return tempfile.mkdtemp(prefix="ta-conn-test-")


def _save_system(tmp: str, system_id: str = "acme") -> None:
    with patch.dict(os.environ, {"TA_DATA_DIR": tmp}):
        setup_store.save_profile(
            SystemProfile(system_id=system_id, name="Acme", kind="software")
        )


class ConnectionStoreTests(unittest.TestCase):
    def test_key_shown_once_and_stored_hashed_mode_600(self) -> None:
        tmp = _tmp_data()
        with patch.dict(os.environ, {"TA_DATA_DIR": tmp}):
            connection, key = connection_store.create_connection(
                "acme", "logs", {}, None
            )
            assert key is not None
            self.assertTrue(key.startswith("ta_live_"))
            path = connection_store.connection_path(connection.id)
            mode = stat.S_IMODE(path.stat().st_mode)
            self.assertEqual(mode, 0o600)
            raw = path.read_text(encoding="utf-8")
            self.assertNotIn(key, raw)
            self.assertIn(connection_store.hash_key(key), raw)
            again = connection_store.get_connection(connection.id)
            assert again is not None
            self.assertEqual(again.secret_hint, "****" + key[-4:])
            self.assertEqual(
                connection_store.find_system_for_key(key, "logs"), "acme"
            )
            self.assertIsNone(
                connection_store.find_system_for_key(key, "device")
            )

    def test_delete_kills_key_immediately(self) -> None:
        tmp = _tmp_data()
        with patch.dict(os.environ, {"TA_DATA_DIR": tmp}):
            connection, key = connection_store.create_connection(
                "acme", "device", {}, None
            )
            assert key is not None
            self.assertEqual(
                connection_store.find_system_for_key(key, "device"), "acme"
            )
            self.assertTrue(
                connection_store.delete_connection(connection.id)
            )
            self.assertIsNone(
                connection_store.find_system_for_key(key, "device")
            )
            self.assertFalse(
                connection_store.delete_connection(connection.id)
            )

    def test_mark_seen_stamps_status(self) -> None:
        tmp = _tmp_data()
        with patch.dict(os.environ, {"TA_DATA_DIR": tmp}):
            connection, _ = connection_store.create_connection(
                "acme", "logs", {}, None
            )
            self.assertEqual(connection.status, "waiting")
            connection_store.mark_seen(connection.id)
            updated = connection_store.get_connection(connection.id)
            assert updated is not None
            self.assertEqual(updated.status, "ok")
            self.assertGreater(updated.last_seen, 0.0)


class ConnectionApiTests(unittest.TestCase):
    def test_create_needs_known_system_and_secret_for_github(self) -> None:
        tmp = _tmp_data()
        with patch.dict(os.environ, {"TA_DATA_DIR": tmp}):
            with TestClient(app) as client:
                missing = client.post(
                    "/api/connections",
                    json={"system_id": "ghost", "kind": "logs", "config": {}},
                )
                self.assertEqual(missing.status_code, 404)
        _save_system(tmp)
        with patch.dict(os.environ, {"TA_DATA_DIR": tmp}):
            with TestClient(app) as client:
                no_secret = client.post(
                    "/api/connections",
                    json={
                        "system_id": "acme",
                        "kind": "github",
                        "config": {"repo": "acme/api"},
                    },
                )
                self.assertEqual(no_secret.status_code, 400)

    def test_github_secret_never_returned_but_recoverable(self) -> None:
        tmp = _tmp_data()
        _save_system(tmp)
        with patch.dict(os.environ, {"TA_DATA_DIR": tmp}):
            with TestClient(app) as client:
                created = client.post(
                    "/api/connections",
                    json={
                        "system_id": "acme",
                        "kind": "github",
                        "config": {"repo": "acme/api"},
                        "secret": "ghp_testtoken1234",
                    },
                )
                self.assertEqual(created.status_code, 200)
                body = created.json()
                self.assertIsNone(body["key"])
                self.assertEqual(
                    body["connection"]["secret_hint"], "****1234"
                )
                listed = client.get("/api/connections?system_id=acme")
                dumped = json.dumps(listed.json())
                self.assertNotIn("ghp_testtoken1234", dumped)
                connection_id = body["connection"]["id"]
                self.assertEqual(
                    connection_store.get_secret(connection_id),
                    "ghp_testtoken1234",
                )
                with patch(
                    "core.connections.github.check_repo",
                    return_value={
                        "ok": True,
                        "detail": "connected · default branch main",
                        "permissions": {
                            "read": True,
                            "pull_requests": True,
                        },
                    },
                ):
                    tested = client.post(
                        f"/api/connections/{connection_id}/test"
                    )
                self.assertTrue(tested.json()["ok"])
                self.assertEqual(
                    tested.json()["permissions"],
                    {"read": True, "pull_requests": True},
                )

    def test_deleted_key_fails_ingest_immediately(self) -> None:
        tmp = _tmp_data()
        _save_system(tmp)
        line = {"ts": 1.0, "level": "ERROR", "message": "boom"}
        payload = {"service": "api", "lines": [line]}
        with patch.dict(os.environ, {"TA_DATA_DIR": tmp}):
            with TestClient(app) as client:
                created = client.post(
                    "/api/connections",
                    json={"system_id": "acme", "kind": "logs", "config": {}},
                )
                key = created.json()["key"]
                headers = {"Authorization": f"Bearer {key}"}
                ok = client.post("/api/ingest/logs", json=payload, headers=headers)
                self.assertEqual(ok.status_code, 200)
                connection_id = created.json()["connection"]["id"]
                client.delete(f"/api/connections/{connection_id}")
                dead = client.post(
                    "/api/ingest/logs", json=payload, headers=headers
                )
                self.assertEqual(dead.status_code, 401)
                self.assertIsNone(key_auth.system_for_key(key, "logs"))

    def test_fixture_key_gated_on_api(self) -> None:
        tmp = _tmp_data()
        line = {"ts": 1.0, "level": "ERROR", "message": "boom"}
        payload = {"service": "api", "lines": [line]}
        headers = {"Authorization": "Bearer ta_live_fixture"}
        with patch.dict(os.environ, {"TA_DATA_DIR": tmp}):
            os.environ.pop("TA_FIXTURE_KEYS", None)
            with TestClient(app) as client:
                denied = client.post(
                    "/api/ingest/logs", json=payload, headers=headers
                )
                self.assertEqual(denied.status_code, 401)
        with patch.dict(
            os.environ, {"TA_DATA_DIR": tmp, "TA_FIXTURE_KEYS": "1"}
        ):
            with TestClient(app) as client:
                allowed = client.post(
                    "/api/ingest/logs", json=payload, headers=headers
                )
                self.assertEqual(allowed.status_code, 200)


class ConnectDoorTests(unittest.TestCase):
    LOGS = {"system_id": "acme", "kind": "logs", "config": {}}

    def test_switch_off_refuses_every_connection_route(self) -> None:
        tmp = _tmp_data()
        _save_system(tmp)
        env = {"TA_DATA_DIR": tmp, "PRODUCTION_CONNECT_ENABLED": "0"}
        with patch.dict(os.environ, env):
            os.environ.pop("CONNECT_ACCESS_CODE", None)
            with TestClient(app) as client:
                door = client.get("/api/connections/enabled").json()
                self.assertFalse(door["enabled"])
                created = client.post("/api/connections", json=self.LOGS)
                self.assertEqual(created.status_code, 403)
                listed = client.get("/api/connections")
                self.assertEqual(listed.status_code, 403)

    def test_access_code_guards_create_list_test_delete(self) -> None:
        tmp = _tmp_data()
        _save_system(tmp)
        env = {"TA_DATA_DIR": tmp, "CONNECT_ACCESS_CODE": "judges-2026"}
        good = {"X-Connect-Code": "judges-2026"}
        with patch.dict(os.environ, env):
            os.environ.pop("PRODUCTION_CONNECT_ENABLED", None)
            with TestClient(app) as client:
                door = client.get("/api/connections/enabled").json()
                self.assertEqual(door, {"enabled": True, "code_required": True})
                self.assertEqual(
                    client.post("/api/connections/code").status_code, 401
                )
                self.assertEqual(
                    client.post(
                        "/api/connections/code",
                        headers={"X-Connect-Code": "wrong"},
                    ).status_code,
                    401,
                )
                self.assertEqual(
                    client.post(
                        "/api/connections/code", headers=good
                    ).status_code,
                    200,
                )
                denied = client.post("/api/connections", json=self.LOGS)
                self.assertEqual(denied.status_code, 401)
                created = client.post(
                    "/api/connections", json=self.LOGS, headers=good
                )
                self.assertEqual(created.status_code, 200)
                conn_id = created.json()["connection"]["id"]
                self.assertEqual(
                    client.get("/api/connections").status_code, 401
                )
                self.assertEqual(
                    client.get("/api/connections", headers=good).status_code,
                    200,
                )
                self.assertEqual(
                    client.post(
                        f"/api/connections/{conn_id}/test"
                    ).status_code,
                    401,
                )
                self.assertEqual(
                    client.delete(f"/api/connections/{conn_id}").status_code,
                    401,
                )
                self.assertEqual(
                    client.delete(
                        f"/api/connections/{conn_id}", headers=good
                    ).status_code,
                    200,
                )


class ConnectionIdentityTests(unittest.TestCase):
    def test_identities(self) -> None:
        from apps.api.routes.production import _connection_identity

        self.assertEqual(
            _connection_identity("github", {"repo": "Acme/Api"}), "acme/api"
        )
        self.assertEqual(
            _connection_identity("railway", {"service_id": "svc-1"}), "svc-1"
        )
        self.assertEqual(
            _connection_identity("webhook", {"url": "https://x/hook"}),
            "https://x/hook",
        )

    def test_no_identity_means_always_create(self) -> None:
        from apps.api.routes.production import _connection_identity

        self.assertIsNone(_connection_identity("logs", {}))
        self.assertIsNone(_connection_identity("sentry", {}))
        self.assertIsNone(_connection_identity("device", {}))
        self.assertIsNone(_connection_identity("github", {}))
        self.assertIsNone(_connection_identity("github", {"repo": "  "}))
        self.assertIsNone(_connection_identity("github", None))


class ConnectionRetryTests(unittest.TestCase):
    def test_retry_same_repo_updates_in_place(self) -> None:
        tmp = _tmp_data()
        _save_system(tmp)
        with patch.dict(os.environ, {"TA_DATA_DIR": tmp}):
            os.environ.pop("DATABASE_URL", None)
            with TestClient(app) as client:
                first = client.post(
                    "/api/connections",
                    json={
                        "system_id": "acme",
                        "kind": "github",
                        "config": {"repo": "acme/api"},
                        "secret": "ghp_1111",
                    },
                )
                self.assertEqual(first.status_code, 200)
                retry = client.post(
                    "/api/connections",
                    json={
                        "system_id": "acme",
                        "kind": "github",
                        "config": {"repo": "Acme/Api"},
                        "secret": "ghp_2222",
                    },
                )
                self.assertEqual(retry.status_code, 200)
                self.assertEqual(
                    retry.json()["connection"]["id"],
                    first.json()["connection"]["id"],
                )
                listed = client.get(
                    "/api/connections", params={"system_id": "acme"}
                )
                self.assertEqual(listed.status_code, 200)
                self.assertEqual(len(listed.json()["connections"]), 1)
                self.assertEqual(
                    listed.json()["connections"][0]["secret_hint"], "****2222"
                )

    def test_different_repo_creates_new_row(self) -> None:
        tmp = _tmp_data()
        _save_system(tmp)
        with patch.dict(os.environ, {"TA_DATA_DIR": tmp}):
            os.environ.pop("DATABASE_URL", None)
            with TestClient(app) as client:
                for repo in ("acme/api", "acme/other"):
                    response = client.post(
                        "/api/connections",
                        json={
                            "system_id": "acme",
                            "kind": "github",
                            "config": {"repo": repo},
                            "secret": "ghp_x",
                        },
                    )
                    self.assertEqual(response.status_code, 200)
                listed = client.get(
                    "/api/connections", params={"system_id": "acme"}
                )
                self.assertEqual(len(listed.json()["connections"]), 2)

    def test_generated_keys_never_dedupe(self) -> None:
        tmp = _tmp_data()
        _save_system(tmp)
        with patch.dict(os.environ, {"TA_DATA_DIR": tmp}):
            os.environ.pop("DATABASE_URL", None)
            with TestClient(app) as client:
                ids = set()
                for _ in range(2):
                    response = client.post(
                        "/api/connections",
                        json={
                            "system_id": "acme",
                            "kind": "logs",
                            "config": {},
                        },
                    )
                    self.assertEqual(response.status_code, 200)
                    ids.add(response.json()["connection"]["id"])
                self.assertEqual(len(ids), 2)
