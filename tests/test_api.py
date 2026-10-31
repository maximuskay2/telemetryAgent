import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from apps.api.main import app, infer_level


class InferLevelTests(unittest.TestCase):
    def test_classifies_known_severities(self) -> None:
        self.assertEqual(infer_level("fatal process crash"), "CRITICAL")
        self.assertEqual(infer_level("deadlock on row"), "WARNING")
        self.assertEqual(infer_level("request failed"), "ERROR")
        self.assertEqual(infer_level("connected"), "INFO")


class IngestionTests(unittest.TestCase):
    def test_posted_log_is_broadcast_to_websocket_clients(self) -> None:
        with TestClient(app) as client:
            with client.websocket_connect("/api/ws") as websocket:
                response = client.post(
                    "/api/logs",
                    json={"message": "database deadlock", "source": "test"},
                )
                self.assertEqual(response.status_code, 200)
                event = response.json()
                streamed_event = websocket.receive_json()

        self.assertEqual(event["message"], "database deadlock")
        self.assertEqual(event["level"], "WARNING")
        self.assertEqual(streamed_event["id"], event["id"])


class RunAgentTests(unittest.TestCase):
    def test_run_streams_steps_and_done_over_websocket(self) -> None:
        from core.schemas.diagnosis import Diagnosis
        from core.schemas.remediation import GeneratedPatch

        diag = Diagnosis(
            summary="Deadlock",
            likely_cause="Lock ordering inversion",
            suggested_actions=[],
            confidence=0.9,
        )
        patch_ = GeneratedPatch(patch_code="x = 1\n", test_code="def test_x(): assert True\n")
        with patch.dict(os.environ, {"BASETEN_API_KEY": "x", "GITHUB_TOKEN": ""}), \
                patch("core.agent.loop.meta_client.diagnose", return_value=diag), \
                patch("core.infer.baseten_client.generate_patch", return_value=patch_), \
                patch(
                    "core.agent.loop.verify_patch",
                    return_value={"passed": True, "feedback": "1 passed"},
                ):
            with TestClient(app) as client:
                with client.websocket_connect("/api/ws") as websocket:
                    response = client.post("/api/run", json={"log_text": "deadlock"})
                    self.assertEqual(response.status_code, 200)
                    steps = [websocket.receive_json() for _ in range(4)]

        self.assertEqual(
            [step["step"] for step in steps],
            ["diagnose", "generate", "verify", "done"],
        )
        self.assertEqual(steps[-1]["status"], "PASS")
        self.assertIn("duration_ms", steps[0])


class RunApplianceTests(unittest.TestCase):
    def test_appliance_run_streams_domain_tagged_steps(self) -> None:
        from core.schemas.diagnosis import Diagnosis
        from core.schemas.remediation import Runbook

        diag = Diagnosis(
            summary="Door left open",
            likely_cause="Worn gasket",
            suggested_actions=[],
            confidence=0.8,
        )
        runbook = Runbook(
            steps=["Close the door"],
            target_temperature_c=3.0,
            restart_delay_s=240,
            power_off_minutes=5.0,
            disables_protection=False,
        )
        with patch.dict(os.environ, {"BASETEN_API_KEY": "x"}), \
                patch("core.agent.loop.meta_client.diagnose", return_value=diag), \
                patch(
                    "core.infer.baseten_client.generate_runbook",
                    return_value=runbook,
                ):
            with TestClient(app) as client:
                with client.websocket_connect("/api/ws") as websocket:
                    response = client.post(
                        "/api/run/appliance",
                        json={"appliance_type": "fridge", "fault": "door_open"},
                    )
                    self.assertEqual(response.status_code, 200)
                    steps = [websocket.receive_json() for _ in range(4)]

        body = response.json()
        self.assertEqual(body["status"], "PASS")
        self.assertIsNotNone(body["alert"])
        self.assertEqual(body["alert"]["channel"], "sms-stub")
        self.assertEqual(
            [step["step"] for step in steps],
            ["diagnose", "generate", "verify", "done"],
        )
        for step in steps:
            self.assertEqual(step["domain"], "appliance")
            self.assertEqual(step["run_id"], body["run_id"])
        self.assertIn("wo-", steps[-1]["message"])


