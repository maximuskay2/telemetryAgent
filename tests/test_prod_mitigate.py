"""J-R4 acceptance: mitigations + pause (James). Railway mocked."""

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

import apps.api.main as api_main
from apps.api.main import app
from core.actions import mitigate
from core.connections import store as connection_store
from core.schemas.profile import Policy, SystemProfile
from core.schemas.remediation import ExecutionResult
from core.setup import store as setup_store

ROOT = Path(__file__).resolve().parent.parent
HOOK_URL = "http://hook.test/mitigate"


def _tmp_data() -> str:
    return tempfile.mkdtemp(prefix="ta-mitigate-test-")


def _save_system(
    tmp: str,
    system_id: str = "acme",
    status: str = "armed",
    allowed: Optional[list] = None,
) -> None:
    with patch.dict(os.environ, {"TA_DATA_DIR": tmp}):
        setup_store.save_profile(
            SystemProfile(
                system_id=system_id,
                name="Acme",
                kind="software",
                environment={"mode": "production"},
                status=status,
                policy=Policy(
                    allowed_actions=(
                        allowed if allowed is not None
                        else ["rollback", "restart"]
                    ),
                    auto_fix_allowed=False,
                ),
            )
        )


def _save_webhook(tmp: str, system_id: str = "acme") -> str:
    with patch.dict(os.environ, {"TA_DATA_DIR": tmp}):
        connection, _ = connection_store.create_connection(
            system_id, "webhook", {"url": HOOK_URL}, "whsec_test"
        )
        return connection.id


def _hook_client(status: int = 200, seen: Optional[list] = None) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(status, json={"ok": status == 200})

    return httpx.Client(
        transport=httpx.MockTransport(handler), base_url="http://hook.test"
    )


def _railway_client(
    deployments: list, seen: Optional[list] = None
) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        query = payload.get("query", "")
        if seen is not None:
            seen.append(query)
        if "deployments" in query:
            return httpx.Response(
                200,
                json={
                    "data": {
                        "deployments": {
                            "edges": [
                                {"node": item} for item in deployments
                            ]
                        }
                    }
                },
            )
        if "deploymentRedeploy" in query:
            return httpx.Response(
                200,
                json={
                    "data": {
                        "deploymentRedeploy": {
                            "id": payload["variables"]["id"],
                            "status": "BUILDING",
                        }
                    }
                },
            )
        if "deploymentRestart" in query:
            return httpx.Response(200, json={"data": {"deploymentRestart": True}})
        if "me {" in query:
            return httpx.Response(
                200, json={"data": {"me": {"email": "ops@acme.test"}}}
            )
        return httpx.Response(200, json={"data": {}})

    return httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://backboard.railway.app",
    )


class AllowlistTests(unittest.TestCase):
    def setUp(self) -> None:
        mitigate.reset_mitigate_state()

    def test_stop_delete_scale_impossible(self) -> None:
        tmp = _tmp_data()
        _save_system(tmp)
        _save_webhook(tmp)
        with patch.dict(os.environ, {"TA_DATA_DIR": tmp}):
            for action in ("stop", "delete", "scale-0", "scale_0", "power_off", ""):
                result = mitigate.execute(
                    "acme", action, "run1", client=_hook_client()
                )
                self.assertEqual(result["status"], "refused")
                self.assertIn("not allowlisted", result["reason"])
            proposed = asyncio.run(
                mitigate.propose(
                    "acme", "run1", "stop", start_ticker=False
                )
            )
            self.assertEqual(proposed["status"], "refused")

    def test_option_id_parsing(self) -> None:
        self.assertEqual(
            mitigate.action_for_option_id("opt_rollback"), "rollback"
        )
        self.assertEqual(
            mitigate.action_for_option_id("opt_restart"), "restart"
        )
        self.assertEqual(
            mitigate.action_for_option_id("opt_open_pr"), "open_pr"
        )
        self.assertIsNone(mitigate.action_for_option_id("opt_stop"))
        self.assertIsNone(mitigate.action_for_option_id("bogus"))


