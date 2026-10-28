"""P8: 'mark as normal' feedback loop."""

import asyncio
import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from apps.api.main import app, pending_actions, software_runs
from core.schemas.profile import HardLimit, Provenance, SystemProfile
from core.setup.gate import Candidate, evaluate
from core.setup.modes import ModeState


def _prov():
    return Provenance(source_doc="spec.pdf", page_or_region="p.1", quote="q")


def _profile(**over):
    data = {
        "system_id": "sys-1",
        "name": "walk-in",
        "kind": "appliance",
        "appliance_type": "fridge",
        "status": "armed",
        "hard_limits": [
            HardLimit(
                metric="temp_c", op=">", threshold=8.0,
                provenance=_prov(),
            ).model_dump()
        ],
    }
    data.update(over)
    return SystemProfile(**data)


class FeedbackApiTests(unittest.TestCase):
    def tearDown(self) -> None:
        software_runs.clear()
        pending_actions.clear()

    def test_create_and_list_pending(self):
        from core.setup import store as setup_store

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"TA_DATA_DIR": tmp}):
                setup_store.save_profile(_profile())
                with TestClient(app) as client:
                    created = client.post(
                        "/api/systems/sys-1/feedback",
                        json={
                            "fingerprint": "fp1",
                            "signature": "WARN cache cold, warming",
                            "rule": "error",
                            "created_by": "pixel",
                        },
                    )
                    self.assertEqual(created.status_code, 200)
                    item = created.json()
                    self.assertEqual(item["status"], "pending")
                    self.assertTrue(item["id"])
                    listed = client.get("/api/systems/sys-1/feedback")
        items = listed.json()["feedback"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["signature"], "WARN cache cold, warming")

    def test_hard_limit_breach_is_rejected(self):
        from core.setup import store as setup_store

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"TA_DATA_DIR": tmp}):
                setup_store.save_profile(_profile())
                with TestClient(app) as client:
                    response = client.post(
                        "/api/systems/sys-1/feedback",
                        json={
                            "fingerprint": "fp2",
                            "signature": "temp_c 9.5",
                            "metrics": {"temp_c": 9.5},
                        },
                    )
                    self.assertEqual(response.status_code, 400)
                    self.assertIn("hard limits", response.json()["detail"])
                    listed = client.get("/api/systems/sys-1/feedback")
                    self.assertEqual(listed.json()["feedback"], [])

    def test_confirm_appends_behaviour(self):
        from core.setup import store as setup_store

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"TA_DATA_DIR": tmp}):
                setup_store.save_profile(_profile())
                with TestClient(app) as client:
                    created = client.post(
                        "/api/systems/sys-1/feedback",
                        json={
                            "fingerprint": "fp3",
                            "signature": "WARN cache cold, warming",
                            "rule": "error",
                            "created_by": "pixel",
                        },
                    ).json()
                    confirmed = client.post(
                        f"/api/systems/sys-1/feedback/{created['id']}/confirm"
                    )
                    self.assertEqual(confirmed.status_code, 200)
                    behaviours = confirmed.json()["expected_behaviours"]
                    self.assertEqual(len(behaviours), 1)
                    self.assertIn("Marked normal", behaviours[0]["name"])
                    self.assertEqual(
                        behaviours[0]["provenance"]["source_doc"], "user"
                    )
                    again = client.post(
                        f"/api/systems/sys-1/feedback/{created['id']}/confirm"
                    )
                    self.assertEqual(again.status_code, 409)

    def test_reject_keeps_record(self):
        from core.setup import store as setup_store

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"TA_DATA_DIR": tmp}):
                setup_store.save_profile(_profile())
                with TestClient(app) as client:
                    created = client.post(
                        "/api/systems/sys-1/feedback",
                        json={
                            "fingerprint": "fp4",
                            "signature": "x",
                        },
                    ).json()
                    rejected = client.delete(
                        f"/api/systems/sys-1/feedback/{created['id']}"
                    )
                    self.assertEqual(rejected.status_code, 200)
                    profile = client.get("/api/systems/sys-1/profile")
        # GET profile only surfaces pending items.
        self.assertEqual(profile.json()["feedback"], [])

    def test_pending_does_not_suppress_confirmed_does(self):
        from core.setup import store as setup_store

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"TA_DATA_DIR": tmp}):
                setup_store.save_profile(_profile())
                with TestClient(app) as client:
                    created = client.post(
                        "/api/systems/sys-1/feedback",
                        json={
                            "fingerprint": "fp5",
                            "signature": "WARN cache cold, warming",
                            "rule": "error",
                        },
                    ).json()
                    before = setup_store.get_profile("sys-1")
                    candidate = Candidate(
                        system_id="sys-1", source="log", rule="error",
                        fingerprint="fp5",
                        signature="WARN cache cold, warming",
                        window="WARN cache cold, warming",
                    )
                    pending = evaluate(candidate, before, ModeState())
                    self.assertNotEqual(pending.decision, "suppress")
                    client.post(
                        f"/api/systems/sys-1/feedback/{created['id']}/confirm"
                    )
                    after = setup_store.get_profile("sys-1")
                    confirmed = evaluate(candidate, after, ModeState())
                    self.assertEqual(confirmed.decision, "suppress")

    def test_confirmed_cannot_suppress_hard_limit(self):
        from core.setup import store as setup_store

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"TA_DATA_DIR": tmp}):
                setup_store.save_profile(_profile())
                with TestClient(app) as client:
                    created = client.post(
                        "/api/systems/sys-1/feedback",
                        json={
                            "fingerprint": "fp6",
                            "signature": "temp_c_high",
                            "rule": "temp_c_high",
                        },
                    ).json()
                    client.post(
                        f"/api/systems/sys-1/feedback/{created['id']}/confirm"
                    )
                    profile = setup_store.get_profile("sys-1")
                    candidate = Candidate(
                        system_id="sys-1", source="sensor",
                        rule="temp_c_high", fingerprint="fp6",
                        metrics={"temp_c": 9.5},
                    )
                    decision = evaluate(candidate, profile, ModeState())
                    self.assertEqual(decision.decision, "act")

    def _seed_run(self, gate):
        from core.schemas.remediation import ExecutionResult

        software_runs["r-fb"] = {
            "target": "inventory",
            "result": ExecutionResult(
                status="PASS", stdout="", stderr="", attempts=1,
                model_used="test", run_id="r-fb", patch_code="x = 1\n",
            ),
            "gate": gate,
        }
        from apps.api.main import _maybe_open_action

        asyncio.run(_maybe_open_action("r-fb", "software"))

    def test_disapprove_with_mark_normal_parks_feedback(self):
        from core.setup import store as setup_store

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"TA_DATA_DIR": tmp}):
                setup_store.save_profile(_profile())
                self._seed_run(
                    {
                        "decision": "act",
                        "system_id": "sys-1",
                        "fingerprint": "fp7",
                        "signature": "WARN cache cold, warming",
                        "rule": "error",
                    }
                )
                with TestClient(app) as client:
                    response = client.post(
                        "/api/actions/r-fb/disapprove",
                        json={"device": "pixel", "mark_normal": True},
                    )
                    self.assertEqual(response.status_code, 200)
                    body = response.json()
                    self.assertEqual(body["state"], "disapproved")
                    self.assertEqual(
                        body["feedback"]["feedback"]["fingerprint"], "fp7"
                    )
                    listed = client.get("/api/systems/sys-1/feedback")
                    self.assertEqual(len(listed.json()["feedback"]), 1)

    def test_disapprove_without_flag_parks_nothing(self):
        from core.setup import store as setup_store

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"TA_DATA_DIR": tmp}):
                setup_store.save_profile(_profile())
                self._seed_run(
                    {
                        "decision": "act",
                        "system_id": "sys-1",
                        "fingerprint": "fp8",
                        "signature": "WARN cache cold, warming",
                        "rule": "error",
                    }
                )
                with TestClient(app) as client:
                    response = client.post(
                        "/api/actions/r-fb/disapprove",
                        json={"device": "pixel"},
                    )
                    self.assertEqual(response.status_code, 200)
                    self.assertIsNone(response.json()["feedback"])
                    listed = client.get("/api/systems/sys-1/feedback")
                    self.assertEqual(listed.json()["feedback"], [])

    def test_mark_normal_without_gate_context_is_400(self):
        from core.setup import store as setup_store

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"TA_DATA_DIR": tmp}):
                setup_store.save_profile(_profile())
                self._seed_run({})
                with TestClient(app) as client:
                    response = client.post(
                        "/api/actions/r-fb/disapprove",
                        json={"device": "pixel", "mark_normal": True},
                    )
                    self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
