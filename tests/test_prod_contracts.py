"""H0 contract tests: §3.4 shapes + key auth (James)."""

import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from apps.api.main import app
from core.actions import mitigate
from core.connections import is_production
from core.connections import auth as key_auth
from core.schemas.events import SimEvent
from core.schemas.production import (
    FIXTURE_KEY,
    FIXTURE_SYSTEM_ID,
    Connection,
    OptionsResult,
)
from core.schemas.profile import SystemProfile
from core.setup import store as setup_store


def _tmp_data() -> str:
    return tempfile.mkdtemp(prefix="ta-prod-test-")


def _save_system(tmp: str, system_id: str = "acme") -> None:
    with patch.dict(os.environ, {"TA_DATA_DIR": tmp}):
        setup_store.save_profile(
            SystemProfile(system_id=system_id, name="Acme", kind="software")
        )


class IsProductionTests(unittest.TestCase):
    def test_demo_and_missing_mode_are_not_production(self) -> None:
        class Profile:
            def __init__(self, environment):
                self.environment = environment

        self.assertFalse(is_production(Profile({})))
        self.assertFalse(is_production(Profile({"demo": "true"})))
        self.assertFalse(is_production(Profile({"mode": "demo"})))
        self.assertFalse(is_production(None))

    def test_production_mode_is_production(self) -> None:
        class Profile:
            environment = {"mode": "production"}

        self.assertTrue(is_production(Profile()))


class FixtureKeyTests(unittest.TestCase):
    def test_fixture_key_resolves_only_with_flag(self) -> None:
        with patch.dict(os.environ, {"TA_FIXTURE_KEYS": "1"}):
            self.assertEqual(
                key_auth.system_for_key(FIXTURE_KEY, "logs"),
                FIXTURE_SYSTEM_ID,
            )
            self.assertEqual(
                key_auth.system_for_key(FIXTURE_KEY, "device"),
                FIXTURE_SYSTEM_ID,
            )
        with patch.dict(os.environ, {"TA_FIXTURE_KEYS": "0"}):
            self.assertIsNone(key_auth.system_for_key(FIXTURE_KEY, "logs"))
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TA_FIXTURE_KEYS", None)
            self.assertIsNone(key_auth.system_for_key(FIXTURE_KEY, "logs"))

    def test_wrong_key_resolves_to_none(self) -> None:
        self.assertIsNone(key_auth.system_for_key("nope", "logs"))
        self.assertIsNone(key_auth.system_for_key("", "device"))


class MitigateStubTests(unittest.TestCase):
    def test_no_options_not_paused_execute_refused(self) -> None:
        self.assertEqual(mitigate.software_options({}), [])
        self.assertFalse(mitigate.is_paused())
        result = mitigate.execute("sys", "rollback", "run1")
        self.assertEqual(result["status"], "refused")


class NewEventKindTests(unittest.TestCase):
    def test_h0_kinds_validate(self) -> None:
        for kind in (
            "connection_status",
            "option_status",
            "actions_paused",
            "pr_opened",
        ):
            event = SimEvent(kind=kind, payload={})
            self.assertEqual(event.kind, kind)