class CorsTests(unittest.TestCase):
    def test_dashboard_origins_allowed(self) -> None:
        with TestClient(app) as client:
            for origin in (
                "http://localhost:3000",
                "http://127.0.0.1:3000",
                "http://192.168.1.97:3000",
            ):
                response = client.get("/api/health", headers={"Origin": origin})
                self.assertEqual(
                    response.headers.get("access-control-allow-origin"), origin
                )

    def test_foreign_origin_rejected(self) -> None:
        with TestClient(app) as client:
            response = client.get(
                "/api/health", headers={"Origin": "http://evil.example"}
            )
        self.assertNotIn("access-control-allow-origin", response.headers)

    def test_cors_regex_override_for_deploys(self) -> None:
        from apps.api.main import cors_origin_regex

        with patch.dict(
            os.environ, {"CORS_ORIGIN_REGEX": r"https://.*\.up\.railway\.app$"}
        ):
            self.assertEqual(
                cors_origin_regex(), r"https://.*\.up\.railway\.app$"
            )
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CORS_ORIGIN_REGEX", None)
            self.assertIn("localhost", cors_origin_regex())

    def test_preflight_allows_put_and_delete(self) -> None:
        with TestClient(app) as client:
            for method in ("PUT", "DELETE"):
                response = client.options(
                    "/api/systems/x/profile",
                    headers={
                        "Origin": "http://localhost:3000",
                        "Access-Control-Request-Method": method,
                        "Access-Control-Request-Headers": "Content-Type",
                    },
                )
                self.assertEqual(response.status_code, 200, method)
                self.assertIn(
                    "access-control-allow-origin", response.headers
                )


