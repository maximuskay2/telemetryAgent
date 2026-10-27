"""Local Docker runner: same verify contract, host never executes code."""

import subprocess
import sys
import unittest
from unittest.mock import patch

from core.verify.local_runner import verify_patch_local
from core.verify.sandbox import verify_patch


def _completed(returncode=0, stdout="1 passed", stderr=""):
    return subprocess.CompletedProcess(
        args=["docker"], returncode=returncode, stdout=stdout, stderr=stderr
    )


class LocalRunnerTests(unittest.TestCase):
    def test_empty_inputs_rejected_without_docker(self) -> None:
        with patch("shutil.which", side_effect=AssertionError("no docker check")):
            with self.assertRaises(ValueError):
                verify_patch_local("", "t")
            with self.assertRaises(ValueError):
                verify_patch_local("p", "")

    def test_missing_docker_raises_instead_of_running(self) -> None:
        with patch("shutil.which", return_value=None), patch(
            "subprocess.run", side_effect=AssertionError("must not run")
        ):
            with self.assertRaises(RuntimeError) as ctx:
                verify_patch_local("p", "t")
        self.assertIn("Docker is not installed", str(ctx.exception))

    def test_pass_and_fail_from_exit_code(self) -> None:
        with patch("shutil.which", return_value="/usr/bin/docker"), patch(
            "subprocess.run", return_value=_completed(0)
        ) as run:
            result = verify_patch_local("p", "t")
        self.assertTrue(result["passed"])
        self.assertIn("[local docker]", result["feedback"])
        self.assertIn("1 passed", result["feedback"])
        argv = run.call_args.args[0]
        self.assertEqual(argv[:3], ["docker", "run", "--rm"])
        self.assertIn("pytest -q test_solution.py", argv[-1])

        with patch("shutil.which", return_value="/usr/bin/docker"), patch(
            "subprocess.run", return_value=_completed(1, stdout="", stderr="FAILED")
        ):
            result = verify_patch_local("p", "t")
        self.assertFalse(result["passed"])
        self.assertIn("FAILED", result["feedback"])

    def test_timeout_counts_as_failed(self) -> None:
        with patch("shutil.which", return_value="/usr/bin/docker"), patch(
            "subprocess.run", side_effect=subprocess.TimeoutExpired("docker", 5)
        ):
            result = verify_patch_local("p", "t", timeout=5)
        self.assertFalse(result["passed"])
        self.assertIn("timed out after 5s", result["feedback"])

    def test_feedback_truncated(self) -> None:
        with patch("shutil.which", return_value="/usr/bin/docker"), patch(
            "subprocess.run", return_value=_completed(1, stdout="x" * 20000)
        ):
            result = verify_patch_local("p", "t")
        self.assertLessEqual(len(result["feedback"]), 8100)


class SandboxFallbackTests(unittest.TestCase):
    def test_missing_modal_falls_back_to_docker(self) -> None:
        sentinel = {"passed": True, "feedback": "local"}
        with patch.dict(sys.modules, {"modal": None}), patch(
            "core.verify.local_runner.verify_patch_local", return_value=sentinel
        ) as local:
            result = verify_patch("p", "t", timeout=11)
        self.assertEqual(result, sentinel)
        local.assert_called_once_with("p", "t", timeout=11)

    def test_modal_auth_error_falls_back_to_docker(self) -> None:
        class AuthError(Exception):
            pass

        try:
            import modal  # noqa: F401
        except ImportError:
            self.skipTest("modal not installed")
        sentinel = {"passed": True, "feedback": "local"}
        with patch("modal.App.lookup", side_effect=AuthError("no creds")), patch(
            "core.verify.local_runner.verify_patch_local", return_value=sentinel
        ):
            self.assertEqual(verify_patch("p", "t"), sentinel)

    def test_other_modal_errors_still_raise(self) -> None:
        try:
            import modal  # noqa: F401
        except ImportError:
            self.skipTest("modal not installed")
        with patch("modal.App.lookup", side_effect=RuntimeError("boom")), patch(
            "core.verify.local_runner.verify_patch_local",
            side_effect=AssertionError("no fallback"),
        ):
            with self.assertRaises(RuntimeError):
                verify_patch("p", "t")


if __name__ == "__main__":
    unittest.main()
