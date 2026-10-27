"""Appliance loop runs the shared core with runbook/safety/notify wiring."""

import os
import unittest
from unittest.mock import patch

from core.agent.loop import run_appliance_loop
from core.schemas.diagnosis import Diagnosis
from core.schemas.remediation import ApplianceAlert, Runbook
from core.simulate.appliance import generate_window

DIAGNOSIS = Diagnosis(
    summary="Door left open",
    likely_cause="Worn door gasket",
    suggested_actions=["Close the door"],
    confidence=0.85,
)
RUNBOOK = Runbook(
    steps=["Close the door", "Verify the seal"],
    target_temperature_c=3.0,
    restart_delay_s=240,
    power_off_minutes=10.0,
    disables_protection=False,
)
ALERT = ApplianceAlert(
    alert_id="alert-1",
    channel="sms-stub",
    message="m",
    work_order_id="wo-1",
    work_order="w",
)
TELEMETRY = generate_window("fridge", "door_open", n_readings=10, seed=1)


def _patch_env(**overrides):
    base = {"BASETEN_API_KEY": "", "FIREWORKS_API_KEY": "", "MODEL_API_KEY": "",
            "META_MODEL_API_KEY": "", "FIREWORKS_PATCH_MODEL": ""}
    base.update(overrides)
    return patch.dict(os.environ, base, clear=False)


class ApplianceLoopTests(unittest.TestCase):
    def test_first_attempt_pass_alerts(self) -> None:
        calls = []
        with _patch_env(BASETEN_API_KEY="x"), \
                patch("core.agent.loop.meta_client.diagnose",
                      return_value=DIAGNOSIS) as diag, \
                patch("core.infer.baseten_client.generate_runbook",
                      return_value=RUNBOOK) as gen:
            result = run_appliance_loop(
                TELEMETRY, send_alert=lambda **kw: (calls.append(kw), ALERT)[1]
            )
        self.assertEqual(result.status, "PASS")
        self.assertEqual(result.runbook, RUNBOOK)
        self.assertEqual(result.alert, ALERT)
        self.assertEqual(result.attempts, 1)
        self.assertTrue(result.model_used.startswith("baseten:"))
        self.assertTrue(result.run_id)
        diag.assert_called_once_with(TELEMETRY.model_dump_json())
        gen.assert_called_once_with(DIAGNOSIS, None)
        self.assertEqual(calls[0]["diagnosis"], DIAGNOSIS)
        self.assertEqual(calls[0]["runbook"], RUNBOOK)

    def test_violation_feedback_retries_then_passes(self) -> None:
        bad = RUNBOOK.model_copy(update={"restart_delay_s": 5})
        with _patch_env(BASETEN_API_KEY="x"), \
                patch("core.agent.loop.meta_client.diagnose", return_value=DIAGNOSIS), \
                patch("core.infer.baseten_client.generate_runbook",
                      side_effect=[bad, RUNBOOK]) as gen, \
                patch("core.infer.meta_client.generate_runbook",
                      return_value=RUNBOOK):
            result = run_appliance_loop(TELEMETRY, max_attempts=3)
        self.assertEqual(result.status, "PASS")
        self.assertEqual(result.attempts, 2)
        self.assertIsNone(result.alert)  # no sender passed
        _, feedback = gen.call_args_list[1].args
        self.assertIn("180s", feedback)

    def test_final_attempt_escalates_to_wonder(self) -> None:
        bad = RUNBOOK.model_copy(update={"steps": []})
        with _patch_env(BASETEN_API_KEY="x", MODEL_API_KEY="z"), \
                patch("core.agent.loop.meta_client.diagnose", return_value=DIAGNOSIS), \
                patch("core.infer.baseten_client.generate_runbook", return_value=bad), \
                patch("core.infer.meta_client.generate_runbook",
                      return_value=RUNBOOK) as esc:
            result = run_appliance_loop(TELEMETRY, max_attempts=2)
        self.assertEqual(result.status, "PASS")
        self.assertEqual(result.attempts, 2)
        self.assertIn("muse-wonder", result.model_used)
        esc.assert_called_once()
        args, kwargs = esc.call_args
        self.assertIn("no actionable steps", args[1])
        self.assertEqual(kwargs.get("model"), "muse-wonder-1.0")

    def test_all_fail_returns_violations(self) -> None:
        bad = RUNBOOK.model_copy(update={"disables_protection": True})
        with _patch_env(BASETEN_API_KEY="x"), \
                patch("core.agent.loop.meta_client.diagnose", return_value=DIAGNOSIS), \
                patch("core.infer.baseten_client.generate_runbook", return_value=bad), \
                patch("core.infer.meta_client.generate_runbook", return_value=bad):
            result = run_appliance_loop(TELEMETRY, max_attempts=2)
        self.assertEqual(result.status, "FAIL")
        self.assertEqual(result.attempts, 2)
        self.assertIn("must not disable", result.feedback)
        self.assertIsNone(result.runbook)

    def test_events_carry_domain_run_id_and_details(self) -> None:
        events = []
        with _patch_env(BASETEN_API_KEY="x"), \
                patch("core.agent.loop.meta_client.diagnose", return_value=DIAGNOSIS), \
                patch("core.infer.baseten_client.generate_runbook", return_value=RUNBOOK):
            result = run_appliance_loop(TELEMETRY, on_event=events.append, run_id="r1")
        self.assertEqual(result.run_id, "r1")
        self.assertEqual(
            [e["step"] for e in events], ["diagnose", "generate", "verify"]
        )
        for event in events:
            self.assertEqual(event["domain"], "appliance")
            self.assertEqual(event["run_id"], "r1")
            self.assertTrue(event["detail"])
        self.assertIn("Door left open", events[0]["detail"])
        self.assertIn("runbook", events[1]["detail"])
        self.assertIn("0 violations", events[2]["detail"])

    def test_no_providers_raises(self) -> None:
        with patch.dict(os.environ, {}, clear=True), \
                patch("core.agent.loop.meta_client.diagnose", return_value=DIAGNOSIS):
            with self.assertRaises(RuntimeError):
                run_appliance_loop(TELEMETRY, max_attempts=2)


if __name__ == "__main__":
    unittest.main()