class StubEndpointTests(unittest.TestCase):
    def test_enabled_follows_env_flag(self) -> None:
        with TestClient(app) as client:
            with patch.dict(os.environ, {"PRODUCTION_CONNECT_ENABLED": "1"}):
                response = client.get("/api/connections/enabled")
            self.assertEqual(response.json(), {"enabled": True})
            with patch.dict(os.environ, {"PRODUCTION_CONNECT_ENABLED": "0"}):
                response = client.get("/api/connections/enabled")
            self.assertEqual(response.json(), {"enabled": False})

    def test_connections_crud_shapes(self) -> None:
        tmp = _tmp_data()
        _save_system(tmp)
        with patch.dict(os.environ, {"TA_DATA_DIR": tmp}):
            with TestClient(app) as client:
                created = client.post(
                    "/api/connections",
                    json={"system_id": "acme", "kind": "logs", "config": {}},
                )
                self.assertEqual(created.status_code, 200)
                body = created.json()
                self.assertTrue(body["key"].startswith("ta_live_"))
                Connection.model_validate(body["connection"])
                listed = client.get("/api/connections?system_id=acme")
                self.assertEqual(listed.status_code, 200)
                for item in listed.json()["connections"]:
                    Connection.model_validate(item)
                    self.assertNotIn("secret", item)
                    self.assertNotIn("key", item)
                tested = client.post(
                    f"/api/connections/{body['connection']['id']}/test"
                )
                self.assertTrue(tested.json()["ok"])
                deleted = client.delete(
                    f"/api/connections/{body['connection']['id']}"
                )
                self.assertEqual(deleted.json(), {"deleted": True})

    def test_ingest_auth_and_shapes(self) -> None:
        tmp = _tmp_data()
        line = {"ts": 1.0, "level": "ERROR", "message": "boom"}
        body = {"service": "api", "release": "v1", "commit": "abc", "lines": [line]}
        env = {"TA_DATA_DIR": tmp, "TA_FIXTURE_KEYS": "1"}
        with patch.dict(os.environ, env):
            with TestClient(app) as client:
                denied = client.post("/api/ingest/logs", json=body)
                self.assertEqual(denied.status_code, 401)
                wrong = client.post(
                    "/api/ingest/logs",
                    json=body,
                    headers={"Authorization": "Bearer wrong"},
                )
                self.assertEqual(wrong.status_code, 401)
                ok = client.post(
                    "/api/ingest/logs",
                    json=body,
                    headers={"Authorization": f"Bearer {FIXTURE_KEY}"},
                )
                # Real pipeline now: 1 line, no rule hit.
                self.assertEqual(ok.json(), {"accepted": 1, "candidates": 0})
                sentry_denied = client.post("/api/ingest/sentry/wrong", json={})
                self.assertEqual(sentry_denied.status_code, 401)
                sentry_ok = client.post(
                    f"/api/ingest/sentry/{FIXTURE_KEY}", json={}
                )
                self.assertEqual(sentry_ok.json(), {"accepted": 1})

    def test_options_fixture_echoes_run_id(self) -> None:
        with TestClient(app) as client:
            response = client.get("/api/incidents/run9/options")
            self.assertEqual(response.status_code, 200)
            parsed = OptionsResult.model_validate(response.json())
            self.assertEqual(parsed.run_id, "run9")
            self.assertEqual(len(parsed.options), 1)

    def test_execute_needs_mobile_token_when_set(self) -> None:
        url = "/api/incidents/run9/options/opt_1/execute"
        with TestClient(app) as client:
            with patch.dict(os.environ, {"MOBILE_API_TOKEN": ""}):
                opened = client.post(url)
                self.assertEqual(
                    opened.json(), {"status": "sent", "command_id": "cmd_1"}
                )
            with patch.dict(os.environ, {"MOBILE_API_TOKEN": "secret"}):
                denied = client.post(url)
                self.assertEqual(denied.status_code, 401)
                allowed = client.post(url, headers={"X-Mobile-Token": "secret"})
                self.assertEqual(allowed.status_code, 200)

    def test_device_commands_need_device_key(self) -> None:
        env = {"TA_DATA_DIR": _tmp_data(), "TA_FIXTURE_KEYS": "1"}
        with patch.dict(os.environ, env):
            with TestClient(app) as client:
                denied = client.get("/api/devices/esp1/commands")
                self.assertEqual(denied.status_code, 401)
                ok = client.get(
                    "/api/devices/esp1/commands",
                    headers={"Authorization": f"Bearer {FIXTURE_KEY}"},
                )
                self.assertEqual(ok.status_code, 200)
                self.assertEqual(ok.json()["commands"][0]["id"], "cmd_1")
                ack = client.post(
                    "/api/devices/esp1/commands/cmd_1/ack",
                    json={"ok": True, "detail": ""},
                    headers={"Authorization": f"Bearer {FIXTURE_KEY}"},
                )
                self.assertEqual(ack.json(), {"status": "done"})

    def test_pause_round_trip(self) -> None:
        with TestClient(app) as client:
            with patch.dict(os.environ, {"MOBILE_API_TOKEN": ""}):
                state = client.get("/api/actions/pause")
                self.assertEqual(state.json(), {"paused": False})
                flipped = client.post(
                    "/api/actions/pause", json={"paused": True}
                )
                self.assertEqual(flipped.json(), {"paused": True})
