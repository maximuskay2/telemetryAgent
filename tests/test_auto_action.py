"""Server-owned veto windows (M0): eligibility, countdown, decisions."""

import asyncio
import os
import time
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from apps.api.main import (
    _decide_action,
    _maybe_open_action,
    _record_step,
    _settle_window,
    appliance_runs,
    hub,
    pending_actions,
    run_steps,
    software_runs,
)
from apps.api.main import app as api_app
from core.actions.auto_action import action_summary_for
from core.schemas.events import AgentStep
from core.schemas.remediation import ApplianceResult, ExecutionResult, Runbook


def _software_entry(status="PASS", target="inventory", patch="x = 1\n"):
    return {
        "target": target,
        "result": ExecutionResult(
            status=status, stdout="", stderr="", attempts=1,
            model_used="test", run_id="r-soft", patch_code=patch,
        ),
    }


def _appliance_entry(status="PASS", steps=("Close the fridge door",)):
    runbook = None
    if steps is not None:
        runbook = Runbook(
            steps=list(steps), target_temperature_c=3.5,
            restart_delay_s=180, power_off_minutes=0,
        )
    return {
        "appliance_type": "fridge",
        "result": ApplianceResult(
            status=status, runbook=runbook, attempts=1,
            model_used="test", run_id="r-app",
        ),
    }


class _Socket:
    def __init__(self) -> None:
        self.sent: list = []

    async def send_json(self, payload) -> None:
        self.sent.append(payload)


class _ActionCase(unittest.TestCase):
    def setUp(self) -> None:
        software_runs.clear()
        appliance_runs.clear()
        run_steps.clear()
        pending_actions.clear()
        self.socket = _Socket()
        hub.clients.add(self.socket)
        self.addCleanup(hub.clients.discard, self.socket)


class EligibilityTests(_ActionCase):
    def test_software_pass_is_eligible(self) -> None:
        summary = action_summary_for("software", _software_entry())
        self.assertIsNotNone(summary)
        assert summary is not None
        self.assertIn("shop", summary)

    def test_software_ineligible_cases(self) -> None:
        self.assertIsNone(action_summary_for(
            "software", _software_entry(status="FAIL")))
        self.assertIsNone(action_summary_for(
            "software", _software_entry(patch=None)))
        self.assertIsNone(action_summary_for(
            "software", _software_entry(target=None)))
        self.assertIsNone(action_summary_for("software", {}))

    def test_appliance_pass_is_eligible(self) -> None:
        summary = action_summary_for("appliance", _appliance_entry())
        self.assertIsNotNone(summary)
        assert summary is not None
        self.assertIn("Close the fridge door", summary)

    def test_appliance_ineligible_cases(self) -> None:
        self.assertIsNone(action_summary_for(
            "appliance", _appliance_entry(status="FAIL")))
        self.assertIsNone(action_summary_for(
            "appliance", _appliance_entry(steps=None)))
        self.assertIsNone(action_summary_for("appliance", {}))

    def test_unknown_domain_ineligible(self) -> None:
        self.assertIsNone(action_summary_for("toaster", _software_entry()))


class OpenerTests(_ActionCase):
    def test_opens_window_and_broadcasts_pending(self) -> None:
        software_runs["r-soft"] = _software_entry()
        action = asyncio.run(_maybe_open_action("r-soft", "software"))
        self.assertIsNotNone(action)
        assert action is not None
        self.assertEqual(action.state, "pending")
        self.assertGreater(action.deadline, action.opened_at)
        kinds = [m.get("kind") for m in self.socket.sent]
        self.assertIn("action_pending", kinds)

    def test_ineligible_run_opens_nothing(self) -> None:
        software_runs["r-soft"] = _software_entry(status="FAIL")
        self.assertIsNone(asyncio.run(_maybe_open_action("r-soft", "software")))
        self.assertEqual(pending_actions, {})

    def test_open_is_idempotent(self) -> None:
        software_runs["r-soft"] = _software_entry()
        first = asyncio.run(_maybe_open_action("r-soft", "software"))
        second = asyncio.run(_maybe_open_action("r-soft", "software"))
        self.assertIs(first, second)
        self.assertEqual(len(pending_actions), 1)


