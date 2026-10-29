"""N-R2: sim_device protocol behaviour against a fake device API."""

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from hardware import sim_device

_DEVICE_KEY = "device-key-1"


class _FakeApi(BaseHTTPRequestHandler):
    server_version = "FakeApi/1"

    def _send(self, body, status=200):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode() if length else "{}"
        return json.loads(raw or "{}")

    def log_message(self, *args):
        pass

    def do_POST(self):
        if self.path.endswith("/readings"):
            self.server.readings.append(
                {
                    "auth": self.headers.get("Authorization"),
                    "body": self._body(),
                }
            )
            self._send({"accepted": True})
        elif "/commands/" in self.path and self.path.endswith("/ack"):
            cid = self.path.split("/commands/")[1].split("/ack")[0]
            self.server.acks.append({"id": cid, "body": self._body()})
            self.server.queued = [
                cmd for cmd in self.server.queued if cmd["id"] != cid
            ]
            self._send({"status": "done"})
        else:
            self._send({"detail": "not found"}, status=404)

    def do_GET(self):
        if self.path.endswith("/commands"):
            self.server.polls.append(dict(self.headers))
            self._send({"commands": list(self.server.queued)})
        else:
            self._send({"detail": "not found"}, status=404)


class SimDeviceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeApi)
        self.server.readings = []
        self.server.acks = []
        self.server.polls = []
        self.server.queued = []
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True
        )
        self.thread.start()
        host, port = self.server.server_address
        self.api = f"http://{host}:{port}"
        self.args = [
            "--api", self.api,
            "--device", "sim-fridge-01",
            "--key", _DEVICE_KEY,
            "--interval", "0.01",
            "--poll-interval", "0",
        ]

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def _run(self, extra):
        return sim_device.main(self.args + extra)

    def _assert_bearer_key(self, header):
        scheme, _, key = (header or "").partition(" ")
        self.assertEqual(scheme, "Bearer")
        self.assertEqual(key, _DEVICE_KEY)

    def test_posts_readings_with_bearer_key(self) -> None:
        self._run(["--fault", "door_open", "--max-readings", "3"])
        self.assertGreaterEqual(len(self.server.readings), 3)
        first = self.server.readings[0]
        self._assert_bearer_key(first["auth"])
        body = first["body"]
        self.assertEqual(body["appliance_type"], "fridge")
        self.assertTrue(body["door_open"])
        temps = [item["body"]["temperature_c"] for item in self.server.readings]
        self.assertGreater(temps[-1], temps[0])

    def test_executes_defrost_and_acks(self) -> None:
        self.server.queued.append(
            {"id": "cmd_1", "action": "defrost", "params": {},
             "expires_at": 9999999999.0}
        )
        summary = self._run(["--max-readings", "2"])
        self.assertEqual(len(self.server.acks), 1)
        self.assertEqual(self.server.acks[0]["id"], "cmd_1")
        self.assertTrue(self.server.acks[0]["body"]["ok"])
        self.assertTrue(summary["defrost_on"])
        self.assertFalse(summary["compressor_on"])

    def test_power_cycle_refused_during_defrost(self) -> None:
        self.server.queued.append(
            {"id": "cmd_1", "action": "defrost", "params": {},
             "expires_at": 9999999999.0}
        )
        self.server.queued.append(
            {"id": "cmd_2", "action": "power_cycle",
             "params": {"min_off_s": 180}, "expires_at": 9999999999.0}
        )
        self._run(["--max-readings", "2"])
        acks = {ack["id"]: ack["body"] for ack in self.server.acks}
        self.assertTrue(acks["cmd_1"]["ok"])
        self.assertFalse(acks["cmd_2"]["ok"])
        self.assertIn("defrost", acks["cmd_2"]["detail"])

    def test_unknown_action_nacked(self) -> None:
        self.server.queued.append(
            {"id": "cmd_9", "action": "self_destruct", "params": {},
             "expires_at": 9999999999.0}
        )
        self._run(["--max-readings", "1"])
        self.assertEqual(len(self.server.acks), 1)
        self.assertFalse(self.server.acks[0]["body"]["ok"])
        self.assertIn("unknown action", self.server.acks[0]["body"]["detail"])

    def test_setpoint_updates_state(self) -> None:
        self.server.queued.append(
            {"id": "cmd_3", "action": "setpoint",
             "params": {"target_c": 2.5}, "expires_at": 9999999999.0}
        )
        summary = self._run(["--max-readings", "1"])
        self.assertTrue(self.server.acks[0]["body"]["ok"])
        self.assertEqual(summary["setpoint_c"], 2.5)


if __name__ == "__main__":
    unittest.main()
