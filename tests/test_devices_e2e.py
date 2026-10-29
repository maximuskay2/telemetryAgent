"""N-R2: sim_device.py end to end against a live API on 8201.

A tapped option queues a real command, the software ESP32 polls it over
real HTTP and acks, and the option flips to done — within 10 s (roadmap
§4 N-R2 acceptance). Slow by design; one test only.
"""

import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
import uvicorn

from apps.api.main import app
from core.devices import queue as device_queue
from core.schemas.production import FIXTURE_KEY, FIXTURE_SYSTEM_ID
from core.schemas.remediation import ApplianceResult
from hardware import sim_device

from tests.test_devices_router import _FIXTURE as _ROUTER_FIXTURE
import copy

API = "http://127.0.0.1:8201"
RUN_ID = "run-e2e-1"
DEVICE_ID = "sim-e2e-01"


class SimE2ETests(unittest.TestCase):
    def test_tapped_option_acked_within_10s(self) -> None:
        import apps.api.main as api_main

        started = time.time()
        config = uvicorn.Config(
            app, host="127.0.0.1", port=8201, log_level="error"
        )
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        try:
            self._wait_for_health()
            with tempfile.TemporaryDirectory() as tmp, patch.dict(
                os.environ,
                {"TA_DATA_DIR": tmp, "MOBILE_API_TOKEN": ""},
            ):
                api_main.appliance_runs[RUN_ID] = {
                    "appliance_type": "fridge",
                    "result": ApplianceResult.model_validate(
                        copy.deepcopy(_ROUTER_FIXTURE["run"]["result"])
                    ),
                    "started_at": time.time() - 600,
                    "gate": {"system_id": FIXTURE_SYSTEM_ID},
                }
                try:
                    summary = self._drive_sim()
                finally:
                    api_main.appliance_runs.pop(RUN_ID, None)
                    device_queue.reset()
        finally:
            server.should_exit = True
            thread.join(timeout=10)
        elapsed = time.time() - started
        self.assertLess(elapsed, 30.0)  # server boot + sim run budget
        acks = [ack for ack in summary["acks"] if ack["ok"]]
        self.assertTrue(acks, "sim never acked the tapped option")

    def _wait_for_health(self) -> None:
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                response = httpx.get(f"{API}/api/health", timeout=2)
                if response.status_code == 200:
                    return
            except httpx.HTTPError:
                time.sleep(0.1)
        self.fail("API on 8201 never became healthy")

    def _drive_sim(self):
        result: dict = {}
        sim_thread = threading.Thread(
            target=lambda: result.update(
                summary=sim_device.main(
                    [
                        "--api", API,
                        "--device", DEVICE_ID,
                        "--key", FIXTURE_KEY,
                        "--interval", "0.2",
                        "--poll-interval", "0.2",
                        "--max-readings", "15",
                    ]
                )
            ),
            daemon=True,
        )
        sim_thread.start()
        try:
            deadline = time.time() + 5
            while device_queue.device_for_system(FIXTURE_SYSTEM_ID) is None:
                if time.time() > deadline:
                    self.fail("sim readings never linked the device")
                time.sleep(0.05)
            sent = httpx.post(
                f"{API}/api/incidents/{RUN_ID}/options/opt_defrost/execute",
                timeout=5,
            )
            self.assertEqual(sent.status_code, 200)
            tapped_at = time.time()
            deadline = tapped_at + 10
            while time.time() < deadline:
                options = httpx.get(
                    f"{API}/api/incidents/{RUN_ID}/options", timeout=5
                ).json()["options"]
                state = {
                    option["id"]: option["status"] for option in options
                }.get("opt_defrost")
                if state == "done":
                    break
                time.sleep(0.1)
            else:
                self.fail("tapped option not acked within 10 s")
        finally:
            sim_thread.join(timeout=15)
        return result["summary"]


if __name__ == "__main__":
    unittest.main()
