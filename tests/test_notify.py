"""Notify stub pins the alert + work-order contract the dashboard shows."""

import unittest

from core.actions.notify import send_alert
from core.schemas.diagnosis import Diagnosis
from core.schemas.remediation import Runbook


class NotifyTests(unittest.TestCase):
    def test_alert_carries_diagnosis_and_work_order(self) -> None:
        diagnosis = Diagnosis(
            summary="Door left open",
            likely_cause="Worn door gasket",
            suggested_actions=[],
            confidence=0.8,
        )
        runbook = Runbook(
            steps=["Close the door", "Inspect the gasket"],
            target_temperature_c=3.0,
            restart_delay_s=240,
            power_off_minutes=10.0,
            disables_protection=False,
        )
        alert = send_alert(diagnosis, runbook, attempts=2, model_used="baseten:x")
        self.assertEqual(alert.channel, "sms-stub")
        self.assertTrue(alert.alert_id.startswith("alert-"))
        self.assertTrue(alert.work_order_id.startswith("wo-"))
        self.assertIn("Door left open", alert.message)
        self.assertIn("Worn door gasket", alert.message)
        self.assertIn("Close the door", alert.work_order)
        self.assertIn("240s", alert.work_order)
        self.assertIn("2 attempt(s)", alert.work_order)

    def test_ids_are_unique_per_call(self) -> None:
        diagnosis = Diagnosis(
            summary="s", likely_cause="c", suggested_actions=[], confidence=0.5
        )
        runbook = Runbook(
            steps=["step"],
            target_temperature_c=3.0,
            restart_delay_s=180,
            power_off_minutes=0.0,
            disables_protection=False,
        )
        first = send_alert(diagnosis, runbook)
        second = send_alert(diagnosis, runbook)
        self.assertNotEqual(first.alert_id, second.alert_id)
        self.assertNotEqual(first.work_order_id, second.work_order_id)


if __name__ == "__main__":
    unittest.main()
