"""Local Docker pytest runner: verification when Modal is unreachable.

Same contract as `sandbox.verify_patch`: `{"passed": bool, "feedback": str}`.
Generated code runs only inside a throwaway container, never on the host. The
container is network-isolated with baked-in pytest, capped memory/CPU/PIDs, a
read-only source mount, and no persistent state. Without a Docker binary this
raises instead of executing anything locally.

Setup (once per machine):
    ./scripts/build-sandbox-image.sh
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

IMAGE = os.environ.get("TA_SANDBOX_IMAGE", "telemetry-agent-sandbox")
MAX_FEEDBACK_CHARS = 8000

# Docker Desktop on macOS links the CLI outside PATH; check there too.
_DESKTOP_PATHS = (
    "~/.docker/bin/docker",
    "/usr/local/bin/docker",
    "/opt/homebrew/bin/docker",
)


def resolve_docker() -> str | None:
    """Locate the docker CLI: DOCKER_BIN, PATH, then Desktop locations."""
    explicit = os.environ.get("DOCKER_BIN")
    if explicit:
        if os.path.isfile(explicit) and os.access(explicit, os.X_OK):
            return explicit
        return None
    found = shutil.which("docker")
    if found:
        return found
    for candidate in _DESKTOP_PATHS:
        path = os.path.expanduser(candidate)
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


def verify_patch_local(patch_code: str, test_code: str, timeout: int = 120) -> dict:
    """Run a patch + pytest suite inside a throwaway Docker container."""
    if not patch_code or not test_code:
        raise ValueError("patch_code and test_code must be non-empty strings")
    from core.schemas.remediation import normalize_code

    patch_code = normalize_code(patch_code)
    test_code = normalize_code(test_code)
    docker = resolve_docker()
    if docker is None:
        raise RuntimeError(
            "Docker is not installed; cannot run local verification."
        )
    with tempfile.TemporaryDirectory(prefix="ta-verify-") as tmp:
        with open(f"{tmp}/solution.py", "w", encoding="utf-8") as f:
            f.write(patch_code)
        with open(f"{tmp}/test_solution.py", "w", encoding="utf-8") as f:
            f.write(test_code)
        env = dict(os.environ)
        bindir = os.path.dirname(docker)
        if bindir:
            # Credential helpers live beside off-PATH Desktop CLIs.
            env["PATH"] = f"{bindir}:{env.get('PATH', '')}"
        try:
            completed = subprocess.run(
                [
                    docker, "run", "--rm",
                    "--network", "none",
                    "--read-only",
                    "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
                    "--memory", "512m", "--memory-swap", "512m",
                    "--cpus", "1.0",
                    "--pids-limit", "64",
                    "-v", f"{tmp}:/work:ro",
                    "-w", "/work",
                    "-e", "PYTHONDONTWRITEBYTECODE=1",
                    "-e", "HOME=/tmp",
                    IMAGE,
                    "pytest", "-q", "-p", "no:cacheprovider",
                    "test_solution.py",
                ],
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
        except subprocess.TimeoutExpired:
            return {
                "passed": False,
                "feedback": f"[local docker] timed out after {timeout}s.",
            }
    output = completed.stderr + completed.stdout
    if "Unable to find image" in output:
        return {
            "passed": False,
            "feedback": (
                f"[local docker] image '{IMAGE}' is missing; "
                "run ./scripts/build-sandbox-image.sh first."
            ),
        }
    feedback = output[-MAX_FEEDBACK_CHARS:]
    return {"passed": completed.returncode == 0, "feedback": f"[local docker] {feedback}"}
