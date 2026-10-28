"""Versioned SystemProfile storage (P0).

Current profile: `data/profiles/<system_id>.json`. Every save bumps
`version` and keeps an audit snapshot at
`data/profiles/versions/<system_id>.v<version>.json`. Uploaded documents
live under `data/uploads/<system_id>/`. All gitignored. `TA_DATA_DIR`
overrides the root (tests use a tmp dir).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from core.schemas.profile import SystemProfile


def data_root() -> Path:
    override = os.environ.get("TA_DATA_DIR", "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent.parent / "data"


def profiles_dir() -> Path:
    return data_root() / "profiles"


def versions_dir() -> Path:
    return profiles_dir() / "versions"


def uploads_dir(system_id: str) -> Path:
    return data_root() / "uploads" / system_id


def profile_path(system_id: str) -> Path:
    return profiles_dir() / f"{system_id}.json"


def get_profile(system_id: str) -> Optional[SystemProfile]:
    path = profile_path(system_id)
    if not path.exists():
        return None
    return SystemProfile.model_validate_json(path.read_text(encoding="utf-8"))


def list_profiles() -> list[SystemProfile]:
    root = profiles_dir()
    if not root.exists():
        return []
    profiles = []
    for path in sorted(root.glob("*.json")):
        try:
            profiles.append(
                SystemProfile.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
            )
        except ValueError:
            continue
    return profiles


def save_profile(profile: SystemProfile) -> SystemProfile:
    """Persist, bumping the version; keep the previous snapshot for audit."""
    # Re-validate through the read path before writing: model_copy(update=..)
    # skips validation, so without this a status flip could persist a profile
    # that no endpoint can ever read back (stuck learning + 500s everywhere).
    SystemProfile.model_validate(profile.model_dump(mode="json"))
    current = get_profile(profile.system_id)
    version = (current.version + 1) if current is not None else 1
    stored = profile.model_copy(update={"version": version})
    payload = stored.model_dump_json(indent=2)
    profiles_dir().mkdir(parents=True, exist_ok=True)
    versions_dir().mkdir(parents=True, exist_ok=True)
    profile_path(profile.system_id).write_text(payload, encoding="utf-8")
    (versions_dir() / f"{profile.system_id}.v{version}.json").write_text(
        payload, encoding="utf-8"
    )
    return stored


def get_version(system_id: str, version: int) -> Optional[SystemProfile]:
    path = versions_dir() / f"{system_id}.v{version}.json"
    if not path.exists():
        return None
    return SystemProfile.model_validate_json(path.read_text(encoding="utf-8"))


def conflicts_path(system_id: str) -> Path:
    return profiles_dir() / f"{system_id}.conflicts.json"


def save_conflicts(system_id: str, conflicts: list) -> None:
    profiles_dir().mkdir(parents=True, exist_ok=True)
    conflicts_path(system_id).write_text(
        json.dumps(conflicts, indent=2), encoding="utf-8"
    )


def feedback_path(system_id: str) -> Path:
    return profiles_dir() / f"{system_id}.feedback.json"


def get_feedback(system_id: str) -> list:
    """Pending + decided 'mark as normal' items (P8); [] when none."""
    path = feedback_path(system_id)
    if not path.exists():
        return []
    try:
        items = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return []
    return items if isinstance(items, list) else []


def save_feedback(system_id: str, items: list) -> None:
    profiles_dir().mkdir(parents=True, exist_ok=True)
    feedback_path(system_id).write_text(
        json.dumps(items, indent=2), encoding="utf-8"
    )


def get_conflicts(system_id: str) -> list:
    path = conflicts_path(system_id)
    if not path.exists():
        return []
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return []
    return loaded if isinstance(loaded, list) else []
