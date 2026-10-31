"""Local Docker runner: same verify contract, host never executes code."""

import os
import subprocess
import sys
import unittest
from unittest.mock import patch

from core.verify.local_runner import resolve_docker, verify_patch_local
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
        with patch.dict(os.environ, {}, clear=False), patch(
            "shutil.which", return_value=None
        ), patch("os.path.isfile", return_value=False), patch(
            "subprocess.run", side_effect=AssertionError("must not run")
        ):
            os.environ.pop("DOCKER_BIN", None)
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
        self.assertTrue(argv[0].endswith("docker"))
        self.assertEqual(argv[1:3], ["run", "--rm"])
        self.assertIn("pytest", argv)
        self.assertIn("test_solution.py", argv)

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

    def test_container_is_network_isolated_and_capped(self) -> None:
        with patch("shutil.which", return_value="/usr/bin/docker"), patch(
            "subprocess.run", return_value=_completed(0)
        ) as run:
            verify_patch_local("p", "t")
        argv = run.call_args.args[0]
        for flag in ("--network", "none", "--read-only", "--memory", "--cpus",
                     "--pids-limit", "-p", "no:cacheprovider"):
            self.assertIn(flag, argv)
        mount = argv[argv.index("-v") + 1]
        self.assertTrue(mount.endswith(":ro"))
        self.assertNotIn("pip", argv)  # pytest baked in; no install at runtime

    def test_missing_image_points_at_build_script(self) -> None:
        with patch("shutil.which", return_value="/usr/bin/docker"), patch(
            "subprocess.run",
            return_value=_completed(125, stderr="Unable to find image"),
        ):
            result = verify_patch_local("p", "t")
        self.assertFalse(result["passed"])
        self.assertIn("build-sandbox-image", result["feedback"])

    def test_resolver_prefers_docker_bin_then_path_then_desktop(self) -> None:
        with patch.dict(os.environ, {"DOCKER_BIN": "/opt/docker"}), patch(
            "os.path.isfile", return_value=True
        ), patch("os.access", return_value=True):
            self.assertEqual(resolve_docker(), "/opt/docker")
        with patch.dict(os.environ, {}, clear=False), patch(
            "shutil.which", return_value="/usr/bin/docker"
        ):
            os.environ.pop("DOCKER_BIN", None)
            self.assertEqual(resolve_docker(), "/usr/bin/docker")
        with patch.dict(os.environ, {}, clear=False), patch(
            "shutil.which", return_value=None
        ), patch("os.path.isfile", return_value=True), patch(
            "os.access", return_value=True
        ):
            os.environ.pop("DOCKER_BIN", None)
            found = resolve_docker()
            self.assertIsNotNone(found)
            assert found is not None
            self.assertTrue(found.endswith(".docker/bin/docker"))

    def test_bad_docker_bin_resolves_to_none(self) -> None:
        with patch.dict(os.environ, {"DOCKER_BIN": "/nonexistent/docker"}):
            self.assertIsNone(resolve_docker())


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

    def test_ta_verify_local_skips_modal(self) -> None:
        try:
            import modal  # noqa: F401
        except ImportError:
            self.skipTest("modal not installed")
        sentinel = {"passed": True, "feedback": "local"}
        with patch.dict(os.environ, {"TA_VERIFY": "local"}), patch(
            "modal.App.lookup", side_effect=AssertionError("must not touch modal")
        ), patch(
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


class _FakeStream:
    def __init__(self, text="") -> None:
        self._text = text

    def read(self):
        return self._text


class _FakeProcess:
    def __init__(self, behavior="ok") -> None:
        self._behavior = behavior
        self.returncode = 0
        self.stderr = _FakeStream()
        self.stdout = _FakeStream("1 passed")

    def wait(self, timeout=None):
        if self._behavior == "timeout":
            raise TimeoutError("timed out")
        if self._behavior == "shutdown":
            raise Exception("Sandbox already shut down")


class _FakeSandbox:
    def __init__(self, behavior="ok") -> None:
        self._behavior = behavior
        self.terminated = False

    def exec(self, *args, **kwargs):
        return _FakeProcess(self._behavior)

    def terminate(self):
        self.terminated = True


class SandboxExecTests(unittest.TestCase):
    """Mid-run sandbox failures return feedback, never raise."""

    def _run_with(self, behavior):
        try:
            import modal  # noqa: F401
        except ImportError:
            self.skipTest("modal not installed")
        sandbox = _FakeSandbox(behavior)
        with patch("modal.App.lookup"), patch(
            "modal.Sandbox.create", return_value=sandbox
        ), patch("modal.Image.debian_slim") as debian:
            debian.return_value.pip_install.return_value = object()
            return verify_patch("x = 1\n", "def test_x(): assert True\n"), sandbox

    def test_shutdown_sandbox_returns_feedback(self) -> None:
        result, sandbox = self._run_with("shutdown")
        self.assertFalse(result["passed"])
        self.assertIn("sandbox error", result["feedback"])
        self.assertTrue(sandbox.terminated)

    def test_hung_pytest_returns_timeout_feedback(self) -> None:
        result, _ = self._run_with("timeout")
        self.assertFalse(result["passed"])
        self.assertIn("timed out", result["feedback"])

    def test_wait_without_timeout_kw_falls_back(self) -> None:
        class _LegacyProcess(_FakeProcess):
            def wait(self):  # noqa: D102 - old modal has no timeout kw
                self.returncode = 0

        class _LegacySandbox(_FakeSandbox):
            def exec(self, *args, **kwargs):
                return _LegacyProcess()

        try:
            import modal  # noqa: F401
        except ImportError:
            self.skipTest("modal not installed")
        with patch("modal.App.lookup"), patch(
            "modal.Sandbox.create", return_value=_LegacySandbox()
        ), patch("modal.Image.debian_slim") as debian:
            debian.return_value.pip_install.return_value = object()
            result = verify_patch("x = 1\n", "def test_x(): assert True\n")
        self.assertTrue(result["passed"])


if __name__ == "__main__":
    unittest.main()