class PairingTests(unittest.TestCase):
    def test_pairing_returns_lan_url(self) -> None:
        with TestClient(app) as client:
            response = client.get("/api/pairing")
        self.assertEqual(response.status_code, 200)
        api_url = response.json()["api_url"]
        self.assertRegex(api_url, r"^http://[\d.]+:\d+$")

    def test_pairing_ignores_stray_port_env(self) -> None:
        with patch.dict(os.environ, {"PORT": "8000"}):
            with TestClient(
                app, base_url="http://testserver:8001"
            ) as client:
                response = client.get("/api/pairing")
        self.assertEqual(response.status_code, 200)
        self.assertRegex(
            response.json()["api_url"], r"^http://[\d.]+:8001$"
        )

    def test_pairing_prefers_public_url_env(self) -> None:
        with patch.dict(
            os.environ, {"API_PUBLIC_URL": "https://api.example.com/"}
        ):
            with TestClient(app) as client:
                response = client.get("/api/pairing")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["api_url"], "https://api.example.com"
        )

    def test_pairing_uses_public_host_header(self) -> None:
        with TestClient(app) as client:
            response = client.get(
                "/api/pairing",
                headers={
                    "host": "api-production-0c9a.up.railway.app",
                    "x-forwarded-proto": "https",
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["api_url"],
            "https://api-production-0c9a.up.railway.app",
        )

    def test_pairing_keeps_lan_url_for_localhost(self) -> None:
        with TestClient(app) as client:
            response = client.get(
                "/api/pairing", headers={"host": "localhost:8001"}
            )
        self.assertEqual(response.status_code, 200)
        self.assertRegex(
            response.json()["api_url"], r"^http://[\d.]+:\d+$"
        )


class RunFailureTests(unittest.TestCase):
    def test_run_without_keys_returns_503(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with TestClient(app) as client:
                response = client.post("/api/run", json={"log_text": "deadlock"})
        self.assertEqual(response.status_code, 503)
        self.assertIn("MODEL_API_KEY", response.json()["detail"])

    def test_appliance_run_without_keys_returns_503(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with TestClient(app) as client:
                response = client.post(
                    "/api/run/appliance",
                    json={"appliance_type": "fridge", "fault": "door_open"},
                )
        self.assertEqual(response.status_code, 503)
        self.assertIn("MODEL_API_KEY", response.json()["detail"])

    def test_oversize_log_rejected_with_422(self) -> None:
        with TestClient(app) as client:
            response = client.post("/api/run", json={"log_text": "x" * 20001})
        self.assertEqual(response.status_code, 422)

    def test_oversize_diagnose_rejected_with_422(self) -> None:
        with TestClient(app) as client:
            response = client.post("/api/diagnose", json={"log_text": "x" * 20001})
        self.assertEqual(response.status_code, 422)

    def test_invalid_fault_rejected_with_422(self) -> None:
        with TestClient(app) as client:
            response = client.post(
                "/api/run/appliance",
                json={"appliance_type": "fridge", "fault": "explosion"},
            )
        self.assertEqual(response.status_code, 422)

    def test_target_outside_allowlist_rejected_with_400(self) -> None:
        with TestClient(app) as client:
            response = client.post(
                "/api/run",
                json={"log_text": "deadlock", "target_path": "../../README.md"},
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn("allowlisted", response.json()["detail"])

    def test_missing_target_rejected_with_400(self) -> None:
        with TestClient(app) as client:
            response = client.post(
                "/api/run",
                json={"log_text": "deadlock", "target_path": "nope.py"},
            )
        self.assertEqual(response.status_code, 400)

    def test_target_file_flows_to_fail_to_pass_check(self) -> None:
        from core.schemas.diagnosis import Diagnosis
        from core.schemas.remediation import GeneratedPatch
        from core.verify.targets import read_target_file

        diag = Diagnosis(
            summary="Deadlock",
            likely_cause="Lock ordering inversion",
            suggested_actions=[],
            confidence=0.9,
        )
        patch_ = GeneratedPatch(patch_code="x = 1\n", test_code="def test_x(): assert True\n")
        with patch.dict(os.environ, {"BASETEN_API_KEY": "x", "GITHUB_TOKEN": ""}), \
                patch("core.agent.loop.meta_client.diagnose", return_value=diag), \
                patch("core.infer.baseten_client.generate_patch", return_value=patch_), \
                patch(
                    "core.agent.loop.verify_fix",
                    return_value={"passed": True, "feedback": "1 passed"},
                ) as fix:
            with TestClient(app) as client:
                response = client.post(
                    "/api/run",
                    json={
                        "log_text": "deadlock",
                        "target_path": "inventory.py",
                        "source": "watcher",
                    },
                )
        self.assertEqual(response.status_code, 200)
        expected = read_target_file("inventory.py")
        fix.assert_called_once_with(expected, "x = 1\n", "def test_x(): assert True\n")

    def test_source_tag_reaches_stream_events(self) -> None:
        from core.schemas.diagnosis import Diagnosis
        from core.schemas.remediation import GeneratedPatch

        diag = Diagnosis(
            summary="Deadlock",
            likely_cause="Lock ordering inversion",
            suggested_actions=["Check lock order"],
            confidence=0.9,
        )
        patch_ = GeneratedPatch(patch_code="x = 1\n", test_code="def test_x(): assert True\n")
        with patch.dict(os.environ, {"BASETEN_API_KEY": "x", "GITHUB_TOKEN": ""}), \
                patch("core.agent.loop.meta_client.diagnose", return_value=diag), \
                patch("core.infer.baseten_client.generate_patch", return_value=patch_), \
                patch(
                    "core.agent.loop.verify_patch",
                    return_value={"passed": True, "feedback": "1 passed"},
                ):
            with TestClient(app) as client:
                with client.websocket_connect("/api/ws") as websocket:
                    response = client.post(
                        "/api/run",
                        json={"log_text": "deadlock", "source": "watcher"},
                    )
                    self.assertEqual(response.status_code, 200)
                    steps = [websocket.receive_json() for _ in range(4)]
        for step in steps:
            self.assertEqual(step["source"], "watcher")
        self.assertEqual(steps[0]["suggestions"], ["Check lock order"])

    def test_invalid_source_rejected_with_422(self) -> None:
        with TestClient(app) as client:
            response = client.post(
                "/api/run", json={"log_text": "deadlock", "source": "pigeon"}
            )
        self.assertEqual(response.status_code, 422)

    def test_empty_log_rejected_with_422(self) -> None:
        with TestClient(app) as client:
            response = client.post("/api/run", json={"log_text": ""})
        self.assertEqual(response.status_code, 422)


class SampleTests(unittest.TestCase):
    def test_deadlock_sample_matches_file(self) -> None:
        from pathlib import Path as FilePath

        with TestClient(app) as client:
            response = client.get("/api/samples/deadlock")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["name"], "database_deadlock.log")
        expected = (
            FilePath(__file__).resolve().parent.parent
            / "samples"
            / "database_deadlock.log"
        ).read_text(encoding="utf-8")
        self.assertEqual(body["log_text"], expected)
        self.assertIn("Deadlock detected", body["log_text"])


class SimZeroTests(unittest.TestCase):
    def test_default_source_is_manual(self) -> None:
        from core.schemas.remediation import ApplianceRunRequest, RunRequest

        self.assertEqual(RunRequest(log_text="x").source, "manual")
        self.assertEqual(ApplianceRunRequest().source, "manual")

    def test_unknown_target_rejected_with_422(self) -> None:
        with TestClient(app) as client:
            response = client.post(
                "/api/run", json={"log_text": "x", "target": "payments"}
            )
        self.assertEqual(response.status_code, 422)

    def test_inventory_target_uses_real_file_and_pr_paths(self) -> None:
        from core.schemas.diagnosis import Diagnosis
        from core.schemas.remediation import GeneratedPatch
        from core.verify.targets import read_target_file

        diag = Diagnosis(
            summary="Deadlock",
            likely_cause="Lock ordering inversion",
            suggested_actions=[],
            confidence=0.9,
        )
        patch_ = GeneratedPatch(patch_code="x = 1\n", test_code="def test_x(): assert True\n")
        env = {
            "BASETEN_API_KEY": "x",
            "GITHUB_TOKEN": "t",
            "GITHUB_DEMO_REPO": "o/r",
        }
        with patch.dict(os.environ, env), \
                patch("core.agent.loop.meta_client.diagnose", return_value=diag), \
                patch("core.infer.baseten_client.generate_patch", return_value=patch_), \
                patch(
                    "core.agent.loop.verify_patch",
                    return_value={"passed": True, "feedback": "harness ok"},
                ), \
                patch(
                    "core.agent.loop.verify_fix",
                    return_value={"passed": True, "feedback": "1 passed"},
                ) as fix, \
                patch(
                    "core.actions.github_pr.open_fix_pr",
                    return_value="https://github.com/o/r/pull/1",
                ) as pr:
            with TestClient(app) as client:
                response = client.post(
                    "/api/run", json={"log_text": "deadlock", "target": "inventory"}
                )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["pr_url"], "https://github.com/o/r/pull/1"
        )
        fix.assert_called_once_with(
            read_target_file("inventory.py"), "x = 1\n", "def test_x(): assert True\n"
        )
        _, kwargs = pr.call_args
        self.assertEqual(kwargs["code_path"], "inventory.py")
        self.assertEqual(kwargs["test_path"], "test_inventory_regression.py")

    def test_readings_endpoint_runs_appliance_loop(self) -> None:
        from core.schemas.diagnosis import Diagnosis
        from core.schemas.remediation import Runbook

        diag = Diagnosis(
            summary="Door left open",
            likely_cause="Worn gasket",
            suggested_actions=[],
            confidence=0.8,
        )
        runbook = Runbook(
            steps=["Close the door"],
            target_temperature_c=3.0,
            restart_delay_s=240,
            power_off_minutes=5.0,
            disables_protection=False,
        )
        body = {
            "domain": "appliance",
            "source_id": "fridge-01",
            "appliance_type": "fridge",
            "readings": [
                {"ts": 1.0, "temperature_c": 8.0, "current_a": 1.0,
                 "vibration_g": 0.01, "door_open": True}
            ],
        }
        with patch.dict(os.environ, {"BASETEN_API_KEY": "x"}), \
                patch("core.agent.loop.meta_client.diagnose", return_value=diag), \
                patch(
                    "core.infer.baseten_client.generate_runbook",
                    return_value=runbook,
                ):
            with TestClient(app) as client:
                with client.websocket_connect("/api/ws") as websocket:
                    response = client.post(
                        "/api/run/appliance/readings?source=watcher", json=body
                    )
                    self.assertEqual(response.status_code, 200)
                    steps = [websocket.receive_json() for _ in range(4)]
        self.assertEqual(response.json()["status"], "PASS")
        for step in steps:
            self.assertEqual(step["domain"], "appliance")
            self.assertEqual(step["source"], "watcher")

    def test_sim_event_broadcast_to_websocket(self) -> None:
        with TestClient(app) as client:
            with client.websocket_connect("/api/ws") as websocket:
                response = client.post(
                    "/api/sim/events",
                    json={"kind": "shop_metrics", "payload": {"error_rate": 0.5}},
                )
                self.assertEqual(response.status_code, 200)
                received = websocket.receive_json()
        self.assertEqual(received["kind"], "shop_metrics")
        self.assertEqual(received["payload"], {"error_rate": 0.5})

    def test_sim_event_invalid_kind_rejected_with_422(self) -> None:
        with TestClient(app) as client:
            response = client.post("/api/sim/events", json={"kind": "nope"})
        self.assertEqual(response.status_code, 422)


class RunVerificationTests(unittest.TestCase):
    def test_pass_run_exposes_verification_object(self) -> None:
        from core.schemas.diagnosis import Diagnosis
        from core.schemas.remediation import GeneratedPatch
        from core.verify.targets import read_target_file

        diag = Diagnosis(
            summary="Deadlock",
            likely_cause="Lock ordering inversion",
            suggested_actions=[],
            confidence=0.9,
        )
        patch_ = GeneratedPatch(
            patch_code="x = 1\n",
            test_code="def test_x(): assert True\n",
        )
        with patch.dict(os.environ, {"BASETEN_API_KEY": "x", "GITHUB_TOKEN": ""}), \
                patch("core.agent.loop.meta_client.diagnose", return_value=diag), \
                patch("core.infer.baseten_client.generate_patch", return_value=patch_), \
                patch(
                    "core.agent.loop.verify_patch",
                    return_value={"passed": True, "feedback": "harness ok"},
                ), \
                patch(
                    "core.agent.loop.verify_fix",
                    return_value={"passed": True, "feedback": "1 passed"},
                ):
            with TestClient(app) as client:
                response = client.post(
                    "/api/run",
                    json={"log_text": "deadlock", "target": "inventory"},
                )
                self.assertEqual(response.status_code, 200)
                run_id = response.json()["run_id"]
                fetched = client.get(f"/api/runs/{run_id}")
        self.assertEqual(fetched.status_code, 200)
        body = fetched.json()
        for key in ("run_id", "domain", "result", "steps", "decision", "gate"):
            self.assertIn(key, body)
        verification = body["verification"]
        self.assertEqual(verification["target"], "inventory")
        self.assertEqual(
            verification["original_code"], read_target_file("inventory.py")
        )
        self.assertEqual(
            verification["test_code"], "def test_x(): assert True\n"
        )
        # The mocked verifier returns no per-side outputs; the shape holds.
        self.assertIsNone(verification["original"])
        self.assertIsNone(verification["patched"])
        self.assertIsNone(verification["runner"])

    def test_run_without_verification_still_reads(self) -> None:
        from apps.api.main import software_runs
        from core.schemas.remediation import ExecutionResult

        software_runs["old-1"] = {
            "target": None,
            "result": ExecutionResult(
                status="PASS", stdout="x", stderr="",
                attempts=1, model_used="m",
            ),
        }
        try:
            with TestClient(app) as client:
                fetched = client.get("/api/runs/old-1")
        finally:
            software_runs.pop("old-1", None)
        self.assertEqual(fetched.status_code, 200)
        self.assertIsNone(fetched.json()["verification"])
        self.assertEqual(fetched.json()["result"]["status"], "PASS")


class SystemLifecycleTests(unittest.TestCase):
    def test_disarm_returns_armed_to_confirmed(self) -> None:
        import tempfile

        from core.setup import store as setup_store

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"TA_DATA_DIR": tmp}):
                created = self._make_system("shop")
                with TestClient(app) as client:
                    armed = client.post(f"/api/systems/{created}/arm")
                    self.assertEqual(armed.status_code, 200)
                    self.assertEqual(armed.json()["status"], "armed")
                    disarmed = client.post(
                        f"/api/systems/{created}/disarm"
                    )
                    self.assertEqual(disarmed.status_code, 200)
                    self.assertEqual(disarmed.json()["status"], "confirmed")
                    profile = setup_store.get_profile(created)
                    assert profile is not None
                    self.assertEqual(profile.status, "confirmed")

    def test_disarm_rejects_unknown_and_non_armed(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"TA_DATA_DIR": tmp}):
                created = self._make_system("shop")
                with TestClient(app) as client:
                    missing = client.post("/api/systems/nope/disarm")
                    self.assertEqual(missing.status_code, 404)
                    # Confirmed (but not armed) systems conflict.
                    conflict = client.post(f"/api/systems/{created}/disarm")
                    self.assertEqual(conflict.status_code, 409)

    def test_delete_removes_system_and_files(self) -> None:
        import tempfile

        from core.setup import store as setup_store

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"TA_DATA_DIR": tmp}):
                created = self._make_system("shop")
                self.assertTrue(
                    setup_store.profile_path(created).exists()
                )
                with TestClient(app) as client:
                    deleted = client.delete(f"/api/systems/{created}")
                    self.assertEqual(deleted.status_code, 200)
                    self.assertEqual(
                        deleted.json(), {"deleted": created}
                    )
                    again = client.delete(f"/api/systems/{created}")
                    self.assertEqual(again.status_code, 404)
                    missing = client.get(
                        f"/api/systems/{created}/profile"
                    )
                    self.assertEqual(missing.status_code, 404)
                self.assertFalse(
                    setup_store.profile_path(created).exists()
                )

    def test_delete_rejects_traversal_ids(self) -> None:
        import tempfile

        from core.setup import store as setup_store

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"TA_DATA_DIR": tmp}):
                self.assertFalse(setup_store.delete_system("../x"))
                self.assertFalse(setup_store.delete_system("a/b"))
                self.assertFalse(setup_store.delete_system("*.json"))

    def _make_system(self, sample: str) -> str:
        with TestClient(app) as client:
            created = client.post(
                "/api/systems",
                json={"name": "lifecycle-probe", "kind": "software"},
            )
            self.assertEqual(created.status_code, 200)
            system_id = created.json()["system_id"]
            sampled = client.post(
                f"/api/systems/{system_id}/profile/sample",
                json={"sample": sample},
            )
            self.assertEqual(sampled.status_code, 200)
            confirmed = client.post(
                f"/api/systems/{system_id}/profile/confirm",
                json={"confirmed_by": "test", "resolve": []},
            )
            self.assertEqual(confirmed.status_code, 200)
            return system_id


