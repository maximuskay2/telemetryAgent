from __future__ import annotations

import os


async def run_in_modal(command: list[str]) -> str:
    """Run a caller-provided command in an ephemeral Modal sandbox."""
    if not command or not all(isinstance(part, str) and part for part in command):
        raise ValueError("command must be a non-empty list of strings")
    if os.getenv("MODAL_ENABLED", "").lower() != "true":
        raise RuntimeError("Modal execution is disabled; set MODAL_ENABLED=true to enable it.")

    try:
        import modal
    except ImportError as exc:
        raise RuntimeError("Install the optional Modal dependency to use sandbox execution.") from exc

    image = modal.Image.debian_slim().pip_install()
    sandbox = modal.Sandbox.create(*command, image=image, timeout=30)
    try:
        stdout = sandbox.stdout.read()
        stderr = sandbox.stderr.read()
        return stdout + (f"\n{stderr}" if stderr else "")
    finally:
        sandbox.terminate()
