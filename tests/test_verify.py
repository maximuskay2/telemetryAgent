import unittest

from core.verify.sandbox import verify_fix, verify_patch


def _runner_factory(results):
    calls = []

    def runner(solution_code, test_code):
        calls.append((solution_code, test_code))
        return results.pop(0)

    runner.calls = calls
    return runner


class VerifyFixTests(unittest.TestCase):
    def test_fail_to_pass_counts_as_verified(self) -> None:
        runner = _runner_factory([
            {"passed": False, "feedback": "assert order"},
            {"passed": True, "feedback": "1 passed"},
        ])
        outcome = verify_fix("original", "patch", "test", runner=runner)
        self.assertTrue(outcome["passed"])
        self.assertEqual([c[0] for c in runner.calls], ["original", "patch"])
        self.assertEqual([c[1] for c in runner.calls], ["test", "test"])

    def test_pass_on_original_rejects_test(self) -> None:
        runner = _runner_factory([{"passed": True, "feedback": "ok"}])
        outcome = verify_fix("original", "patch", "test", runner=runner)
        self.assertFalse(outcome["passed"])
        self.assertIn("not a regression test", outcome["feedback"])
        self.assertEqual(len(runner.calls), 1)

    def test_fail_to_fail_counts_as_failed(self) -> None:
        runner = _runner_factory([
            {"passed": False, "feedback": "orig fail"},
            {"passed": False, "feedback": "patch fail"},
        ])
        outcome = verify_fix("original", "patch", "test", runner=runner)
        self.assertFalse(outcome["passed"])
        self.assertIn("patch fail", outcome["feedback"])

    def test_empty_inputs_rejected(self) -> None:
        with self.assertRaises(ValueError):
            verify_fix("", "patch", "test", runner=_runner_factory([]))


class VerifyPatchTests(unittest.TestCase):
    def test_empty_inputs_rejected_without_touching_modal(self) -> None:
        with self.assertRaises(ValueError):
            verify_patch("", "test")
        with self.assertRaises(ValueError):
            verify_patch("patch", "")


if __name__ == "__main__":
    unittest.main()
