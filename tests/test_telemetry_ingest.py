"""Hardware telemetry ingest tests (Sim 7): readings reach + trigger."""

import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from apps.api.main import app, external_watchers


def reading(source_id="wokwi-esp32-01", temp_c=3.5, current_a=1.1, door=False):
    return {
        "source_id": source_id,
        "appliance_type": "fridge",
        "temperature_c": temp_c,
        "current_a": current_a,
        "vibration_g": 0.02,
        "door_open": door,
    }


class TelemetryIngestTest(unittest.TestCase):
    def tearDown(self) -> None:
        external_watchers.clear()

    def test_reading_broadcasts_to_dashboard(self) -> None:
        with TestClient(app) as client:
            with client.websocket_connect("/api/ws") as websocket:
                response = client.post(
                    "/api/telemetry/appliance", json=reading()
                )
                self.assertEqual(response.status_code, 200)
                event = websocket.receive_json()
        body = response.json()
        self.assertTrue(body["accepted"])
        self.assertEqual(body["buffered"], 1)
        self.assertIsNone(body["triggered"])
        self.assertEqual(event["kind"], "fridge_reading")
        self.assertEqual(
            event["payload"]["state"]["source_id"], "wokwi-esp32-01"
        )

    def test_hot_streak_triggers_and_runs_watcher_path(self) -> None:
        with TestClient(app) as client:
            with client.websocket_connect("/api/ws") as websocket:
                with patch(
                    "apps.api.main._run_appliance_from_telemetry",
                    new=AsyncMock(),
                ) as run:
                    for _ in range(3):
                        response = client.post(
                            "/api/telemetry/appliance",
                            json=reading(temp_c=6.0),
                        )
                    self.assertEqual(
                        response.json()["triggered"], "temp-warning"
                    )
                    kinds = [
                        websocket.receive_json()["kind"] for _ in range(4)
                    ]
        self.assertEqual(
            kinds,
            ["fridge_reading"] * 3 + ["watcher_trigger"],
        )
        run.assert_called_once()
        telemetry, source = run.call_args.args
        self.assertEqual(source, "watcher")
        self.assertEqual(telemetry.source_id, "wokwi-esp32-01")
        self.assertNotIn("fault", telemetry.model_dump_json())

    def test_sources_keep_independent_streaks(self) -> None:
        with TestClient(app) as client:
            with patch(
                "apps.api.main._run_appliance_from_telemetry",
                new=AsyncMock(),
            ):
                for _ in range(3):
                    client.post(
                        "/api/telemetry/appliance",
                        json=reading("node-a", temp_c=6.0),
                    )
                    cold = client.post(
                        "/api/telemetry/appliance",
                        json=reading("node-b", temp_c=3.5),
                    )
                self.assertIsNone(cold.json()["triggered"])
        self.assertIn("node-a", external_watchers)
        self.assertIn("node-b", external_watchers)

    def test_invalid_readings_rejected(self) -> None:
        with TestClient(app) as client:
            negative = client.post(
                "/api/telemetry/appliance",
                json=reading(current_a=-1.0),
            )
            missing = client.post(
                "/api/telemetry/appliance", json={"source_id": "x"}
            )
        self.assertEqual(negative.status_code, 422)
        self.assertEqual(missing.status_code, 422)


if __name__ == "__main__":
    unittest.main()
