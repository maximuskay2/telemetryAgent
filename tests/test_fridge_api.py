"""Fridge control + stream endpoint tests (Sim 4)."""

import unittest

from fastapi.testclient import TestClient

from apps.api.main import app


class FridgeApiTest(unittest.TestCase):
    def tearDown(self) -> None:
        with TestClient(app) as client:
            client.post("/api/sim/fridge/action", json={"action": "reset"})

    def test_state_snapshot_shape(self) -> None:
        with TestClient(app) as client:
            response = client.get("/api/sim/fridge/state")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        for key in ("appliance_type", "temp_c", "door_open", "compressor_on",
                    "condenser_dirty", "surge_active", "short_cycling"):
            self.assertIn(key, body)

    def test_fault_then_action_round_trip(self) -> None:
        with TestClient(app) as client:
            opened = client.post(
                "/api/sim/fridge/fault", json={"fault": "door_open"}
            )
            self.assertEqual(opened.status_code, 200)
            self.assertTrue(opened.json()["door_open"])
            closed = client.post(
                "/api/sim/fridge/action", json={"action": "close_door"}
            )
            self.assertEqual(closed.status_code, 200)
            self.assertFalse(closed.json()["door_open"])

    def test_reset_restores_baseline(self) -> None:
        with TestClient(app) as client:
            client.post("/api/sim/fridge/fault", json={"fault": "door_open"})
            reset = client.post("/api/sim/fridge/action", json={"action": "reset"})
        body = reset.json()
        self.assertFalse(body["door_open"])
        self.assertEqual(body["temp_c"], 3.5)

    def test_unknown_fault_and_action_rejected(self) -> None:
        with TestClient(app) as client:
            bad_fault = client.post(
                "/api/sim/fridge/fault", json={"fault": "meteor_strike"}
            )
            bad_action = client.post(
                "/api/sim/fridge/action", json={"action": "kick_it"}
            )
        self.assertEqual(bad_fault.status_code, 422)
        self.assertEqual(bad_action.status_code, 422)

    def test_stream_broadcasts_fridge_readings(self) -> None:
        with TestClient(app) as client:
            with client.websocket_connect("/api/ws") as websocket:
                posted = client.post(
                    "/api/sim/fridge/fault", json={"fault": "door_open"}
                )
                self.assertEqual(posted.status_code, 200)
                event = websocket.receive_json()
        self.assertEqual(event["kind"], "fridge_reading")
        self.assertIn("reading", event["payload"])
        self.assertIn("state", event["payload"])
        self.assertIn("temperature_c", event["payload"]["reading"])


if __name__ == "__main__":
    unittest.main()
