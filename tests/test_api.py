import unittest

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


if __name__ == "__main__":
    unittest.main()
