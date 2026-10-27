"""Local Docker pytest runner: Day 3 contingency when Modal is unreachable.

Same contract as `sandbox.verify_patch`: `{"passed": bool, "feedback": str}`.
Generated code runs only inside the container, never on the host; without
Docker installed this raises instead of executing anything locally.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile

IMAGE = "python:3.11-slim"
MAX_FEEDBACK_CHARS = 8000


def verify_patch_local(patch_code: str, test_code: str, timeout: int = 120) -> dict:
    """Run a patch + pytest suite inside a throwaway Docker container."""
    if not patch_code or not test_code:
        raise ValueError("patch_code and test_code must be non-empty strings")
    if shutil.which("docker") is None:
        raise RuntimeError(
            "Docker is not installed; cannot run local verification."
        )
    with tempfile.TemporaryDirectory(prefix="ta-verify-") as tmp:
        with open(f"{tmp}/solution.py", "w", encoding="utf-8") as f:
            f.write(patch_code)
        with open(f"{tmp}/test_solution.py", "w", encoding="utf-8") as f:
            f.write(test_code)
        try:
            completed = subprocess.run(
                [
                    "docker", "run", "--rm",
                    "-v", f"{tmp}:/work",
                    "-w", "/work",
                    IMAGE,
                    "sh", "-c", "pip install -q pytest && pytest -q test_solution.py",
                ],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return {
                "passed": False,
                "feedback": f"[local docker] timed out after {timeout}s.",
            }
    feedback = (completed.stderr + completed.stdout)[-MAX_FEEDBACK_CHARS:]
    return {"passed": completed.returncode == 0, "feedback": f"[local docker] {feedback}"}
