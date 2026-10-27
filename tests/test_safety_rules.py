"""Safety validator pins the hard bounds from the technical blueprint."""

import unittest

from core.schemas.remediation import Runbook
from core.verify.safety_rules import validate_runbook


def _runbook(**overrides):
    base = {
        "steps": ["Close the door", "Verify the seal"],
        "target_temperature_c": 3.0,
        "restart_delay_s": 240,
        "power_off_minutes": 10.0,
        "disables_protection": False,
    }
    base.update(overrides)
    return Runbook(**base)


class SafetyRulesTests(unittest.TestCase):
    def test_safe_fridge_runbook_passes(self) -> None:
        self.assertEqual(validate_runbook(_runbook(), "fridge"), [])

    def test_safe_freezer_runbook_passes(self) -> None:
        self.assertEqual(
            validate_runbook(_runbook(target_temperature_c=-19.0), "freezer"), []
        )

    def test_target_outside_fridge_band_fails(self) -> None:
        violations = validate_runbook(_runbook(target_temperature_c=-19.0), "fridge")
        self.assertEqual(len(violations), 1)
        self.assertIn("outside 0.0..5.0", violations[0])

    def test_target_outside_freezer_band_fails(self) -> None:
        violations = validate_runbook(_runbook(target_temperature_c=3.0), "freezer")
        self.assertEqual(len(violations), 1)
        self.assertIn("outside -25.0..-15.0", violations[0])

    def test_short_restart_delay_fails(self) -> None:
        violations = validate_runbook(_runbook(restart_delay_s=30), "fridge")
        self.assertEqual(len(violations), 1)
        self.assertIn("180s", violations[0])

    def test_long_power_off_fails(self) -> None:
        violations = validate_runbook(_runbook(power_off_minutes=90.0), "fridge")
        self.assertEqual(len(violations), 1)
        self.assertIn("spoilage", violations[0])

    def test_freezer_allows_longer_power_off(self) -> None:
        self.assertEqual(
            validate_runbook(
                _runbook(power_off_minutes=90.0, target_temperature_c=-19.0),
                "freezer",
            ),
            [],
        )

    def test_disabling_protection_fails(self) -> None:
        violations = validate_runbook(_runbook(disables_protection=True), "fridge")
        self.assertIn("must not disable", violations[0])

    def test_empty_steps_fail(self) -> None:
        violations = validate_runbook(_runbook(steps=[]), "fridge")
        self.assertIn("no actionable steps", violations[0])

    def test_unknown_appliance_type_fails(self) -> None:
        violations = validate_runbook(_runbook(), "toaster")
        self.assertIn("Unknown appliance type", violations[0])

    def test_multiple_violations_all_reported(self) -> None:
        violations = validate_runbook(
            _runbook(target_temperature_c=30.0, restart_delay_s=0, steps=[]),
            "fridge",
        )
        self.assertEqual(len(violations), 3)


if __name__ == "__main__":
    unittest.main()
