"""Incident options + device command queue (H0 stubs).

James writes the stubs; after the `contracts-in` tag this file is John's
(N-R1 fills the real options, queue, expiry and readings alias).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from core.actions.auto_action import mobile_token
from core.connections import auth as key_auth
from core.schemas.production import (
    FIXTURE_DEVICE_COMMAND,
    FIXTURE_OPTION,
    AckResult,
    CommandAck,
    CommandList,
    DeviceCommand,
    Option,
    OptionExecuted,
    OptionsResult,
)

router = APIRouter()


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


@router.get(
    "/api/incidents/{run_id}/options", response_model=OptionsResult
)
async def incident_options(run_id: str) -> OptionsResult:
    return OptionsResult(
        run_id=run_id,
        domain="software",
        options=[Option.model_validate(FIXTURE_OPTION)],
    )


@router.post(
    "/api/incidents/{run_id}/options/{option_id}/execute",
    response_model=OptionExecuted,
)
async def execute_option(
    request: Request, run_id: str, option_id: str
) -> OptionExecuted:
    _require_mobile_token(request)
    _ = (run_id, option_id)
    return OptionExecuted(status="sent", command_id="cmd_1")


@router.get(
    "/api/devices/{device_id}/commands", response_model=CommandList
)
async def device_commands(request: Request, device_id: str) -> CommandList:
    _require_device_key(request, device_id)
    return CommandList(
        commands=[DeviceCommand.model_validate(FIXTURE_DEVICE_COMMAND)]
    )


@router.post(
    "/api/devices/{device_id}/commands/{command_id}/ack",
    response_model=AckResult,
)
async def ack_command(
    request: Request, device_id: str, command_id: str, payload: CommandAck
) -> AckResult:
    _require_device_key(request, device_id)
    _ = (command_id, payload)
    return AckResult(status="done")
