"""Scenario/load/reset endpoint tests (Sim 6)."""

import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from apps.api.main import app, appliance_runs, fridge, shop_runtime_path, software_runs
from core.schemas.remediation import ApplianceResult, ExecutionResult


def _ok_reload(url, json=None, timeout=None):
    return httpx.Response(200, json={"inventory": json["inventory_path"]})


class ScenarioApiTest(unittest.TestCase):
    def tearDown(self) -> None:
        with TestClient(app) as client:
            with patch("httpx.post", side_effect=_ok_reload):
                client.post("/api/sim/reset")

    def test_shop_load_spawns_and_validates(self) -> None:
        with TestClient(app) as client:
            good = client.post(
                "/api/sim/shop/load",
                json={"shoppers": 1, "rate": 1, "duration": 1},
            )
            self.assertEqual(good.status_code, 200)
            self.assertIsInstance(good.json()["pid"], int)
            bad = client.post(
                "/api/sim/shop/load",
                json={"shoppers": 0, "rate": 1, "duration": 1},
            )
            self.assertEqual(bad.status_code, 422)

    def test_play_status_and_double_play_rejected(self) -> None:
        with TestClient(app) as client:
            play = client.post("/api/sim/scenario/play")
            self.assertEqual(play.status_code, 200)
            self.assertGreaterEqual(play.json()["steps"], 2)
            status = client.get("/api/sim/scenario/status").json()
            self.assertTrue(status["playing"])
            again = client.post("/api/sim/scenario/play")
            self.assertEqual(again.status_code, 409)

    def test_reset_clears_world(self) -> None:
        software_runs["x"] = {"target": None, "result": ExecutionResult(
            status="FAIL", stdout="", stderr="", attempts=1, model_used="t")}
        appliance_runs["y"] = {"appliance_type": "fridge", "result": ApplianceResult(
            status="FAIL", attempts=1, model_used="t")}
        fridge.apply_fault("door_open")
        runtime = shop_runtime_path()
        runtime.parent.mkdir(parents=True, exist_ok=True)
        runtime.write_text("patched", encoding="utf-8")
        with TestClient(app) as client:
            with patch("httpx.post", side_effect=_ok_reload):
                response = client.post("/api/sim/reset")
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["runtime_patch"], "cleared")
        self.assertEqual(body["shop"], "buggy")
        self.assertEqual(body["fridge"], "reset")
        self.assertFalse(runtime.exists())
        self.assertEqual(software_runs, {})
        self.assertEqual(appliance_runs, {})
        self.assertFalse(fridge.snapshot()["door_open"])

    def test_reset_tolerates_unreachable_shop(self) -> None:
        with TestClient(app) as client:
            with patch("httpx.post",
                       side_effect=httpx.ConnectError("down")):
                body = client.post("/api/sim/reset").json()
        self.assertEqual(body["shop"], "unreachable")


if __name__ == "__main__":
    unittest.main()