class DemoBootstrapTests(unittest.TestCase):
    def test_bootstrap_is_idempotent_and_leaves_user_systems_alone(
        self,
    ) -> None:
        import tempfile

        from core.setup import store as setup_store

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"TA_DATA_DIR": tmp}):
                with TestClient(app) as client:
                    mine = client.post(
                        "/api/systems",
                        json={"name": "my shop", "kind": "software"},
                    )
                    self.assertEqual(mine.status_code, 200)
                    first = None
                    for _ in range(5):
                        boot = client.post("/api/demo/bootstrap")
                        self.assertEqual(boot.status_code, 200)
                        body = boot.json()
                        if first is None:
                            first = body
                        self.assertEqual(
                            body["shop"]["system_id"],
                            first["shop"]["system_id"],
                        )
                        self.assertEqual(
                            body["freezer"]["system_id"],
                            first["freezer"]["system_id"],
                        )
                    assert first is not None
                    self.assertEqual(
                        first["shop"]["environment"], {"demo": "true"}
                    )
                    self.assertEqual(
                        first["freezer"]["environment"], {"demo": "true"}
                    )
                    systems = client.get("/api/systems").json()["systems"]
                    demos = [
                        s
                        for s in systems
                        if s.get("environment", {}).get("demo") == "true"
                    ]
                    self.assertEqual(len(demos), 2)
                    self.assertEqual(len(systems), 3)
                    names = sorted(s["name"] for s in demos)
                    self.assertEqual(
                        names, ["AutoParts Lagos", "Cold-chain Freezer"]
                    )
                    status = client.get("/api/demo/status")
                    self.assertEqual(status.status_code, 200)
                    payload = status.json()
                    self.assertEqual(
                        payload["shop"]["system_id"],
                        first["shop"]["system_id"],
                    )
                    self.assertEqual(payload["shop"]["status"], "draft")
                    self.assertFalse(
                        payload["shop"]["auto_fix_allowed"]
                    )
                    self.assertIsNotNone(payload["freezer"])
                    self.assertIn("scenario_playing", payload)
                    self.assertIn("last_run_id", payload)
                    self.assertIn("pr_url", payload)
                    mine_id = mine.json()["system_id"]
                    kept = setup_store.get_profile(mine_id)
                    assert kept is not None
                    self.assertEqual(kept.name, "my shop")
                    self.assertNotEqual(
                        kept.environment.get("demo"), "true"
                    )