class SettleTests(_ActionCase):
    def test_auto_applies_at_deadline(self) -> None:
        software_runs["r-soft"] = _software_entry()
        asyncio.run(_maybe_open_action("r-soft", "software"))
        pending_actions["r-soft"].deadline = time.time() - 1
        with patch("apps.api.main._deploy_patch_for_run",
                   new=AsyncMock(return_value={"run_id": "r-soft"})) as apply:
            result = asyncio.run(_settle_window("r-soft"))
        apply.assert_called_once_with("r-soft")
        assert result is not None
        self.assertEqual(result.state, "auto_applied")
        kinds = [m.get("kind") for m in self.socket.sent]
        self.assertIn("action_resolved", kinds)

    def test_before_deadline_does_nothing(self) -> None:
        software_runs["r-soft"] = _software_entry()
        asyncio.run(_maybe_open_action("r-soft", "software"))
        with patch("apps.api.main._deploy_patch_for_run",
                   new=AsyncMock()) as apply:
            result = asyncio.run(_settle_window("r-soft"))
        apply.assert_not_called()
        assert result is not None
        self.assertEqual(result.state, "pending")

    def test_kill_switch_expires_instead(self) -> None:
        software_runs["r-soft"] = _software_entry()
        asyncio.run(_maybe_open_action("r-soft", "software"))
        pending_actions["r-soft"].deadline = time.time() - 1
        with patch.dict(os.environ, {"AUTO_ACTION_ENABLED": "false"}), patch(
            "apps.api.main._deploy_patch_for_run", new=AsyncMock()
        ) as apply:
            result = asyncio.run(_settle_window("r-soft"))
        apply.assert_not_called()
        assert result is not None
        self.assertEqual(result.state, "expired")

    def test_apply_failure_marks_failed(self) -> None:
        from apps.api.main import _ApplyError

        software_runs["r-soft"] = _software_entry()
        asyncio.run(_maybe_open_action("r-soft", "software"))
        pending_actions["r-soft"].deadline = time.time() - 1
        with patch("apps.api.main._deploy_patch_for_run",
                   new=AsyncMock(side_effect=_ApplyError(502, "shop down"))):
            result = asyncio.run(_settle_window("r-soft"))
        assert result is not None
        self.assertEqual(result.state, "failed")
        self.assertIn("shop down", result.detail)


class DecideTests(_ActionCase):
    def test_disapprove_cancels_without_applying(self) -> None:
        software_runs["r-soft"] = _software_entry()
        asyncio.run(_maybe_open_action("r-soft", "software"))
        with patch("apps.api.main._deploy_patch_for_run",
                   new=AsyncMock()) as apply:
            result = asyncio.run(_decide_action("r-soft", False, "pixel-8"))
        apply.assert_not_called()
        self.assertEqual(result.state, "disapproved")
        self.assertEqual(result.decided_by, "pixel-8")

    def test_approve_applies_now(self) -> None:
        software_runs["r-soft"] = _software_entry()
        asyncio.run(_maybe_open_action("r-soft", "software"))
        with patch("apps.api.main._deploy_patch_for_run",
                   new=AsyncMock(return_value={})) as apply:
            result = asyncio.run(_decide_action("r-soft", True, "pixel-8"))
        apply.assert_called_once_with("r-soft")
        self.assertEqual(result.state, "approved")

    def test_second_decision_rejected(self) -> None:
        from apps.api.main import _ApplyError

        software_runs["r-soft"] = _software_entry()
        asyncio.run(_maybe_open_action("r-soft", "software"))
        asyncio.run(_decide_action("r-soft", False, "pixel-8"))
        with self.assertRaises(_ApplyError) as ctx:
            asyncio.run(_decide_action("r-soft", True, "pixel-8"))
        self.assertEqual(ctx.exception.status, 409)

    def test_late_decision_rejected(self) -> None:
        from apps.api.main import _ApplyError

        software_runs["r-soft"] = _software_entry()
        asyncio.run(_maybe_open_action("r-soft", "software"))
        pending_actions["r-soft"].deadline = time.time() - 1
        with self.assertRaises(_ApplyError) as ctx:
            asyncio.run(_decide_action("r-soft", False, "pixel-8"))
        self.assertEqual(ctx.exception.status, 409)

    def test_unknown_run_rejected(self) -> None:
        from apps.api.main import _ApplyError

        with self.assertRaises(_ApplyError) as ctx:
            asyncio.run(_decide_action("nope", False, "pixel-8"))
        self.assertEqual(ctx.exception.status, 404)


