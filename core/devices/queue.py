"""In-memory device command queue (John, N-R1).

Ephemeral by design (commands expire after 2 minutes), so — like the run
stores in `apps/api/main.py` — it lives in memory, not on disk. All entry
points take an optional `now` epoch for deterministic tests.
"""

from __future__ import annotations

import time
from typing import Optional
from uuid import uuid4

#: A command the device never picks up expires (roadmap §4 N-R1).
COMMAND_TTL_S = 120

#: Hygiene bound, mirroring `_MAX_STORED_RUNS` in the API.
_MAX_COMMANDS = 500
_MAX_OPTION_STATUSES = 500

_COMMANDS: dict[str, dict] = {}
_OPTION_STATUS: dict[tuple[str, str], dict] = {}
#: Latest sighting per system: readings and polls prove which device id a
#: system's key currently serves (execute queues under it).
_DEVICE_BY_SYSTEM: dict[str, dict] = {}


def reset() -> None:
    """Clear all queue state (tests only)."""
    _COMMANDS.clear()
    _OPTION_STATUS.clear()
    _DEVICE_BY_SYSTEM.clear()


def _prune(now: float) -> None:
    if len(_COMMANDS) > _MAX_COMMANDS:
        ordered = sorted(
            _COMMANDS.values(), key=lambda entry: entry["created_at"]
        )
        for entry in ordered[: len(_COMMANDS) - _MAX_COMMANDS]:
            _COMMANDS.pop(entry["id"], None)
    if len(_OPTION_STATUS) > _MAX_OPTION_STATUSES:
        ordered = sorted(
            _OPTION_STATUS.items(), key=lambda item: item[1]["updated_at"]
        )
        for key, _ in ordered[: len(_OPTION_STATUS) - _MAX_OPTION_STATUSES]:
            _OPTION_STATUS.pop(key, None)


def enqueue(
    device_id: str,
    run_id: str,
    option_id: str,
    action: str,
    params: Optional[dict] = None,
    now: Optional[float] = None,
) -> dict:
    """Queue one device command; returns the stored entry."""
    now = time.time() if now is None else now
    entry = {
        "id": f"cmd_{uuid4().hex[:8]}",
        "device_id": device_id,
        "run_id": run_id,
        "option_id": option_id,
        "action": action,
        "params": dict(params or {}),
        "created_at": now,
        "expires_at": now + COMMAND_TTL_S,
        "status": "sent",
        "detail": "",
    }
    _COMMANDS[entry["id"]] = entry
    set_option_status(run_id, option_id, "sent", "", now)
    _prune(now)
    return entry


def _sweep(now: float) -> None:
    for entry in _COMMANDS.values():
        if entry["status"] == "sent" and now > entry["expires_at"]:
            entry["status"] = "expired"
            entry["detail"] = "device offline — no ack in time"
            set_option_status(
                entry["run_id"],
                entry["option_id"],
                "expired",
                entry["detail"],
                now,
            )


def pending_for(device_id: str, now: Optional[float] = None) -> list[dict]:
    """Unacked, unexpired commands for one device (§3.4 command shape)."""
    now = time.time() if now is None else now
    _sweep(now)
    return [
        {
            "id": entry["id"],
            "action": entry["action"],
            "params": dict(entry["params"]),
            "expires_at": entry["expires_at"],
        }
        for entry in _COMMANDS.values()
        if entry["device_id"] == device_id and entry["status"] == "sent"
    ]


def get(command_id: str) -> Optional[dict]:
    """One command entry by id, or None."""
    return _COMMANDS.get(command_id)


def ack(
    command_id: str,
    ok: bool,
    detail: str = "",
    now: Optional[float] = None,
) -> Optional[dict]:
    """Record a device ack; terminal states are sticky (idempotent)."""
    now = time.time() if now is None else now
    _sweep(now)
    entry = _COMMANDS.get(command_id)
    if entry is None:
        return None
    if entry["status"] != "sent":
        return entry
    entry["status"] = "done" if ok else "failed"
    entry["detail"] = detail
    set_option_status(
        entry["run_id"], entry["option_id"], entry["status"], detail, now
    )
    return entry


def set_option_status(
    run_id: str,
    option_id: str,
    status: str,
    detail: str = "",
    now: Optional[float] = None,
) -> None:
    """Remember a non-device lifecycle event (manual/dispatch execute)."""
    now = time.time() if now is None else now
    _OPTION_STATUS[(run_id, option_id)] = {
        "status": status,
        "detail": detail,
        "updated_at": now,
    }


def option_statuses(run_id: str) -> dict[str, dict]:
    """Latest lifecycle state per option id for one run."""
    return {
        option_id: {"status": item["status"], "detail": item["detail"]}
        for (stored_run_id, option_id), item in _OPTION_STATUS.items()
        if stored_run_id == run_id
    }


def active_command(
    run_id: str, option_id: str, now: Optional[float] = None
) -> Optional[dict]:
    """Latest still-pending command for one option, or None."""
    now = time.time() if now is None else now
    _sweep(now)
    for entry in _COMMANDS.values():
        if (
            entry["run_id"] == run_id
            and entry["option_id"] == option_id
            and entry["status"] == "sent"
        ):
            return entry
    return None


def note_device_seen(
    system_id: str, device_id: str, now: Optional[float] = None
) -> None:
    """Record that a system's key served this device id (latest wins)."""
    now = time.time() if now is None else now
    _DEVICE_BY_SYSTEM[system_id] = {"device_id": device_id, "seen_at": now}


def device_for_system(system_id: str) -> Optional[str]:
    """Device id to queue under for a system, or None when never seen."""
    sighting = _DEVICE_BY_SYSTEM.get(system_id)
    return sighting["device_id"] if sighting else None
