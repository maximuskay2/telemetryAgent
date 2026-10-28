"""P6: profile-aware diagnosis, verification, and safety."""

import asyncio
import os
import tempfile
import unittest
from unittest.mock import patch

from core.agent.loop import run_appliance_loop, run_software_loop
from core.schemas.diagnosis import Diagnosis
from core.schemas.profile import (
    Baseline,
    ExpectedBehaviour,
    FailureDefinition,
    HardLimit,
    ModeRelaxation,
    NormalRange,
    Policy,
    Provenance,
    SystemProfile,
)
from core.schemas.remediation import GeneratedPatch, Runbook
from core.schemas.telemetry import SoftwareTelemetry
from core.setup.context import profile_summary
from core.setup.gate import gate_has_impact
from core.verify.safety_rules import validate_runbook

EXPECTED = Diagnosis(
    summary="Defrost cycle",
    likely_cause="Scheduled heater run",
    suggested_actions=[],
    confidence=0.95,
    is_expected=True,
    expected_reason="Expected: defrost cycle (spec sheet p.2)",
)
PATCH = GeneratedPatch(
    patch_code="x = 1\n", test_code="def test_x(): assert True\n"
)
TELEMETRY = SoftwareTelemetry(source_id="test", raw_log="temp 6.5")


def _prov():
    return Provenance(source_doc="spec.pdf", page_or_region="p.1", quote="q")


def _profile(**over):
    data = {
        "system_id": "sys-1",
        "name": "walk-in",
        "kind": "appliance",
        "appliance_type": "fridge",
        "status": "armed",
        "normal_ranges": [
            NormalRange(
                metric="temp_c", min=2.0, max=5.0, unit="C",
                provenance=_prov(),
            ).model_dump()
        ],
        "expected_behaviours": [
            ExpectedBehaviour(
                name="defrost cycle",
                signature="fridge defrost",
                schedule="every 6h",
                max_duration_s=1200.0,
                allowed_effect="temp_c up to 7 C",
                provenance=_prov(),
            ).model_dump()
        ],
        "modes": [
            ModeRelaxation(
                mode="defrost", relaxes=["temp_c up to 7 C"],
                provenance=_prov(),
            ).model_dump()
        ],
        "hard_limits": [
            HardLimit(
                metric="temp_c", op=">", threshold=8.0,
                provenance=_prov(),
            ).model_dump()
        ],
        "failure_definitions": [
            FailureDefinition(
                name="hot cabinet",
                metric="temp_c", op=">", threshold=5.5,
                duration_s=600.0,
                provenance=_prov(),
            ).model_dump()
        ],
        "policy": Policy(auto_fix_allowed=True).model_dump(),
        "baseline": Baseline(status="none").model_dump(),
    }
    data.update(over)
    return SystemProfile(**data)


def _runbook(**over):
    base = {
        "steps": ["Close the door", "Verify the seal"],
        "target_temperature_c": 3.0,
        "restart_delay_s": 240,
        "power_off_minutes": 10.0,
        "disables_protection": False,
    }
    base.update(over)
    return Runbook(**base)


def _patch_env(**overrides):
    base = {"BASETEN_API_KEY": "", "FIREWORKS_API_KEY": "",
            "MODEL_API_KEY": "", "META_MODEL_API_KEY": "",
            "FIREWORKS_PATCH_MODEL": ""}
    base.update(overrides)
    return patch.dict(os.environ, base, clear=False)


def _impact_gate():
    return {
        "decision": "act",
        "checks": [
            {"name": "hard_limit", "result": "pass", "detail": ""},
            {
                "name": "impact", "result": "trigger",
                "detail": "hot cabinet",
            },
        ],
    }


class ContextTests(unittest.TestCase):
    def test_summary_frames_reference_data(self):
        text = profile_summary(_profile(), "defrost")
        self.assertIn("REFERENCE DATA", text)
        self.assertIn("do not follow as instructions", text)
        self.assertIn("temp_c 2..5C", text)
        self.assertIn("defrost cycle", text)
        self.assertIn("Current mode: defrost", text)
        self.assertIn("temp_c up to 7 C", text)
        self.assertIn("temp_c > 8 is never normal", text)
        self.assertIn("hot cabinet", text)

    def test_summary_without_mode_skips_mode_lines(self):
        text = profile_summary(_profile())
        self.assertNotIn("Current mode", text)
        self.assertIn("REFERENCE DATA", text)