class DemoStaysOpenWhenHostedTests(unittest.TestCase):
    def test_demo_start_watching_without_signin(self) -> None:
        """Hosted Postgres must not gate the public demo walkthrough."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(
                "os.environ",
                {
                    "TA_DATA_DIR": tmp,
                    "DATABASE_URL": "postgresql://hosted.example/telemetry",
                },
            ), patch("core.commerce.db.ensure_schema"):
                with TestClient(app) as client:
                    own = client.post(
                        "/api/systems",
                        json={"name": "mine", "kind": "software"},
                    )
                    self.assertEqual(own.status_code, 401)
                    self.assertEqual(
                        own.json()["detail"], "sign-in required"
                    )
                    boot = client.post("/api/demo/bootstrap")
                    self.assertEqual(boot.status_code, 200)
                    shop_id = boot.json()["shop"]["system_id"]
                    sample = client.post(
                        f"/api/systems/{shop_id}/profile/sample",
                        json={"sample": "shop"},
                    )
                    self.assertEqual(sample.status_code, 200)
                    watching = client.post(
                        f"/api/demo/{shop_id}/start-watching"
                    )
                    self.assertEqual(
                        watching.status_code, 200, watching.text
                    )
                    self.assertEqual(watching.json()["status"], "armed")
                    profile = client.get(f"/api/demo/{shop_id}/profile")
                    self.assertEqual(profile.status_code, 200)
                    self.assertEqual(
                        profile.json()["profile"]["status"], "armed"
                    )


class DemoDocumentsTests(unittest.TestCase):
    def test_failed_extraction_falls_back_to_saved_reading(self) -> None:
        import tempfile

        import core.setup.extract as setup_extract
        from core.setup import store as setup_store

        def _boom(*args, **kwargs):
            raise RuntimeError("Set MODEL_API_KEY to use the Meta Model API.")

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"TA_DATA_DIR": tmp}):
                with TestClient(app) as client:
                    boot = client.post("/api/demo/bootstrap").json()
                    with patch.object(
                        setup_extract, "default_model_fn", _boom
                    ):
                        for key in ("shop", "freezer"):
                            resp = client.post(
                                f"/api/demo/{boot[key]['system_id']}"
                                "/documents"
                            )
                            self.assertEqual(resp.status_code, 200)
                            body = resp.json()
                            self.assertTrue(body["fallback"])
                            profile = body["profile"]
                            self.assertTrue(profile["normal_ranges"])
                            self.assertTrue(profile["hard_limits"])
                            kept = setup_store.get_profile(
                                profile["system_id"]
                            )
                            assert kept is not None
                            self.assertEqual(
                                kept.environment.get("demo"), "true"
                            )

    def test_successful_extraction_keeps_demo_identity(self) -> None:
        import tempfile

        import core.setup.extract as setup_extract

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"TA_DATA_DIR": tmp}):
                with TestClient(app) as client:
                    # The freezer keeps the live path; the shop is
                    # fallback-only (see demo_documents).
                    shop = client.post("/api/demo/bootstrap").json()["freezer"]
                    renamed = {
                        "name": "Renamed By Manual",
                        "environment": {},
                    }
                    with patch.object(
                        setup_extract,
                        "fill_profile_from_text",
                        return_value=renamed,
                    ):
                        with patch.object(
                            setup_extract,
                            "merge_partials",
                            return_value=(renamed, []),
                        ):
                            resp = client.post(
                                f"/api/demo/{shop['system_id']}/documents"
                            )
                    self.assertEqual(resp.status_code, 200)
                    body = resp.json()
                    self.assertFalse(body["fallback"])
                    self.assertEqual(
                        body["profile"]["name"], "Cold-chain Freezer"
                    )
                    self.assertEqual(
                        body["profile"]["environment"], {"demo": "true"}
                    )

    def test_shop_documents_uses_saved_reading_without_extracting(
        self,
    ) -> None:
        import tempfile

        import core.setup.extract as setup_extract

        def _must_not_run(*args, **kwargs):
            raise AssertionError("extraction must not run for the shop")

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"TA_DATA_DIR": tmp}):
                with TestClient(app) as client:
                    shop = client.post("/api/demo/bootstrap").json()["shop"]
                    with patch.object(
                        setup_extract, "fill_profile_from_text", _must_not_run
                    ):
                        resp = client.post(
                            f"/api/demo/{shop['system_id']}/documents"
                        )
                    self.assertEqual(resp.status_code, 200)
                    body = resp.json()
                    self.assertTrue(body["fallback"])
                    self.assertTrue(body["profile"]["hard_limits"])

    def test_demo_documents_rejects_non_demo_systems(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"TA_DATA_DIR": tmp}):
                with TestClient(app) as client:
                    mine = client.post(
                        "/api/systems",
                        json={"name": "mine", "kind": "software"},
                    )
                    resp = client.post(
                        f"/api/demo/{mine.json()['system_id']}/documents"
                    )
                    self.assertEqual(resp.status_code, 404)
                    missing = client.post("/api/demo/nope/documents")
                    self.assertEqual(missing.status_code, 404)


class DemoLearnTests(unittest.TestCase):
    def test_defrost_hump_sits_mid_window(self) -> None:
        from apps.api.main import _demo_freezer_round

        temp, _current, mode = _demo_freezer_round(0.5, 10)
        self.assertEqual(mode, "defrost")
        self.assertGreater(temp, 5.0)
        for frac in (0.0, 0.2, 0.39, 0.66, 0.9):
            _temp, _current, mode = _demo_freezer_round(frac, 1)
            self.assertEqual(mode, "")

    def test_shop_learn_teaches_patterns_and_starts_no_runs(self) -> None:
        import tempfile
        import time

        from apps.api.main import appliance_runs, software_runs

        runs_before = len(software_runs) + len(appliance_runs)
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"TA_DATA_DIR": tmp}):
                with TestClient(app) as client:
                    shop = client.post("/api/demo/bootstrap").json()["shop"]
                    sid = shop["system_id"]
                    started = client.post(
                        f"/api/demo/{sid}/learn",
                        json={"duration_s": 12},
                    )
                    self.assertEqual(started.status_code, 200)
                    self.assertEqual(
                        started.json()["driver"], "demo-gentle"
                    )
                    baseline = {}
                    for _ in range(60):
                        time.sleep(0.5)
                        baseline = client.get(
                            f"/api/systems/{sid}/baseline"
                        ).json()
                        if baseline["status"] != "learning":
                            break
                    self.assertNotEqual(baseline["status"], "learning")
                    compiled = baseline["baseline"]
                    self.assertGreaterEqual(
                        len(compiled["log_templates"]), 2
                    )
                    self.assertEqual(
                        sorted(compiled["metric_bands"]),
                        ["error_rate", "orders_per_min", "p95_ms"],
                    )
        self.assertEqual(
            len(software_runs) + len(appliance_runs), runs_before
        )

    def test_demo_learn_rejects_non_demo_systems(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"TA_DATA_DIR": tmp}):
                with TestClient(app) as client:
                    mine = client.post(
                        "/api/systems",
                        json={"name": "mine", "kind": "software"},
                    )
                    resp = client.post(
                        f"/api/demo/{mine.json()['system_id']}/learn",
                        json={},
                    )
                    self.assertEqual(resp.status_code, 404)


class DemoCandidateTests(unittest.TestCase):
    def test_storm_candidate_acts_on_ambient_error_rate(self) -> None:
        import tempfile
        from types import SimpleNamespace
        from unittest.mock import AsyncMock

        from apps.api.main import software_runs

        async def fake_run(request):
            software_runs["enrich-test"] = {
                "target": "inventory",
                "result": None,
            }
            return SimpleNamespace(status="fixed")

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"TA_DATA_DIR": tmp}):
                with TestClient(app) as client:
                    shop = client.post("/api/demo/bootstrap").json()["shop"]
                    sid = shop["system_id"]
                    sampled = client.post(
                        f"/api/systems/{sid}/profile/sample",
                        json={"sample": "shop"},
                    )
                    self.assertEqual(sampled.status_code, 200)
                    confirmed = client.post(
                        f"/api/systems/{sid}/profile/confirm",
                        json={"confirmed_by": "test", "resolve": []},
                    )
                    self.assertEqual(confirmed.status_code, 200)
                    armed = client.post(f"/api/systems/{sid}/arm")
                    self.assertEqual(armed.status_code, 200)
                    metrics = client.post(
                        "/api/sim/events",
                        json={
                            "kind": "shop_metrics",
                            "payload": {"error_rate": 0.9},
                        },
                    )
                    self.assertEqual(metrics.status_code, 200)
                    with patch(
                        "apps.api.main.run_agent",
                        new=AsyncMock(side_effect=fake_run),
                    ):
                        response = client.post(
                            "/api/incidents/candidate",
                            json={
                                "system_id": sid,
                                "rule": "error",
                                "fingerprint": "deadlock-1",
                                "signature": "Deadlock detected",
                                "window": "WARNING retry=1\nDeadlock",
                            },
                        )
                    try:
                        self.assertEqual(response.status_code, 200)
                        body = response.json()
                        self.assertEqual(
                            body["decision"]["decision"], "act"
                        )
                        self.assertEqual(body["run_id"], "enrich-test")
                    finally:
                        software_runs.pop("enrich-test", None)

    def test_watcher_default_shop_id_reaches_the_demo_shop(self) -> None:
        import tempfile
        from types import SimpleNamespace
        from unittest.mock import AsyncMock

        from apps.api.main import software_runs

        async def fake_run(request):
            software_runs["alias-test"] = {
                "target": "inventory",
                "result": None,
            }
            return SimpleNamespace(status="fixed")

        candidate = {
            "system_id": "shop",
            "rule": "error",
            "fingerprint": "deadlock-alias",
            "signature": "Deadlock detected",
            "window": "WARNING retry=1\nDeadlock",
        }
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"TA_DATA_DIR": tmp}):
                with TestClient(app) as client:
                    before = client.post(
                        "/api/incidents/candidate", json=candidate
                    ).json()
                    self.assertEqual(
                        before["decision"]["decision"], "observe"
                    )
                    sid = client.post("/api/demo/bootstrap").json()[
                        "shop"
                    ]["system_id"]
                    self.assertNotEqual(sid, "shop")
                    client.post(
                        f"/api/systems/{sid}/profile/sample",
                        json={"sample": "shop"},
                    )
                    client.post(
                        f"/api/systems/{sid}/profile/confirm",
                        json={"confirmed_by": "test", "resolve": []},
                    )
                    self.assertEqual(
                        client.post(f"/api/systems/{sid}/arm").status_code,
                        200,
                    )
                    client.post(
                        "/api/sim/events",
                        json={
                            "kind": "shop_metrics",
                            "payload": {"error_rate": 0.9},
                        },
                    )
                    with patch(
                        "apps.api.main.run_agent",
                        new=AsyncMock(side_effect=fake_run),
                    ):
                        response = client.post(
                            "/api/incidents/candidate", json=candidate
                        )
                    try:
                        body = response.json()
                        self.assertEqual(
                            body["decision"]["decision"], "act"
                        )
                        self.assertEqual(
                            body["decision"]["system_id"], sid
                        )
                    finally:
                        software_runs.pop("alias-test", None)


if __name__ == "__main__":
    unittest.main()
