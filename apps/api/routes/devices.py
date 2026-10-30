"""Incident options + device command queue (John, N-R1).

Software runs get their options from `mitigate.software_options()` ([] until
James's R4); appliance runs get remote/manual/dispatch options built from
the stored run's runbook + profile (`core.devices.options`). Remote executes
queue a 2-minute device command; manual/dispatch executes resolve at once.
`POST /api/devices/{id}/readings` is the keyed alias of the (untouched)
`/api/telemetry/appliance` endpoint for production devices.
"""

from __future__ import annotations

import time
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from core.actions import mitigate
from core.actions.auto_action import mobile_token
from core.connections import auth as key_auth
from core.connections import store as connection_store
from core.devices import options as device_options
from core.devices import queue as device_queue
from core.schemas.events import SimEvent
from core.schemas.production import (
    AckResult,
    CommandAck,
    CommandList,
    DeviceCommand,
    Option,
    OptionExecuted,
    OptionsResult,
)
from core.setup import store as setup_store

router = APIRouter()

#: First-viewed epoch per run: `started_at` for entries that predate the
#: stamp (power-cycle delay anchor; entry values always win when present).
_RUN_FIRST_SEEN: dict[str, float] = {}
_MAX_FIRST_SEEN = 500


def _require_mobile_token(request: Request) -> None:
    token = mobile_token()
    if not token:
        return
    if request.headers.get("X-Mobile-Token", "") != token:
        raise HTTPException(
            status_code=401, detail="bad or missing mobile token"
        )


def _require_device_key(request: Request, device_id: str) -> str:
    scheme, _, value = request.headers.get("Authorization", "").partition(" ")
    system_id = (
        key_auth.system_for_key(value.strip(), "device")
        if scheme.lower() == "bearer" and value.strip()
        else None
    )
    if system_id is None:
        raise HTTPException(status_code=401, detail="unknown device key")
    _ = device_id
    return system_id


def _api_main():
    import apps.api.main as api_main

    return api_main


def _find_run(run_id: str):
    """(domain, stored entry) or (None, None) for an unknown run."""
    api_main = _api_main()
    if run_id in api_main.software_runs:
        return "software", api_main.software_runs[run_id]
    if run_id in api_main.appliance_runs:
        return "appliance", api_main.appliance_runs[run_id]
    return None, None


def _system_id_for(entry: dict) -> str:
    gate = entry.get("gate") or {}
    return str(gate.get("system_id") or "")


def _profile_for(entry: dict):
    system_id = _system_id_for(entry)
    if not system_id:
        return None
    try:
        return setup_store.get_profile(system_id)
    except Exception:
        return None


def _run_view(run_id: str, entry: dict, now: float) -> dict:
    run = dict(entry)
    run.setdefault("run_id", run_id)
    if not isinstance(run.get("started_at"), (int, float)):
        seen = _RUN_FIRST_SEEN.get(run_id)
        if seen is None:
            seen = now
            _RUN_FIRST_SEEN[run_id] = seen
            if len(_RUN_FIRST_SEEN) > _MAX_FIRST_SEEN:
                oldest = list(_RUN_FIRST_SEEN)[
                    : len(_RUN_FIRST_SEEN) - _MAX_FIRST_SEEN
                ]
                for key in oldest:
                    del _RUN_FIRST_SEEN[key]
        run["started_at"] = seen
    return run


def _appliance_options(run_id: str, entry: dict, now: float) -> list[Option]:
    profile = _profile_for(entry)
    run = _run_view(run_id, entry, now)
    return [
        Option.model_validate(option)
        for option in device_options.build_appliance_options(
            run, profile, now
        )
    ]


def _software_options(entry: dict) -> list[Option]:
    return [
        Option.model_validate(option)
        for option in mitigate.software_options(entry)
    ]


def _with_statuses(
    run_id: str, options: list[Option]
) -> list[Option]:
    statuses = device_queue.option_statuses(run_id)
    for option in options:
        item = statuses.get(option.id)
        if item is not None:
            option.status = item["status"]
    return options


async def _broadcast_connection(
    connection_id: str, system_id: str, detail: str
) -> None:
    api_main = _api_main()
    await api_main.hub.broadcast(
        SimEvent(
            kind="connection_status",
            payload={
                "connection_id": connection_id,
                "system_id": system_id,
                "status": "ok",
                "detail": detail,
            },
        )
    )


async def _broadcast_option(
    run_id: str, option_id: str, status: str, detail: str
) -> None:
    api_main = _api_main()
    await api_main.hub.broadcast(
        SimEvent(
            kind="option_status",
            payload={
                "run_id": run_id,
                "option_id": option_id,
                "status": status,
                "detail": detail,
            },
        )
    )


@router.get(
    "/api/incidents/{run_id}/options", response_model=OptionsResult
)
async def incident_options(run_id: str) -> OptionsResult:
    domain, entry = _find_run(run_id)
    if entry is None or domain is None:
        raise HTTPException(status_code=404, detail="unknown run_id")
    if domain == "software":
        options = _with_statuses(run_id, _software_options(entry))
    else:
        options = _with_statuses(
            run_id, _appliance_options(run_id, entry, time.time())
        )
    return OptionsResult(run_id=run_id, domain=domain, options=options)