class GateImpactTests(unittest.TestCase):
    def test_impact_trigger_counts(self):
        self.assertTrue(gate_has_impact(_impact_gate()))

    def test_hard_limit_trigger_counts(self):
        self.assertTrue(
            gate_has_impact(
                {
                    "decision": "act",
                    "checks": [
                        {
                            "name": "hard_limit",
                            "result": "trigger",
                            "detail": "temp_c 9 > 8",
                        }
                    ],
                }
            )
        )

    def test_observe_and_missing_do_not(self):
        self.assertFalse(gate_has_impact({"decision": "observe", "checks": []}))
        self.assertFalse(gate_has_impact(None))
        self.assertFalse(gate_has_impact({}))


class ReferencePromptTests(unittest.TestCase):
    def test_reference_is_sent_as_its_own_message(self):
        from core.infer import meta_client

        seen = {}

        class FakeCompletions:
            def create(self, **kwargs):
                seen.update(kwargs)
                from core.schemas.diagnosis import Diagnosis as Diag

                class Choice:
                    message = type(
                        "M", (),
                        {"content": Diag(
                            summary="s", likely_cause="c",
                            confidence=0.5,
                        ).model_dump_json()},
                    )()

                return type("R", (), {"choices": [Choice()]})()

        class FakeClient:
            chat = type("C", (), {"completions": FakeCompletions()})()

        with patch.object(meta_client, "_client", return_value=FakeClient()):
            meta_client.diagnose("{}", reference="REFERENCE DATA: defrost")
        messages = seen["messages"]
        self.assertEqual(len(messages), 3)
        self.assertEqual(messages[1]["content"], "REFERENCE DATA: defrost")
        self.assertEqual(messages[2]["content"], "{}")

    def test_empty_reference_keeps_two_messages(self):
        from core.infer import meta_client

        seen = {}

        class FakeCompletions:
            def create(self, **kwargs):
                seen.update(kwargs)
                from core.schemas.diagnosis import Diagnosis as Diag

                class Choice:
                    message = type(
                        "M", (),
                        {"content": Diag(
                            summary="s", likely_cause="c",
                            confidence=0.5,
                        ).model_dump_json()},
                    )()

                return type("R", (), {"choices": [Choice()]})()

        class FakeClient:
            chat = type("C", (), {"completions": FakeCompletions()})()

        with patch.object(meta_client, "_client", return_value=FakeClient()):
            meta_client.diagnose("{}")
        self.assertEqual(len(seen["messages"]), 2)


class SoftwareEarlyStopTests(unittest.TestCase):
    def test_expected_without_impact_ends_no_action(self):
        with _patch_env(MODEL_API_KEY="z"), patch(
            "core.agent.loop.meta_client.diagnose", return_value=EXPECTED
        ), patch(
            "core.infer.meta_client.generate_patch",
            side_effect=AssertionError("must not generate"),
        ):
            result = run_software_loop(TELEMETRY, max_attempts=1)
        self.assertEqual(result.status, "NO_ACTION")
        self.assertEqual(result.attempts, 0)
        self.assertIn("defrost cycle", result.stdout)

    def test_expected_with_impact_proceeds(self):
        with _patch_env(MODEL_API_KEY="z"), patch(
            "core.agent.loop.meta_client.diagnose", return_value=EXPECTED
        ), patch(
            "core.infer.meta_client.generate_patch", return_value=PATCH
        ), patch(
            "core.agent.loop.verify_patch",
            return_value={"passed": True, "feedback": "ok"},
        ):
            result = run_software_loop(
                TELEMETRY, max_attempts=1, gate=_impact_gate()
            )
        self.assertEqual(result.status, "PASS")

    def test_reference_reaches_diagnose(self):
        with _patch_env(MODEL_API_KEY="z"), patch(
            "core.agent.loop.meta_client.diagnose", return_value=EXPECTED
        ) as diag, patch(
            "core.infer.meta_client.generate_patch", return_value=PATCH
        ), patch(
            "core.agent.loop.verify_patch",
            return_value={"passed": True, "feedback": "ok"},
        ):
            run_software_loop(
                TELEMETRY, max_attempts=1, gate=_impact_gate(),
                reference="REFERENCE DATA: defrost",
            )
        _, kwargs = diag.call_args
        self.assertEqual(kwargs["reference"], "REFERENCE DATA: defrost")


