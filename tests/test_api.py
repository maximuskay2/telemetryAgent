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


if __name__ == "__main__":
    unittest.main()