class GateTests(unittest.TestCase):
    def setUp(self) -> None:
        mitigate.reset_mitigate_state()

    def test_gates_in_order(self) -> None:
        tmp = _tmp_data()
        _save_system(tmp)
        _save_webhook(tmp)
        with patch.dict(os.environ, {"TA_DATA_DIR": tmp}):
            ghost = mitigate.execute(
                "ghost", "rollback", "run1", client=_hook_client()
            )
            self.assertIn("unknown system", ghost["reason"])
            _save_system(tmp, "acme-learn", status="learning")
            learning = mitigate.execute(
                "acme-learn", "rollback", "run1", client=_hook_client()
            )
            self.assertIn("learning", learning["reason"])
            mitigate.set_paused(True)
            try:
                paused = mitigate.execute(
                    "acme", "rollback", "run1", client=_hook_client()
                )
                self.assertIn("paused", paused["reason"])
            finally:
                mitigate.set_paused(False)
            _save_system(tmp, "acme-bare")
            bare = mitigate.execute(
                "acme-bare", "rollback", "run1", client=_hook_client()
            )
            self.assertIn("no railway or webhook", bare["reason"])

    def test_propose_needs_policy(self) -> None:
        tmp = _tmp_data()
        _save_system(tmp, allowed=[])
        _save_webhook(tmp)
        with patch.dict(os.environ, {"TA_DATA_DIR": tmp}):
            refused = asyncio.run(
                mitigate.propose(
                    "acme", "run1", "rollback", start_ticker=False
                )
            )
            self.assertIn("policy", refused["reason"])

    def test_second_mitigation_within_10_min_refused(self) -> None:
        tmp = _tmp_data()
        _save_system(tmp)
        _save_webhook(tmp)
        with patch.dict(os.environ, {"TA_DATA_DIR": tmp}):
            first = mitigate.execute(
                "acme", "rollback", "run1", client=_hook_client()
            )
            self.assertEqual(first["status"], "done")
            second = mitigate.execute(
                "acme", "restart", "run2", client=_hook_client()
            )
            self.assertEqual(second["status"], "refused")
            self.assertIn("10 min", second["reason"])

    def test_failure_does_not_consume_budget(self) -> None:
        tmp = _tmp_data()
        _save_system(tmp)
        _save_webhook(tmp)
        with patch.dict(os.environ, {"TA_DATA_DIR": tmp}):
            failed = mitigate.execute(
                "acme", "rollback", "run1", client=_hook_client(500)
            )
            self.assertEqual(failed["status"], "failed")
            retry = mitigate.execute(
                "acme", "rollback", "run1", client=_hook_client()
            )
            self.assertEqual(retry["status"], "done")