class DecideEndpointTests(_ActionCase):
    def test_disapprove_endpoint_cancels(self) -> None:
        software_runs["r-soft"] = _software_entry()
        asyncio.run(_maybe_open_action("r-soft", "software"))
        with TestClient(api_app) as client:
            response = client.post(
                "/api/actions/r-soft/disapprove", json={"device": "pixel-8"}
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["state"], "disapproved")
        self.assertEqual(body["decided_by"], "pixel-8")
        with TestClient(api_app) as client:
            again = client.post(
                "/api/actions/r-soft/disapprove", json={"device": "pixel-8"}
            )
        self.assertEqual(again.status_code, 409)

    def test_approve_endpoint_applies(self) -> None:
        software_runs["r-soft"] = _software_entry()
        asyncio.run(_maybe_open_action("r-soft", "software"))
        with patch("apps.api.main._deploy_patch_for_run",
                   new=AsyncMock(return_value={})):
            with TestClient(api_app) as client:
                response = client.post(
                    "/api/actions/r-soft/approve", json={"device": "pixel-8"}
                )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["state"], "approved")

    def test_token_gating(self) -> None:
        software_runs["r-soft"] = _software_entry()
        asyncio.run(_maybe_open_action("r-soft", "software"))
        with patch.dict(os.environ, {"MOBILE_API_TOKEN": "secret"}):
            with TestClient(api_app) as client:
                missing = client.post(
                    "/api/actions/r-soft/disapprove", json={"device": "x"}
                )
                wrong = client.post(
                    "/api/actions/r-soft/disapprove", json={"device": "x"},
                    headers={"X-Mobile-Token": "nope"},
                )
                right = client.post(
                    "/api/actions/r-soft/disapprove", json={"device": "x"},
                    headers={"X-Mobile-Token": "secret"},
                )
        self.assertEqual(missing.status_code, 401)
        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(right.status_code, 200)

    def test_apply_endpoints_gated_when_token_set(self) -> None:
        software_runs["r-soft"] = _software_entry()
        with patch.dict(os.environ, {"MOBILE_API_TOKEN": "secret"}):
            with TestClient(api_app) as client:
                denied = client.post(
                    "/api/sim/shop/apply-fix", json={"run_id": "r-soft"}
                )
        self.assertEqual(denied.status_code, 401)


class ReportEndpointTests(_ActionCase):
    def test_actions_lists_open_and_recent(self) -> None:
        software_runs["r-soft"] = _software_entry()
        appliance_runs["r-app"] = _appliance_entry()
        asyncio.run(_maybe_open_action("r-soft", "software"))
        asyncio.run(_maybe_open_action("r-app", "appliance"))
        asyncio.run(_decide_action("r-app", False, "pixel-8"))
        with TestClient(api_app) as client:
            body = client.get("/api/actions").json()
        self.assertEqual([a["run_id"] for a in body["open"]], ["r-soft"])
        self.assertEqual([a["run_id"] for a in body["recent"]], ["r-app"])
        self.assertEqual(body["recent"][0]["state"], "disapproved")
        self.assertIn("seconds_left", body["open"][0])
        self.assertGreater(body["open"][0]["seconds_left"], 0)
        self.assertLessEqual(body["open"][0]["seconds_left"], 20)

    def test_runs_list_and_detail(self) -> None:
        software_runs["r-soft"] = _software_entry()
        _record_step(AgentStep(
            step="diagnose", run_id="r-soft", domain="software",
            source="watcher", model="meta:m", detail="locks",
        ))
        asyncio.run(_maybe_open_action("r-soft", "software"))
        with TestClient(api_app) as client:
            listed = client.get("/api/runs").json()["runs"]
            detail = client.get("/api/runs/r-soft").json()
            missing = client.get("/api/runs/nope")
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["source"], "watcher")
        self.assertEqual(listed[0]["n_steps"], 1)
        self.assertEqual(listed[0]["decision"], "pending")
        self.assertEqual(detail["domain"], "software")
        self.assertEqual(len(detail["steps"]), 1)
        self.assertEqual(detail["decision"]["state"], "pending")
        self.assertEqual(missing.status_code, 404)

    def test_record_step_caps_and_ignores_blank(self) -> None:
        _record_step(AgentStep(step="x", run_id=""))
        self.assertEqual(run_steps, {})
        for _ in range(55):
            _record_step(AgentStep(step="x", run_id="r"))
        self.assertEqual(len(run_steps["r"]), 50)

    def test_ticker_broadcasts_seconds_left(self) -> None:
        from apps.api.main import _action_ticker

        software_runs["r-soft"] = _software_entry()

        async def flow():
            await _maybe_open_action("r-soft", "software")
            task = asyncio.ensure_future(_action_ticker())
            await asyncio.sleep(1.3)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        asyncio.run(flow())
        ticks = [m for m in self.socket.sent if m.get("kind") == "action_tick"]
        self.assertGreaterEqual(len(ticks), 1)
        self.assertEqual(ticks[0]["payload"]["run_id"], "r-soft")
        self.assertLessEqual(ticks[0]["payload"]["seconds_left"], 20)


if __name__ == "__main__":
    unittest.main()
