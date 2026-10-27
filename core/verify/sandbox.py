from __future__ import annotations

import base64
import os

# Modal retired sandbox.open() server-side, and its replacement (sandbox.filesystem)
# needs a Modal release that no longer supports Python 3.9, so files go in via exec.
_WRITE_FILE = (
    "import base64, os, sys; "
    "os.makedirs(os.path.dirname(sys.argv[1]), exist_ok=True); "
    "open(sys.argv[1], 'wb').write(base64.b64decode(sys.argv[2]))"
)


def _write_file(sandbox, path: str, content: str) -> None:
    encoded = base64.b64encode(content.encode()).decode()
    process = sandbox.exec("python", "-c", _WRITE_FILE, path, encoded)
    process.wait()
    if process.returncode != 0:
        raise RuntimeError(f"Could not write {path} in sandbox: {process.stderr.read()}")


def _local_fallback(patch_code: str, test_code: str, timeout: int) -> dict:
    from core.verify.local_runner import verify_patch_local

    return verify_patch_local(patch_code, test_code, timeout=timeout)


def verify_patch(patch_code: str, test_code: str, timeout: int = 60) -> dict:
    """Write a generated patch and pytest suite into a Modal Sandbox and run pytest.

    Generated code is untrusted and only ever runs inside a sandbox. When Modal
    is unavailable (not installed, or no credentials), this falls back to the
    local Docker runner instead of failing. `TA_VERIFY=local` forces Docker
    (fast, offline) without touching Modal.
    """
    if not patch_code or not test_code:
        raise ValueError("patch_code and test_code must be non-empty strings")
    if os.environ.get("TA_VERIFY", "").lower() == "local":
        return _local_fallback(patch_code, test_code, timeout)
    try:
        import modal
    except ImportError:
        return _local_fallback(patch_code, test_code, timeout)

    try:
        image = modal.Image.debian_slim(python_version="3.11").pip_install("pytest")
        app = modal.App.lookup("telemetry-agent-sandbox", create_if_missing=True)
        sandbox = modal.Sandbox.create(app=app, image=image, timeout=timeout)
    except Exception as exc:
        if type(exc).__name__ == "AuthError":
            return _local_fallback(patch_code, test_code, timeout)
        raise
    try:
        _write_file(sandbox, "/work/solution.py", patch_code)
        _write_file(sandbox, "/work/test_solution.py", test_code)
        process = sandbox.exec("pytest", "-q", "test_solution.py", workdir="/work")
        process.wait()
        return {
            "passed": process.returncode == 0,
            "feedback": process.stderr.read() + process.stdout.read(),
        }
    finally:
        sandbox.terminate()


def verify_fix(original_code: str, patch_code: str, test_code: str, runner=None) -> dict:
    """Fail-to-pass check: the test must FAIL on the original and PASS on the patch.

    `runner` defaults to `verify_patch` and is injectable for tests.
    """
    if not original_code or not patch_code or not test_code:
        raise ValueError("original_code, patch_code and test_code must be non-empty strings")
    run = runner or verify_patch
    before = run(original_code, test_code)
    if before["passed"]:
        return {
            "passed": False,
            "feedback": "Test passes on the original code; not a regression test.\n"
            + before["feedback"],
        }
    after = run(patch_code, test_code)
    if not after["passed"]:
        return {"passed": False, "feedback": after["feedback"]}
    return {"passed": True, "feedback": after["feedback"]}
