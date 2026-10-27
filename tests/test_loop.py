import os
import unittest
from unittest.mock import patch

from core.agent.loop import run_diagnostic_loop, run_loop, run_software_loop
from core.schemas.diagnosis import Diagnosis
from core.schemas.remediation import GeneratedPatch, VerificationResult
from core.schemas.telemetry import SoftwareTelemetry

DIAGNOSIS = Diagnosis(
    summary="Deadlock on inventory_items",
    likely_cause="Lock ordering inversion in orders service",
    suggested_actions=["Retry with backoff"],
    confidence=0.9,
)
PATCH = GeneratedPatch(patch_code="x = 1\n", test_code="def test_x(): assert True\n")
TELEMETRY = SoftwareTelemetry(source_id="test", raw_log="deadlock log")


def _patch_env(**overrides):
    base = {"BASETEN_API_KEY": "", "FIREWORKS_API_KEY": "", "MODEL_API_KEY": "",
            "META_MODEL_API_KEY": "", "FIREWORKS_PATCH_MODEL": ""}
    base.update(overrides)
    return patch.dict(os.environ, base, clear=False)


def _stub_wiring(verify_results):
    calls = {"generate": 0, "escalate": 0}
    results = list(verify_results)

    def diagnose(telemetry):
        return DIAGNOSIS

    def generate_fix(diagnosis, feedback):
        calls["generate"] += 1
        return PATCH

    def escalate(diagnosis, feedback):
        calls["escalate"] += 1
        return PATCH

    def verify(fix):
        return results.pop(0)

    def act(fix, diagnosis, result, attempts):
        return ("acted", attempts)

    return diagnose, generate_fix, verify, act, escalate, calls


class RunLoopCoreTests(unittest.TestCase):
    def test_pass_first_attempt_uses_generate_fix(self) -> None:
        wiring = _stub_wiring([VerificationResult(passed=True, feedback="ok")])
        diagnose, generate_fix, verify, act, escalate, calls = wiring
        outcome = run_loop("t", diagnose, generate_fix, verify, act, escalate, max_attempts=3)
        self.assertEqual(outcome, ("acted", 1))
        self.assertEqual(calls, {"generate": 1, "escalate": 0})

    def test_final_attempt_uses_escalate(self) -> None:
        wiring = _stub_wiring([VerificationResult(passed=False, feedback="bad"),
                               VerificationResult(passed=True, feedback="ok")])
        diagnose, generate_fix, verify, act, escalate, calls = wiring
        outcome = run_loop("t", diagnose, generate_fix, verify, act, escalate, max_attempts=2)
        self.assertEqual(outcome, ("acted", 2))
        self.assertEqual(calls, {"generate": 1, "escalate": 1})

    def test_feedback_passed_between_attempts(self) -> None:
        seen = []

        def generate_fix(diagnosis, feedback):
            seen.append(feedback)
            return PATCH

        def escalate(diagnosis, feedback):
            seen.append(feedback)
            return PATCH

        wiring = _stub_wiring([VerificationResult(passed=False, feedback="boom"),
                               VerificationResult(passed=True, feedback="ok")])
        diagnose, _, verify, act, _, _ = wiring
        run_loop("t", diagnose, generate_fix, verify, act, escalate, max_attempts=2)
        self.assertEqual(seen, [None, "boom"])

    def test_returns_fail_after_max_attempts(self) -> None:
        wiring = _stub_wiring([VerificationResult(passed=False, feedback="first"),
                               VerificationResult(passed=False, feedback="last")])
        diagnose, generate_fix, verify, act, escalate, _ = wiring
        outcome = run_loop("t", diagnose, generate_fix, verify, act, escalate, max_attempts=2)
        self.assertEqual(outcome, {"status": "FAIL", "attempts": 2, "feedback": "last"})

    def test_emits_step_events(self) -> None:
        events = []
        wiring = _stub_wiring([VerificationResult(passed=True, feedback="ok")])
        diagnose, generate_fix, verify, act, escalate, _ = wiring
        run_loop("t", diagnose, generate_fix, verify, act, escalate,
                 max_attempts=1, on_event=events.append)
        self.assertEqual([e["step"] for e in events], ["diagnose", "generate", "verify"])

    def test_diagnose_event_carries_suggestions(self) -> None:
        events = []
        wiring = _stub_wiring([VerificationResult(passed=True, feedback="ok")])
        diagnose, generate_fix, verify, act, escalate, _ = wiring
        run_loop("t", diagnose, generate_fix, verify, act, escalate,
                 max_attempts=1, on_event=events.append)
        self.assertEqual(events[0]["suggestions"], ["Retry with backoff"])