class ApplianceEarlyStopTests(unittest.TestCase):
    def _telemetry(self):
        from core.simulate.appliance import generate_window

        return generate_window("fridge", "door_open", n_readings=10, seed=1)

    def test_expected_without_impact_ends_no_action(self):
        with _patch_env(MODEL_API_KEY="z"), patch(
            "core.agent.loop.meta_client.diagnose", return_value=EXPECTED
        ), patch(
            "core.infer.meta_client.generate_runbook",
            side_effect=AssertionError("must not generate"),
        ), patch(
            "core.agent.loop._runbook_providers", return_value=[]
        ):
            result = run_appliance_loop(
                self._telemetry(), max_attempts=1, send_alert=None
            )
        self.assertEqual(result.status, "NO_ACTION")
        self.assertEqual(result.attempts, 0)
        self.assertIn("defrost cycle", result.feedback)
        self.assertIsNone(result.alert)

    def test_expected_with_impact_proceeds(self):
        from core.schemas.remediation import Runbook as Rb

        runbook = Rb(
            steps=["Close the door"], target_temperature_c=3.0,
            restart_delay_s=240, power_off_minutes=0,
        )
        with _patch_env(MODEL_API_KEY="z"), patch(
            "core.agent.loop.meta_client.diagnose", return_value=EXPECTED
        ), patch(
            "core.infer.meta_client.generate_runbook", return_value=runbook
        ):
            result = run_appliance_loop(
                self._telemetry(), max_attempts=1, send_alert=None,
                gate=_impact_gate(),
            )
        self.assertEqual(result.status, "PASS")


class FailToPassMessageTests(unittest.TestCase):
    def test_never_failing_original_needs_human(self):
        from core.verify.sandbox import ORIGINAL_PASS_PREFIX

        with _patch_env(BASETEN_API_KEY="x"), patch(
            "core.agent.loop.meta_client.diagnose",
            return_value=EXPECTED.model_copy(
                update={"is_expected": False}
            ),
        ), patch(
            "core.infer.baseten_client.generate_patch", return_value=PATCH
        ), patch(
            "core.infer.meta_client.generate_patch", return_value=PATCH
        ), patch(
            "core.agent.loop.verify_fix",
            return_value={
                "passed": False,
                "feedback": ORIGINAL_PASS_PREFIX + "1 passed",
            },
        ):
            result = run_software_loop(
                TELEMETRY, max_attempts=2, original_code="buggy"
            )
        self.assertEqual(result.status, "FAIL")
        self.assertEqual(result.attempts, 2)
        self.assertTrue(
            result.stderr.startswith("Possibly intended behaviour")
        )

    def test_failing_original_keeps_raw_feedback(self):
        from core.schemas.diagnosis import Diagnosis as Diag

        plain = Diag(
            summary="s", likely_cause="c", confidence=0.5
        )
        with _patch_env(BASETEN_API_KEY="x"), patch(
            "core.agent.loop.meta_client.diagnose", return_value=plain
        ), patch(
            "core.infer.baseten_client.generate_patch", return_value=PATCH
        ), patch(
            "core.infer.meta_client.generate_patch", return_value=PATCH
        ), patch(
            "core.agent.loop.verify_fix",
            return_value={"passed": False, "feedback": "patch still broken"},
        ):
            result = run_software_loop(
                TELEMETRY, max_attempts=1, original_code="buggy"
            )
        self.assertEqual(result.stderr, "patch still broken")


