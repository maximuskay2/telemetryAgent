"""Allowlisted demo-target file resolution (I2).

`target_path` lets a run verify fail-to-pass against the real buggy file
instead of model-invented code. Paths resolve only inside
`demo/target-service/`; anything else is rejected.
"""

from __future__ import annotations

from pathlib import Path

TARGET_DIR = Path(__file__).resolve().parent.parent.parent / "demo" / "target-service"
MAX_TARGET_BYTES = 100_000


def resolve_target_path(target_path: str) -> Path:
    """Return the allowlisted file, or raise ValueError with a readable reason."""
    if not target_path or not target_path.strip():
        raise ValueError("target_path must be a non-empty relative path.")
    candidate = (TARGET_DIR / target_path).resolve()
    allowed = TARGET_DIR.resolve()
    if candidate != allowed and allowed not in candidate.parents:
        raise ValueError(
            f"target_path {target_path!r} is outside the allowlisted directory."
        )
    if not candidate.exists():
        raise ValueError(f"target_path {target_path!r} does not exist.")
    if not candidate.is_file():
        raise ValueError(f"target_path {target_path!r} is not a file.")
    if candidate.stat().st_size > MAX_TARGET_BYTES:
        raise ValueError(f"target_path {target_path!r} exceeds the size limit.")
    return candidate


def read_target_file(target_path: str) -> str:
    """Read an allowlisted target file as text."""
    return resolve_target_path(target_path).read_text(encoding="utf-8")
