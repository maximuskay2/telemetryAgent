"""N-R1: devices router behaviour (options, execute, queue, readings)."""

import copy
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from apps.api.main import app
from apps.api.routes import devices as devices_router
from core.devices import queue as device_queue
from core.schemas.production import FIXTURE_KEY, FIXTURE_SYSTEM_ID

_FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "devices_door_open.json")
    .read_text()
)


def _appliance_entry(started_ago_s=600.0, system_id=None):
    import apps.api.main as api_main  # noqa: F401  (kept for clarity)

    from core.schemas.remediation import ApplianceResult

    entry = {
        "appliance_type": "fridge",
        "result": ApplianceResult.model_validate(
            copy.deepcopy(_FIXTURE["run"]["result"])
        ),
        "started_at": time.time() - started_ago_s,
    }
    if system_id is not None:
        entry["gate"] = {"system_id": system_id, "decision": "act"}
    return entry


def _software_entry():
    from core.schemas.remediation import ExecutionResult

    return {
        "target": "inventory",
        "result": ExecutionResult(
            status="PASS",
            stdout="",
            stderr="",
            attempts=1,
            model_used="meta:test",
        ),
    }


class _Recorder:
    def __init__(self):
        self.sent = []

    async def send_json(self, event):
        self.sent.append(event)


class DevicesRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        import apps.api.main as api_main

        self.api_main = api_main
        self.client = TestClient(app)
        fixture_keys = patch.dict(os.environ, {"TA_FIXTURE_KEYS": "1"})
        fixture_keys.start()
        self.addCleanup(fixture_keys.stop)
        self.run_ids: list[str] = []
        device_queue.reset()
        self.recorder = _Recorder()
        api_main.hub.clients.add(self.recorder)  # type: ignore[arg-type]

    def tearDown(self) -> None:
        for run_id in self.run_ids:
            self.api_main.software_runs.pop(run_id, None)
            self.api_main.appliance_runs.pop(run_id, None)
            devices_router._RUN_FIRST_SEEN.pop(run_id, None)
        self.api_main.hub.clients.discard(self.recorder)
        device_queue.reset()
        self.client.close()

    def _seed_appliance(self, run_id, **kwargs):
        self.api_main.appliance_runs[run_id] = _appliance_entry(**kwargs)
        self.run_ids.append(run_id)

    def _seed_software(self, run_id):
        self.api_main.software_runs[run_id] = _software_entry()
        self.run_ids.append(run_id)

    def _options(self, response):
        self.assertEqual(response.status_code, 200)
        body = response.json()
        return {option["id"]: option for option in body["options"]}

    def _device_key(self):
        return {"Authorization": f"Bearer {FIXTURE_KEY}"}

    def test_options_unknown_run_404(self) -> None:
        response = self.client.get("/api/incidents/nope/options")
        self.assertEqual(response.status_code, 404)

    def test_appliance_options_three_groups(self) -> None:
        self._seed_appliance("run-dev-1")
        response = self.client.get("/api/incidents/run-dev-1/options")
        body = response.json()
        self.assertEqual(body["run_id"], "run-dev-1")
        self.assertEqual(body["domain"], "appliance")
        kinds = [option["kind"] for option in body["options"]]
        self.assertEqual(kinds, ["remote"] * 4 + ["manual"] * 3 + ["dispatch"])
        by_id = self._options(response)
        for option_id in (
            "opt_defrost",
            "opt_setpoint_minus_1",
            "opt_power_cycle",
            "opt_backup",
        ):
            self.assertTrue(
                by_id[option_id]["safety"]["ok"], option_id
            )

    def test_power_cycle_refused_before_delay_over_http(self) -> None:
        self._seed_appliance("run-dev-2", started_ago_s=5.0)
        response = self.client.get("/api/incidents/run-dev-2/options")
        by_id = self._options(response)
        power = by_id["opt_power_cycle"]
        self.assertFalse(power["safety"]["ok"])
        self.assertIn("wait", power["safety"]["reason"])

    def test_software_options_empty_until_jr4(self) -> None:
        self._seed_software("run-dev-sw")
        response = self.client.get("/api/incidents/run-dev-sw/options")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["options"], [])

    def test_execute_manual_done(self) -> None:
        self._seed_appliance("run-dev-3")
        with patch.dict(os.environ, {"MOBILE_API_TOKEN": ""}):
            done = self.client.post(
                "/api/incidents/run-dev-3/options/opt_manual_1/execute"
            )
        self.assertEqual(
            done.json(), {"status": "done", "command_id": ""}
        )
        by_id = self._options(
            self.client.get("/api/incidents/run-dev-3/options")
        )
        self.assertEqual(by_id["opt_manual_1"]["status"], "done")
        events = [
            event for event in self.recorder.sent
            if event.get("kind") == "option_status"
        ]
        self.assertTrue(
            any(
                event["payload"]["option_id"] == "opt_manual_1"
                and event["payload"]["status"] == "done"
                for event in events
            )
        )

    def test_execute_unknown_option_404(self) -> None:
        self._seed_appliance("run-dev-4")
        with patch.dict(os.environ, {"MOBILE_API_TOKEN": ""}):
            response = self.client.post(
                "/api/incidents/run-dev-4/options/opt_nope/execute"
            )
        self.assertEqual(response.status_code, 404)

    def test_execute_unsafe_never_queues(self) -> None:
        self._seed_appliance("run-dev-5", started_ago_s=5.0)
        with patch.dict(os.environ, {"MOBILE_API_TOKEN": ""}):
            refused = self.client.post(
                "/api/incidents/run-dev-5/options/opt_power_cycle/execute"
            )
        self.assertEqual(refused.status_code, 409)
        pending = device_queue.pending_for("any-device")
        self.assertEqual(pending, [])

    def test_execute_remote_full_cycle(self) -> None:
        self._seed_appliance("run-dev-6", system_id=FIXTURE_SYSTEM_ID)
        device_queue.note_device_seen(FIXTURE_SYSTEM_ID, "sim-fridge-01")
        with patch.dict(os.environ, {"MOBILE_API_TOKEN": ""}):
            sent = self.client.post(
                "/api/incidents/run-dev-6/options/opt_defrost/execute"
            )
        self.assertEqual(sent.status_code, 200)
        command_id = sent.json()["command_id"]
        self.assertTrue(command_id.startswith("cmd_"))
        queued = self.client.get(
            "/api/devices/sim-fridge-01/commands", headers=self._device_key()
        )
        self.assertEqual(queued.status_code, 200)
        commands = queued.json()["commands"]
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0]["action"], "defrost")
        ack = self.client.post(
            f"/api/devices/sim-fridge-01/commands/{command_id}/ack",
            json={"ok": True, "detail": "relay on"},
            headers=self._device_key(),
        )
        self.assertEqual(ack.json(), {"status": "done"})
        by_id = self._options(
            self.client.get("/api/incidents/run-dev-6/options")
        )
        self.assertEqual(by_id["opt_defrost"]["status"], "done")

    def test_execute_remote_no_device_409(self) -> None:
        self._seed_appliance("run-dev-7", system_id=FIXTURE_SYSTEM_ID)
        with patch.dict(os.environ, {"MOBILE_API_TOKEN": ""}):
            refused = self.client.post(
                "/api/incidents/run-dev-7/options/opt_defrost/execute"
            )
        self.assertEqual(refused.status_code, 409)
        self.assertIn("no device linked", refused.json()["detail"])

    def test_commands_empty_and_auth(self) -> None:
        denied = self.client.get("/api/devices/sim-fridge-01/commands")
        self.assertEqual(denied.status_code, 401)
        empty = self.client.get(
            "/api/devices/sim-fridge-01/commands", headers=self._device_key()
        )
        self.assertEqual(empty.json(), {"commands": []})

    def test_ack_unknown_or_wrong_device_404(self) -> None:
        queued = device_queue.enqueue(
            "dev-a", "run-x", "opt_defrost", "defrost", {}
        )
        missing = self.client.post(
            "/api/devices/dev-a/commands/cmd_nope/ack",
            json={"ok": True, "detail": ""},
            headers=self._device_key(),
        )
        self.assertEqual(missing.status_code, 404)
        wrong = self.client.post(
            f"/api/devices/dev-b/commands/{queued['id']}/ack",
            json={"ok": True, "detail": ""},
            headers=self._device_key(),
        )
        self.assertEqual(wrong.status_code, 404)

    def test_readings_alias_accepts_keyed_device(self) -> None:
        body = {
            "appliance_type": "fridge",
            "temperature_c": 3.5,
            "current_a": 1.2,
            "vibration_g": 0.02,
            "door_open": False,
        }
        denied = self.client.post(
            "/api/devices/sim-fridge-01/readings", json=body
        )
        self.assertEqual(denied.status_code, 401)
        ok = self.client.post(
            "/api/devices/sim-fridge-01/readings",
            json=body,
            headers=self._device_key(),
        )
        self.assertEqual(ok.status_code, 200)
        payload = ok.json()
        self.assertTrue(payload["accepted"])
        self.assertEqual(payload["device_id"], "sim-fridge-01")
        self.assertEqual(payload["system_id"], FIXTURE_SYSTEM_ID)

    def test_readings_flips_real_device_connection(self) -> None:
        from core.connections import store as connection_store

        body = {
            "appliance_type": "fridge",
            "temperature_c": 3.5,
            "current_a": 1.2,
            "vibration_g": 0.02,
            "door_open": False,
        }
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"TA_DATA_DIR": tmp}):
                _, key = connection_store.create_connection(
                    "coldstore-b", "device", {"device_id": "sim-real-01"},
                    None,
                )
                self.assertIsNotNone(key)
                first = self.client.post(
                    "/api/devices/sim-real-01/readings",
                    json=body,
                    headers={"Authorization": f"Bearer {key}"},
                )
                self.assertEqual(first.status_code, 200)
                stored = connection_store.list_connections("coldstore-b")
                self.assertEqual(len(stored), 1)
                self.assertEqual(stored[0].status, "ok")
                self.assertGreater(stored[0].last_seen, 0)
                events = [
                    event for event in self.recorder.sent
                    if event.get("kind") == "connection_status"
                ]
                self.assertEqual(len(events), 1)
                self.assertEqual(
                    events[0]["payload"]["connection_id"], stored[0].id
                )
                second = self.client.post(
                    "/api/devices/sim-real-01/readings",
                    json=body,
                    headers={"Authorization": f"Bearer {key}"},
                )
                self.assertEqual(second.status_code, 200)
                events = [
                    event for event in self.recorder.sent
                    if event.get("kind") == "connection_status"
                ]
                self.assertEqual(len(events), 1)  # only the first flip

    def test_readings_links_device_for_execute(self) -> None:
        self._seed_appliance("run-dev-8", system_id=FIXTURE_SYSTEM_ID)
        posted = self.client.post(
            "/api/devices/sim-fridge-01/readings",
            json={
                "appliance_type": "fridge",
                "temperature_c": 3.5,
                "current_a": 1.2,
                "vibration_g": 0.02,
                "door_open": False,
            },
            headers=self._device_key(),
        )
        self.assertEqual(posted.status_code, 200)
        with patch.dict(os.environ, {"MOBILE_API_TOKEN": ""}):
            sent = self.client.post(
                "/api/incidents/run-dev-8/options/opt_backup/execute"
            )
        self.assertEqual(sent.json()["status"], "sent")

    def test_execute_mobile_token_enforced(self) -> None:
        self._seed_appliance("run-dev-9")
        url = "/api/incidents/run-dev-9/options/opt_dispatch/execute"
        with patch.dict(os.environ, {"MOBILE_API_TOKEN": "secret"}):
            denied = self.client.post(url)
            self.assertEqual(denied.status_code, 401)
            allowed = self.client.post(
                url, headers={"X-Mobile-Token": "secret"}
            )
            self.assertEqual(allowed.status_code, 200)

    def test_paused_refuses_execute_and_withholds_commands(self) -> None:
        self._seed_appliance("run-dev-10", system_id=FIXTURE_SYSTEM_ID)
        device_queue.note_device_seen(FIXTURE_SYSTEM_ID, "sim-fridge-01")
        device_queue.enqueue(
            "sim-fridge-01", "run-dev-10", "opt_defrost", "defrost", {}
        )
        with patch.dict(os.environ, {"MOBILE_API_TOKEN": ""}), patch(
            "core.actions.mitigate.is_paused", return_value=True
        ):
            refused = self.client.post(
                "/api/incidents/run-dev-10/options/opt_dispatch/execute"
            )
            self.assertEqual(refused.status_code, 409)
            withheld = self.client.get(
                "/api/devices/sim-fridge-01/commands",
                headers=self._device_key(),
            )
            self.assertEqual(withheld.json(), {"commands": []})

    def test_profile_linked_setpoint_uses_profile_limits(self) -> None:
        from core.schemas.profile import SystemProfile

        profile = SystemProfile(**_FIXTURE["profile"])
        profile.hard_limits = [
            type(profile.hard_limits[0])(**{
                **profile.hard_limits[0].model_dump(),
                "op": "<",
                "threshold": 3.5,
            })
        ]
        with tempfile.TemporaryDirectory() as tmp:
            profiles = Path(tmp) / "profiles"
            profiles.mkdir()
            (profiles / "coldstore-b.json").write_text(
                profile.model_dump_json()
            )
            self._seed_appliance("run-dev-11", system_id="coldstore-b")
            with patch.dict(os.environ, {"TA_DATA_DIR": tmp}):
                response = self.client.get(
                    "/api/incidents/run-dev-11/options"
                )
        by_id = self._options(response)
        setpoint = by_id["opt_setpoint_minus_1"]
        self.assertFalse(setpoint["safety"]["ok"])
        self.assertIn("hard limit", setpoint["safety"]["reason"])


if __name__ == "__main__":
    unittest.main()