class WebhookTests(unittest.TestCase):
    def test_fixture_signature_verifies(self) -> None:
        fixture = json.loads(
            (ROOT / "tests" / "fixtures" / "prod_webhook_hmac.json").read_text(
                encoding="utf-8"
            )
        )
        computed = mitigate.webhook_signature(
            fixture["secret"], fixture["body"].encode()
        )
        self.assertEqual(computed, fixture["signature"])

    def test_signed_headers_sent(self) -> None:
        seen: list = []
        result = mitigate.webhook_call(
            HOOK_URL,
            "whsec_test",
            {"action": "rollback", "ts": 1.0},
            _hook_client(seen=seen),
        )
        self.assertEqual(result["status"], "done")
        request = seen[0]
        signature = request.headers.get("X-Telemetry-Signature", "")
        self.assertTrue(signature.startswith("sha256="))
        self.assertEqual(
            signature,
            mitigate.webhook_signature("whsec_test", request.content),
        )

    def test_unreachable_webhook_fails(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("down")

        client = httpx.Client(
            transport=httpx.MockTransport(handler),
            base_url="http://hook.test",
        )
        result = mitigate.webhook_call(
            HOOK_URL, "s", {"action": "ping", "ts": 1.0}, client
        )
        self.assertEqual(result["status"], "failed")


class RailwayTests(unittest.TestCase):
    def test_rollback_redeploys_newest_success(self) -> None:
        seen: list = []
        deployments = [
            {"id": "d1", "status": "SUCCESS", "createdAt": "2026-01-01"},
            {"id": "d2", "status": "FAILED", "createdAt": "2026-01-02"},
            {"id": "d3", "status": "SUCCESS", "createdAt": "2026-01-03"},
        ]
        result = mitigate.railway_rollback(
            {"service_id": "svc1"},
            "tok",
            _railway_client(deployments, seen),
        )
        self.assertEqual(result["status"], "done")
        self.assertEqual(result["deployment_id"], "d3")
        self.assertTrue(any("deploymentRedeploy" in query for query in seen))

    def test_rollback_without_success_fails(self) -> None:
        deployments = [
            {"id": "d1", "status": "FAILED", "createdAt": "2026-01-01"}
        ]
        result = mitigate.railway_rollback(
            {"service_id": "svc1"}, "tok", _railway_client(deployments)
        )
        self.assertEqual(result["status"], "failed")
        self.assertIn("no successful deployment", result["detail"])

    def test_restart_targets_latest(self) -> None:
        deployments = [
            {"id": "d1", "status": "SUCCESS", "createdAt": "2026-01-01"},
            {"id": "d2", "status": "CRASHED", "createdAt": "2026-01-02"},
        ]
        result = mitigate.railway_restart(
            {"service_id": "svc1"}, "tok", _railway_client(deployments)
        )
        self.assertEqual(result["status"], "done")
        self.assertEqual(result["deployment_id"], "d2")

    def test_railway_errors_are_readable(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json={"errors": [{"message": "bad service id"}]}
            )

        client = httpx.Client(
            transport=httpx.MockTransport(handler),
            base_url="https://backboard.railway.app",
        )
        result = mitigate.railway_rollback({"service_id": "x"}, "tok", client)
        self.assertEqual(result["status"], "failed")
        self.assertIn("bad service id", result["detail"])
        checked = mitigate.railway_check("tok", client)
        self.assertFalse(checked["ok"])

    def test_railway_check_ok(self) -> None:
        checked = mitigate.railway_check("tok", _railway_client([]))
        self.assertTrue(checked["ok"])
        self.assertIn("ops@acme.test", checked["detail"])


class WindowTests(unittest.TestCase):
    def setUp(self) -> None:
        mitigate.reset_mitigate_state()

    def _env(self, tmp):
        return (
            patch.dict(os.environ, {"TA_DATA_DIR": tmp}),
            patch.object(api_main.hub, "broadcast", new=AsyncMock()),
        )

    def test_propose_approve_runs_adapter(self) -> None:
        tmp = _tmp_data()
        _save_system(tmp)
        _save_webhook(tmp)
        env, hub = self._env(tmp)
        with env, hub as broadcast:
            proposed = asyncio.run(
                mitigate.propose(
                    "acme", "run1", "rollback", start_ticker=False
                )
            )
            self.assertEqual(proposed["status"], "proposed")
            kinds = [
                call.args[0].kind for call in broadcast.await_args_list
            ]
            self.assertIn("action_pending", kinds)
            decided = asyncio.run(
                mitigate.decide(
                    "run1", True, "phone", client=_hook_client()
                )
            )
            self.assertEqual(decided["status"], "done")
            kinds = [
                call.args[0].kind for call in broadcast.await_args_list
            ]
            self.assertIn("action_resolved", kinds)

    def test_disapprove_cancels_without_running(self) -> None:
        tmp = _tmp_data()
        _save_system(tmp)
        _save_webhook(tmp)
        seen: list = []
        env, hub = self._env(tmp)
        with env, hub:
            asyncio.run(
                mitigate.propose(
                    "acme", "run1", "rollback", start_ticker=False
                )
            )
            decided = asyncio.run(
                mitigate.decide(
                    "run1", False, "phone",
                    client=_hook_client(seen=seen),
                )
            )
            self.assertEqual(decided["status"], "cancelled")
            self.assertEqual(seen, [])

    def test_expired_window_without_approval(self) -> None:
        tmp = _tmp_data()
        _save_system(tmp)
        _save_webhook(tmp)
        env, hub = self._env(tmp)
        with env, hub:
            asyncio.run(
                mitigate.propose(
                    "acme", "run1", "rollback", start_ticker=False
                )
            )
            mitigate._windows["run1"].deadline = 1.0  # force due
            settled = asyncio.run(mitigate.settle_due())
            self.assertEqual(settled[0]["status"], "expired")
            late = asyncio.run(mitigate.decide("run1", True, "phone"))
            self.assertIn("already", late["reason"])

    def test_paused_freezes_due_window(self) -> None:
        tmp = _tmp_data()
        _save_system(tmp)
        _save_webhook(tmp)
        env, hub = self._env(tmp)
        with env, hub:
            asyncio.run(
                mitigate.propose(
                    "acme", "run1", "rollback", start_ticker=False,
                    auto_apply=True,
                )
            )
            mitigate._windows["run1"].deadline = 1.0
            mitigate.set_paused(True)
            try:
                settled = asyncio.run(
                    mitigate.settle_due(client=_hook_client())
                )
            finally:
                mitigate.set_paused(False)
            self.assertEqual(settled[0]["status"], "expired")

    def test_audit_and_run_mitigation_recorded(self) -> None:
        tmp = _tmp_data()
        _save_system(tmp)
        _save_webhook(tmp)
        api_main.software_runs["run9"] = {
            "result": ExecutionResult(
                status="PASS", stdout="", stderr="", attempts=1,
                model_used="m", run_id="run9",
            )
        }
        try:
            with patch.dict(os.environ, {"TA_DATA_DIR": tmp}):
                result = mitigate.execute(
                    "acme", "restart", "run9",
                    decided_by="phone", client=_hook_client(),
                )
                self.assertEqual(result["status"], "done")
                with open(
                    os.path.join(tmp, "mitigations.json"),
                    encoding="utf-8",
                ) as handle:
                    state = json.loads(handle.read())
                self.assertEqual(state["log"][-1]["decided_by"], "phone")
                self.assertEqual(
                    state["log"][-1]["action"], "restart"
                )
                stored = api_main.software_runs["run9"]["result"]
                self.assertEqual(stored.mitigation.action, "restart")
                self.assertEqual(stored.mitigation.status, "done")
        finally:
            api_main.software_runs.pop("run9", None)


class OptionsTests(unittest.TestCase):
    def setUp(self) -> None:
        mitigate.reset_mitigate_state()

    def test_full_options_with_pr(self) -> None:
        tmp = _tmp_data()
        _save_system(tmp)
        _save_webhook(tmp)
        run = {
            "system_id": "acme",
            "run_id": "run1",
            "result": {"pr_url": "https://github.com/acme/api/pull/7"},
        }
        with patch.dict(os.environ, {"TA_DATA_DIR": tmp}):
            options = mitigate.software_options(run)
        by_kind = {option.kind: option for option in options}
        self.assertEqual(set(by_kind), {"open_pr", "rollback", "restart"})
        self.assertEqual(
            by_kind["open_pr"].url, "https://github.com/acme/api/pull/7"
        )
        self.assertTrue(by_kind["rollback"].safety.ok)
        self.assertIn("webhook", by_kind["rollback"].detail)

    def test_safety_gates(self) -> None:
        tmp = _tmp_data()
        _save_system(tmp)
        run = {"system_id": "acme", "result": {}}
        with patch.dict(os.environ, {"TA_DATA_DIR": tmp}):
            bare = mitigate.software_options(run)
            rollback = next(
                o for o in bare if o.kind == "rollback"
            )
            self.assertFalse(rollback.safety.ok)
            self.assertIn("no railway or webhook", rollback.safety.reason)
            self.assertEqual(
                {o.kind for o in bare}, {"rollback", "restart"}
            )
        _save_webhook(tmp)
        with patch.dict(os.environ, {"TA_DATA_DIR": tmp}):
            mitigate.set_paused(True)
            try:
                paused = mitigate.software_options(run)
                rollback = next(
                    o for o in paused if o.kind == "rollback"
                )
                self.assertFalse(rollback.safety.ok)
                self.assertIn("paused", rollback.safety.reason)
            finally:
                mitigate.set_paused(False)

    def test_appliance_run_has_no_software_options(self) -> None:
        self.assertEqual(
            mitigate.software_options({"domain": "appliance"}), []
        )


class PauseApiTests(unittest.TestCase):
    def test_round_trip_with_broadcast(self) -> None:
        tmp = _tmp_data()
        with patch.dict(
            os.environ, {"TA_DATA_DIR": tmp, "MOBILE_API_TOKEN": ""}
        ):
            with (
                TestClient(app) as client,
                patch.object(
                    api_main.hub, "broadcast", new=AsyncMock()
                ) as broadcast,
            ):
                state = client.get("/api/actions/pause")
                self.assertEqual(state.json(), {"paused": False})
                flipped = client.post(
                    "/api/actions/pause", json={"paused": True}
                )
                self.assertEqual(flipped.json(), {"paused": True})
                kinds = [
                    call.args[0].kind
                    for call in broadcast.await_args_list
                ]
                self.assertIn("actions_paused", kinds)
                event = next(
                    call.args[0]
                    for call in broadcast.await_args_list
                    if call.args[0].kind == "actions_paused"
                )
                self.assertEqual(event.payload, {"paused": True})
                back = client.post(
                    "/api/actions/pause", json={"paused": False}
                )
                self.assertEqual(back.json(), {"paused": False})

    def test_pause_needs_token_when_set(self) -> None:
        tmp = _tmp_data()
        with patch.dict(
            os.environ, {"TA_DATA_DIR": tmp, "MOBILE_API_TOKEN": "secret"}
        ):
            with TestClient(app) as client:
                denied = client.post(
                    "/api/actions/pause", json={"paused": True}
                )
                self.assertEqual(denied.status_code, 401)


class HostingTestEndpointTests(unittest.TestCase):
    def test_railway_and_webhook_tests(self) -> None:
        tmp = _tmp_data()
        with patch.dict(os.environ, {"TA_DATA_DIR": tmp}):
            setup_store.save_profile(
                SystemProfile(
                    system_id="acme", name="Acme", kind="software"
                )
            )
            railway, _ = connection_store.create_connection(
                "acme", "railway", {"service_id": "svc1"}, "tok"
            )
            webhook, _ = connection_store.create_connection(
                "acme", "webhook", {"url": HOOK_URL}, "sec"
            )
            with TestClient(app) as client:
                with (
                    patch.object(
                        mitigate, "railway_check",
                        return_value={
                            "ok": True, "detail": "token valid (x)"
                        },
                    ),
                    patch.object(
                        mitigate, "webhook_ping",
                        return_value={"ok": True, "detail": "pong"},
                    ),
                ):
                    tested = client.post(
                        f"/api/connections/{railway.id}/test"
                    )
                    self.assertTrue(tested.json()["ok"])
                    pinged = client.post(
                        f"/api/connections/{webhook.id}/test"
                    )
                    self.assertTrue(pinged.json()["ok"])