@router.post(
    "/api/incidents/{run_id}/options/{option_id}/execute",
    response_model=OptionExecuted,
)
async def execute_option(
    request: Request, run_id: str, option_id: str
) -> OptionExecuted:
    _require_mobile_token(request)
    if mitigate.is_paused():
        raise HTTPException(status_code=409, detail="actions paused")
    domain, entry = _find_run(run_id)
    if entry is None or domain is None:
        raise HTTPException(status_code=404, detail="unknown run_id")
    now = time.time()
    if domain == "software":
        options = _software_options(entry)
    else:
        options = _appliance_options(run_id, entry, now)
    option = next(
        (item for item in options if item.id == option_id), None
    )
    if option is None:
        raise HTTPException(status_code=404, detail="unknown option_id")
    if not option.safety.ok:
        raise HTTPException(
            status_code=409, detail=option.safety.reason or "option unsafe"
        )
    current = device_queue.option_statuses(run_id).get(option_id, {})
    if current.get("status") in ("done", "cancelled"):
        return OptionExecuted(status=current["status"], command_id="")
    if current.get("status") == "sent":
        active = device_queue.active_command(run_id, option_id, now)
        if active is not None:
            return OptionExecuted(status="sent", command_id=active["id"])

    if option.kind in ("manual", "dispatch"):
        device_queue.set_option_status(run_id, option_id, "done", "", now)
        await _broadcast_option(run_id, option_id, "done", "")
        return OptionExecuted(status="done", command_id="")
    if option.kind == "open_pr":
        # The PR already exists; the phone opens its URL directly.
        return OptionExecuted(status="done", command_id="")
    if option.kind in ("rollback", "restart"):
        result = mitigate.execute(
            _system_id_for(entry), option.kind, run_id
        )
        status = str(result.get("status", "failed"))
        detail = str(result.get("reason", result.get("detail", "")))
        if status in ("refused", "denied", "failed", "error"):
            raise HTTPException(
                status_code=409, detail=detail or f"{option.kind} refused"
            )
        device_queue.set_option_status(run_id, option_id, status, detail, now)
        await _broadcast_option(run_id, option_id, status, detail)
        return OptionExecuted(
            status=status, command_id=str(result.get("command_id", ""))
        )
    if option.kind == "remote":
        profile = _profile_for(entry)
        run = _run_view(run_id, entry, now)
        command = device_options.device_command_for(
            option_id, run, profile, now
        )
        if command is None:
            raise HTTPException(
                status_code=409, detail="option no longer safe"
            )
        device_id = device_queue.device_for_system(_system_id_for(entry))
        if device_id is None:
            raise HTTPException(
                status_code=409,
                detail="no device linked to this system yet",
            )
        queued = device_queue.enqueue(
            device_id,
            run_id,
            option_id,
            command["action"],
            command["params"],
            now,
        )
        await _broadcast_option(run_id, option_id, "sent", "")
        return OptionExecuted(status="sent", command_id=queued["id"])
    raise HTTPException(
        status_code=400, detail=f"cannot execute {option.kind}"
    )


@router.get(
    "/api/devices/{device_id}/commands", response_model=CommandList
)
async def device_commands(request: Request, device_id: str) -> CommandList:
    system_id = _require_device_key(request, device_id)
    device_queue.note_device_seen(system_id, device_id, time.time())
    if mitigate.is_paused():
        return CommandList(commands=[])
    pending = device_queue.pending_for(device_id, time.time())
    return CommandList(
        commands=[DeviceCommand.model_validate(item) for item in pending]
    )


@router.post(
    "/api/devices/{device_id}/commands/{command_id}/ack",
    response_model=AckResult,
)
async def ack_command(
    request: Request, device_id: str, command_id: str, payload: CommandAck
) -> AckResult:
    _require_device_key(request, device_id)
    entry = device_queue.get(command_id)
    if entry is None or entry["device_id"] != device_id:
        raise HTTPException(status_code=404, detail="unknown command")
    result = device_queue.ack(
        command_id, payload.ok, payload.detail, time.time()
    )
    assert result is not None
    await _broadcast_option(
        result["run_id"], result["option_id"], result["status"],
        payload.detail,
    )
    return AckResult(status=result["status"])


class DeviceReadingIn(BaseModel):
    """Keyed readings body: TelemetryIngestIn minus source_id (the path
    device id) and system_id (resolved from the device key)."""

    appliance_type: Literal["fridge", "freezer"] = "fridge"
    temperature_c: float
    current_a: float = Field(ge=0)
    vibration_g: float = Field(default=0.0, ge=0)
    door_open: bool = False
    ambient_c: Optional[float] = Field(
        default=None, description="Ambient reference; display only"
    )


@router.post("/api/devices/{device_id}/readings")
async def device_readings(
    request: Request, device_id: str, payload: DeviceReadingIn
) -> dict:
    system_id = _require_device_key(request, device_id)
    device_queue.note_device_seen(system_id, device_id, time.time())
    scheme, _, value = request.headers.get("Authorization", "").partition(" ")
    record = (
        connection_store.find_record_for_key(value.strip(), "device")
        if scheme.lower() == "bearer" and value.strip()
        else None
    )
    if record is not None:
        first = record.get("status") != "ok"
        connection_store.mark_seen(record["id"])
        if first:
            await _broadcast_connection(
                record["id"], system_id, "first reading received"
            )
    api_main = _api_main()
    ingest = api_main.TelemetryIngestIn(
        source_id=device_id,
        system_id=system_id,
        appliance_type=payload.appliance_type,
        temperature_c=payload.temperature_c,
        current_a=payload.current_a,
        vibration_g=payload.vibration_g,
        door_open=payload.door_open,
        ambient_c=payload.ambient_c,
    )
    result = await api_main.ingest_appliance_reading(ingest)
    return {**result, "device_id": device_id, "system_id": system_id}