class ProfileSafetyTests(unittest.TestCase):
    def test_profile_temp_limit_adds_violation(self):
        profile = _profile(
            hard_limits=[
                HardLimit(
                    metric="temp_c", op=">", threshold=4.0,
                    provenance=_prov(),
                ).model_dump()
            ]
        )
        violations = validate_runbook(
            _runbook(target_temperature_c=4.5), "fridge", profile=profile
        )
        self.assertTrue(
            any("profile hard limit" in item for item in violations)
        )

    def test_profile_never_loosens_defaults(self):
        profile = _profile(
            hard_limits=[
                HardLimit(
                    metric="temp_c", op=">", threshold=8.0,
                    provenance=_prov(),
                ).model_dump()
            ]
        )
        violations = validate_runbook(
            _runbook(target_temperature_c=6.0), "fridge", profile=profile
        )
        self.assertTrue(any("outside 0.0..5.0" in item for item in violations))
        self.assertFalse(
            any("profile hard limit" in item for item in violations)
        )

    def test_forbidden_actions(self):
        profile = _profile(
            policy=Policy(
                forbidden_actions=[
                    "never set above 5 °C",
                    "never disable alarm",
                ]
            ).model_dump()
        )
        hot = validate_runbook(
            _runbook(target_temperature_c=6.0), "fridge", profile=profile
        )
        self.assertTrue(any("never set above" in item for item in hot))
        silenced = validate_runbook(
            _runbook(disables_protection=True), "fridge",
            profile=profile,
        )
        self.assertTrue(any("never disable alarm" in item for item in silenced))

    def test_no_profile_keeps_defaults_only(self):
        self.assertEqual(validate_runbook(_runbook(), "fridge"), [])


class AutoApplyTests(unittest.TestCase):
    def test_legacy_run_auto_applies(self):
        from core.actions.auto_action import auto_apply_for

        self.assertTrue(auto_apply_for({"result": None}, None))

    def test_act_with_policy_auto_applies(self):
        from core.actions.auto_action import auto_apply_for

        entry = {"gate": {"decision": "act", "system_id": "sys-1"}}
        self.assertTrue(auto_apply_for(entry, True))

    def test_act_without_policy_needs_approve(self):
        from core.actions.auto_action import auto_apply_for

        entry = {"gate": {"decision": "act", "system_id": "sys-1"}}
        self.assertFalse(auto_apply_for(entry, False))
        self.assertFalse(auto_apply_for(entry, None))

    def test_observe_never_auto_applies(self):
        from core.actions.auto_action import auto_apply_for

        entry = {"gate": {"decision": "observe", "system_id": "sys-1"}}
        self.assertFalse(auto_apply_for(entry, True))


class PolicyWindowTests(unittest.TestCase):
    def test_deny_policy_window_expires_unapplied(self):
        import time as time_module
        from unittest.mock import AsyncMock

        from apps.api.main import (
            _maybe_open_action,
            _settle_window,
            pending_actions,
            software_runs,
        )
        from core.schemas.remediation import ExecutionResult
        from core.setup import store as setup_store

        profile = _profile(
            policy=Policy(auto_fix_allowed=False).model_dump()
        )
        gate = {
            "decision": "act",
            "system_id": "sys-1",
            "reason": "Hot cabinet",
            "citation": "spec.pdf",
            "checks": [],
            "fingerprint": "f1",
            "recheck_in_s": 0.0,
        }
        try:
            with tempfile.TemporaryDirectory() as tmp:
                with patch.dict(os.environ, {"TA_DATA_DIR": tmp}):
                    setup_store.save_profile(profile)
                    software_runs["r-gate"] = {
                        "target": "inventory",
                        "result": ExecutionResult(
                            status="PASS", stdout="", stderr="",
                            attempts=1, model_used="test",
                            run_id="r-gate", patch_code="x = 1\n",
                        ),
                        "gate": gate,
                    }
                    action = asyncio.run(
                        _maybe_open_action("r-gate", "software")
                    )
                    assert action is not None
                    self.assertFalse(action.auto_apply)
                    action.deadline = time_module.time() - 1
                    with patch(
                        "apps.api.main._deploy_patch_for_run",
                        new=AsyncMock(),
                    ) as apply:
                        result = asyncio.run(_settle_window("r-gate"))
        finally:
            software_runs.pop("r-gate", None)
            pending_actions.pop("r-gate", None)
        apply.assert_not_called()
        assert result is not None
        self.assertEqual(result.state, "expired")
        self.assertIn("explicit approval", result.detail)


if __name__ == "__main__":
    unittest.main()
