"""N-R1: appliance fix options from a stored run's runbook + profile."""

import copy
import json
import unittest
from pathlib import Path

from core.devices.options import build_appliance_options, device_command_for
from core.schemas.profile import SystemProfile

_FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "devices_door_open.json")
    .read_text()
)


def _run(**overrides):
    run = copy.deepcopy(_FIXTURE["run"])
    run.update(overrides)
    return run


def _profile(**overrides):
    profile = copy.deepcopy(_FIXTURE["profile"])
    profile.update(overrides)
    return SystemProfile(**profile)


def _by_id(options):
    return {option["id"]: option for option in options}


class ApplianceOptionsTests(unittest.TestCase):
    def test_door_open_run_yields_three_option_groups(self) -> None:
        options = build_appliance_options(
            _run(), _profile(), now=1730200000.0 + 600
        )
        kinds = [option["kind"] for option in options]
        self.assertEqual(
            kinds,
            ["remote"] * 4 + ["manual"] * 3 + ["dispatch"],
        )
        titles = [option["title"] for option in options]
        self.assertIn("Start defrost", titles)
        self.assertIn("Lower setpoint 1 °C", titles)
        self.assertIn("Power-cycle compressor", titles)
        self.assertIn("Switch to backup unit", titles)
        self.assertIn("Close the door", titles)
        self.assertIn("Call or WhatsApp the technician", titles)

    def test_option_ids_stable_across_rebuilds(self) -> None:
        first = build_appliance_options(
            _run(), _profile(), now=1730200000.0 + 600
        )
        second = build_appliance_options(
            _run(), _profile(), now=1730200000.0 + 601
        )
        self.assertEqual(
            [option["id"] for option in first],
            [option["id"] for option in second],
        )

    def test_every_option_matches_section_34_shape(self) -> None:
        options = build_appliance_options(
            _run(), _profile(), now=1730200000.0 + 600
        )
        self.assertGreater(len(options), 0)
        for option in options:
            self.assertEqual(
                sorted(option.keys()),
                ["detail", "id", "kind", "safety", "status", "title", "url"],
            )
            self.assertEqual(
                sorted(option["safety"].keys()), ["ok", "reason"]
            )
            self.assertIsInstance(option["safety"]["ok"], bool)
            self.assertEqual(option["status"], "available")

    def test_setpoint_below_hard_band_is_unsafe(self) -> None:
        run = _run()
        run["result"]["runbook"]["target_temperature_c"] = 0.0
        options = _by_id(
            build_appliance_options(run, _profile(), now=1730200600.0)
        )
        setpoint = options["opt_setpoint_minus_1"]
        self.assertFalse(setpoint["safety"]["ok"])
        self.assertIn("outside", setpoint["safety"]["reason"])
        self.assertTrue(options["opt_defrost"]["safety"]["ok"])

    def test_setpoint_breaching_profile_limit_is_unsafe(self) -> None:
        profile = _profile(
            hard_limits=[
                {
                    "metric": "temp_c",
                    "op": "<",
                    "threshold": 3.5,
                    "provenance": {"source_doc": "manual"},
                }
            ]
        )
        options = _by_id(
            build_appliance_options(_run(), profile, now=1730200600.0)
        )
        setpoint = options["opt_setpoint_minus_1"]
        self.assertFalse(setpoint["safety"]["ok"])
        self.assertIn("hard limit", setpoint["safety"]["reason"])

    def test_power_cycle_refused_before_delay(self) -> None:
        options = _by_id(
            build_appliance_options(_run(), _profile(), now=1730200010.0)
        )
        power = options["opt_power_cycle"]
        self.assertFalse(power["safety"]["ok"])
        self.assertIn("wait 170s", power["safety"]["reason"])

    def test_power_cycle_allowed_after_delay(self) -> None:
        options = _by_id(
            build_appliance_options(_run(), _profile(), now=1730200181.0)
        )
        self.assertTrue(options["opt_power_cycle"]["safety"]["ok"])

    def test_power_cycle_refused_without_start_time(self) -> None:
        run = _run()
        del run["started_at"]
        options = _by_id(
            build_appliance_options(run, _profile(), now=1730200600.0)
        )
        power = options["opt_power_cycle"]
        self.assertFalse(power["safety"]["ok"])
        self.assertIn("unknown", power["safety"]["reason"])

    def test_missing_runbook_disables_remote_and_manual(self) -> None:
        run = _run()
        run["result"] = {
            "status": "FAIL",
            "feedback": "model failed",
            "attempts": 3,
            "model_used": "meta:test",
            "run_id": "run-fridge-1",
        }
        options = build_appliance_options(run, _profile(), now=1730200600.0)
        by_id = _by_id(options)
        for option_id in (
            "opt_defrost",
            "opt_setpoint_minus_1",
            "opt_power_cycle",
            "opt_backup",
        ):
            self.assertFalse(by_id[option_id]["safety"]["ok"])
            self.assertIn("no validated runbook", by_id[option_id]["safety"]["reason"])
        self.assertFalse(
            [option for option in options if option["kind"] == "manual"]
        )
        self.assertTrue(by_id["opt_dispatch"]["safety"]["ok"])

    def test_failed_runbook_marks_manual_unsafe(self) -> None:
        run = _run()
        run["result"]["runbook"]["disables_protection"] = True
        options = _by_id(
            build_appliance_options(run, _profile(), now=1730200600.0)
        )
        self.assertFalse(options["opt_defrost"]["safety"]["ok"])
        manual = options["opt_manual_1"]
        self.assertFalse(manual["safety"]["ok"])
        self.assertIn("safety validation", manual["safety"]["reason"])
        self.assertTrue(options["opt_dispatch"]["safety"]["ok"])

    def test_policy_forbidding_defrost_disables_defrost_only(self) -> None:
        profile = _profile(
            policy={
                "allowed_actions": [],
                "forbidden_actions": ["Never run defrost during service hours"],
                "auto_fix_allowed": False,
                "countdown_s": 20,
                "alert_contacts": [],
            }
        )
        options = _by_id(
            build_appliance_options(_run(), profile, now=1730200600.0)
        )
        self.assertFalse(options["opt_defrost"]["safety"]["ok"])
        self.assertIn("profile policy", options["opt_defrost"]["safety"]["reason"])
        self.assertTrue(options["opt_setpoint_minus_1"]["safety"]["ok"])
        self.assertTrue(options["opt_backup"]["safety"]["ok"])

    def test_dispatch_carries_work_order_and_tel_link(self) -> None:
        options = _by_id(
            build_appliance_options(_run(), _profile(), now=1730200600.0)
        )
        dispatch = options["opt_dispatch"]
        self.assertIn("WO-7", dispatch["detail"])
        self.assertEqual(dispatch["url"], "tel:+15550001111")

    def test_dispatch_without_phone_contact_has_no_url(self) -> None:
        profile = _profile(owner_contact="Akingbade (site B)")
        options = _by_id(
            build_appliance_options(_run(), profile, now=1730200600.0)
        )
        self.assertEqual(options["opt_dispatch"]["url"], "")

    def test_device_command_for_remote_options(self) -> None:
        run, profile, now = _run(), _profile(), 1730200600.0
        self.assertEqual(
            device_command_for("opt_defrost", run, profile, now),
            {"action": "defrost", "params": {}},
        )
        self.assertEqual(
            device_command_for("opt_setpoint_minus_1", run, profile, now),
            {"action": "setpoint", "params": {"target_c": 3.0}},
        )
        self.assertEqual(
            device_command_for("opt_power_cycle", run, profile, now),
            {"action": "power_cycle", "params": {"min_off_s": 180}},
        )
        self.assertEqual(
            device_command_for("opt_backup", run, profile, now),
            {"action": "backup_on", "params": {}},
        )

    def test_device_command_none_for_non_remote_or_unsafe(self) -> None:
        run, profile = _run(), _profile()
        self.assertIsNone(
            device_command_for("opt_manual_1", run, profile, 1730200600.0)
        )
        self.assertIsNone(
            device_command_for("opt_dispatch", run, profile, 1730200600.0)
        )
        self.assertIsNone(
            device_command_for("opt_nope", run, profile, 1730200600.0)
        )
        # Power-cycle before the delay is unsafe: no command.
        self.assertIsNone(
            device_command_for("opt_power_cycle", run, profile, 1730200010.0)
        )


if __name__ == "__main__":
    unittest.main()
