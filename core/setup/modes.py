"""Operating modes (P4): deploying, defrost, maintenance, and the like.

A mode relaxes parts of a profile for a bounded time. It comes from three
places: the device reports it (fridge readings carry `mode`), a human or the
pipeline sets it (`POST /api/systems/{id}/mode`), or the profile schedule
implies it. Every mode has a max duration from the profile; an overrun mode
is an anomaly itself, never a blanket excuse.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from core.schemas.profile import SystemProfile

#: Manual modes live here (runtime state, like pending veto windows). A
#: restart clears them, which fails safe: no relaxations apply.
_manual_modes: dict[str, dict] = {}

#: First-seen time per (system, device mode), for overrun detection.
_device_since: dict[str, tuple[str, float]] = {}


@dataclass
class ModeState:
    mode: str = ""
    source: str = ""  # "manual" | "device" | ""
    since: float = 0.0
    until: Optional[float] = None
    max_duration_s: float = 0.0
    overrun: bool = False


def set_mode(
    system_id: str,
    mode: str,
    duration_s: Optional[float] = None,
    until: Optional[float] = None,
    now: Optional[float] = None,
) -> dict:
    """Human/pipeline mode set; empty mode clears. Returns the record."""
    if not mode:
        _manual_modes.pop(system_id, None)
        return {"mode": "", "source": "manual"}
    at = now if now is not None else time.time()
    record = {
        "mode": mode,
        "source": "manual",
        "since": at,
        "until": until if until is not None else (
            at + duration_s if duration_s else None
        ),
    }
    _manual_modes[system_id] = record
    return record


def _profile_max(profile: Optional[SystemProfile], mode: str) -> float:
    if profile is None:
        return 0.0
    for entry in profile.modes:
        if entry.mode == mode:
            return entry.max_duration_s
    return 0.0


def current_mode(
    system_id: str,
    profile: Optional[SystemProfile] = None,
    device_mode: str = "",
    now: Optional[float] = None,
) -> ModeState:
    """Resolve the effective mode: manual beats device; expiry clears."""
    at = now if now is not None else time.time()
    record = _manual_modes.get(system_id)
    if record is not None:
        until = record.get("until")
        if until is not None and at >= until:
            _manual_modes.pop(system_id, None)
            record = None
    if record is not None and record.get("mode"):
        state = ModeState(
            mode=record["mode"],
            source="manual",
            since=record.get("since", at),
            until=record.get("until"),
        )
    elif device_mode:
        seen = _device_since.get(system_id)
        if seen is None or seen[0] != device_mode:
            seen = (device_mode, at)
            _device_since[system_id] = seen
        state = ModeState(mode=device_mode, source="device", since=seen[1])
    else:
        _device_since.pop(system_id, None)
        return ModeState()
    state.max_duration_s = _profile_max(profile, state.mode)
    if state.max_duration_s > 0 and at - state.since > state.max_duration_s:
        state.overrun = True
    return state


def clear_all() -> None:
    """Test helper: drop every manual mode."""
    _manual_modes.clear()
    _device_since.clear()