class SoftwareLoopTests(unittest.TestCase):
    def test_baseten_first_attempt_pass(self) -> None:
        with _patch_env(BASETEN_API_KEY="x"), \
                patch("core.agent.loop.meta_client.diagnose",
                      return_value=DIAGNOSIS) as diag, \
                patch("core.infer.baseten_client.generate_patch",
                      return_value=PATCH) as gen, \
                patch("core.agent.loop.verify_patch",
                      return_value={"passed": True, "feedback": "1 passed"}):
            result = run_software_loop(TELEMETRY)
        self.assertEqual(result.status, "PASS")
        self.assertEqual(result.attempts, 1)
        self.assertTrue(result.model_used.startswith("baseten:"))
        diag.assert_called_once_with(TELEMETRY.model_dump_json())
        gen.assert_called_once_with(DIAGNOSIS, None)

    def test_falls_back_to_fireworks(self) -> None:
        with _patch_env(BASETEN_API_KEY="x", FIREWORKS_API_KEY="y",
                        FIREWORKS_PATCH_MODEL="fw-model"), \
                patch("core.agent.loop.meta_client.diagnose", return_value=DIAGNOSIS), \
                patch("core.infer.baseten_client.generate_patch",
                      side_effect=RuntimeError("down")), \
                patch("core.infer.fireworks_client.generate_patch",
                      return_value=PATCH) as fw, \
                patch("core.agent.loop.verify_patch",
                      return_value={"passed": True, "feedback": "ok"}):
            result = run_software_loop(TELEMETRY)
        self.assertEqual(result.status, "PASS")
        self.assertTrue(result.model_used.startswith("fireworks:"))
        fw.assert_called_once_with(DIAGNOSIS, None)

    def test_final_attempt_escalates_to_wonder(self) -> None:
        with _patch_env(BASETEN_API_KEY="x", MODEL_API_KEY="z"), \
                patch("core.agent.loop.meta_client.diagnose", return_value=DIAGNOSIS), \
                patch("core.infer.baseten_client.generate_patch", return_value=PATCH), \
                patch("core.infer.meta_client.generate_patch",
                      return_value=PATCH) as esc, \
                patch("core.agent.loop.verify_patch", side_effect=[
                    {"passed": False, "feedback": "boom"},
                    {"passed": True, "feedback": "ok"},
                ]):
            result = run_software_loop(TELEMETRY, max_attempts=2)
        self.assertEqual(result.status, "PASS")
        self.assertEqual(result.attempts, 2)
        self.assertIn("muse-wonder", result.model_used)
        esc.assert_called_once()
        args, kwargs = esc.call_args
        self.assertEqual(args[1], "boom")
        self.assertEqual(kwargs.get("model"), "muse-wonder-1.0")

    def test_all_fail_returns_fail_result(self) -> None:
        with _patch_env(MODEL_API_KEY="z"), \
                patch("core.agent.loop.meta_client.diagnose", return_value=DIAGNOSIS), \
                patch("core.infer.meta_client.generate_patch", return_value=PATCH), \
                patch("core.agent.loop.verify_patch",
                      return_value={"passed": False, "feedback": "nope"}):
            result = run_software_loop(TELEMETRY, max_attempts=1)
        self.assertEqual(result.status, "FAIL")
        self.assertEqual(result.attempts, 1)
        self.assertEqual(result.stderr, "nope")
        self.assertIn("muse-wonder", result.model_used)

    def test_no_providers_raises(self) -> None:
        with patch.dict(os.environ, {}, clear=True), \
                patch("core.agent.loop.meta_client.diagnose", return_value=DIAGNOSIS):
            with self.assertRaises(RuntimeError):
                run_software_loop(TELEMETRY, max_attempts=2)

    def test_diagnostic_wrapper_builds_telemetry(self) -> None:
        with _patch_env(BASETEN_API_KEY="x"), \
                patch("core.agent.loop.meta_client.diagnose",
                      return_value=DIAGNOSIS) as diag, \
                patch("core.infer.baseten_client.generate_patch", return_value=PATCH), \
                patch("core.agent.loop.verify_patch",
                      return_value={"passed": True, "feedback": "ok"}):
            result = run_diagnostic_loop("deadlock log")
        self.assertEqual(result.status, "PASS")
        sent = SoftwareTelemetry.model_validate_json(diag.call_args.args[0])
        self.assertEqual((sent.source_id, sent.raw_log), ("api", "deadlock log"))

    def test_original_code_enables_fail_to_pass_check(self) -> None:
        with _patch_env(BASETEN_API_KEY="x"), \
                patch("core.agent.loop.meta_client.diagnose", return_value=DIAGNOSIS), \
                patch("core.infer.baseten_client.generate_patch", return_value=PATCH), \
                patch("core.agent.loop.verify_fix",
                      return_value={"passed": True, "feedback": "ok"}) as fix, \
                patch("core.agent.loop.verify_patch") as single:
            result = run_software_loop(TELEMETRY, original_code="buggy")
        self.assertEqual(result.status, "PASS")
        fix.assert_called_once_with("buggy", PATCH.patch_code, PATCH.test_code)
        single.assert_not_called()

    def test_step_events_carry_durations(self) -> None:
        events = []
        wiring = _stub_wiring([VerificationResult(passed=True, feedback="ok")])
        diagnose, generate_fix, verify, act, escalate, _ = wiring
        run_loop("t", diagnose, generate_fix, verify, act, escalate,
                 max_attempts=1, on_event=events.append)
        self.assertEqual([e["step"] for e in events], ["diagnose", "generate", "verify"])
        for event in events:
            self.assertIn("duration_ms", event)
            self.assertGreaterEqual(event["duration_ms"], 0.0)

    def test_pr_opener_called_on_pass(self) -> None:
        calls = []

        def fake_open_pr(**kwargs):
            calls.append(kwargs)
            return "https://github.com/o/r/pull/1"

        with _patch_env(BASETEN_API_KEY="x"), \
                patch("core.agent.loop.meta_client.diagnose", return_value=DIAGNOSIS), \
                patch("core.infer.baseten_client.generate_patch", return_value=PATCH), \
                patch("core.agent.loop.verify_patch",
                      return_value={"passed": True, "feedback": "1 passed"}):
            result = run_software_loop(TELEMETRY, open_pr=fake_open_pr)
        self.assertEqual(result.status, "PASS")
        self.assertEqual(result.pr_url, "https://github.com/o/r/pull/1")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["diagnosis"], DIAGNOSIS)
        self.assertEqual(calls[0]["patch"], PATCH)
        self.assertEqual(calls[0]["verification_feedback"], "1 passed")
        self.assertEqual(calls[0]["attempts"], 1)
        self.assertTrue(calls[0]["model_used"].startswith("baseten:"))

    def test_pr_skipped_without_opener(self) -> None:
        with _patch_env(BASETEN_API_KEY="x"), \
                patch("core.agent.loop.meta_client.diagnose", return_value=DIAGNOSIS), \
                patch("core.infer.baseten_client.generate_patch", return_value=PATCH), \
                patch("core.agent.loop.verify_patch",
                      return_value={"passed": True, "feedback": "ok"}):
            result = run_software_loop(TELEMETRY)
        self.assertEqual(result.status, "PASS")
        self.assertIsNone(result.pr_url)


if __name__ == "__main__":
    unittest.main()
