"""Production connections, ingest and pause routes (H0 stubs).

Every handler returns the §3.4 fixture JSON verbatim so John can build the
app, firmware and `/connect` wizard against stable shapes. Real logic:
J-R0 (connections store), J-R1 (ingest), J-R4 (pause state).
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from core.actions.auto_action import mobile_token
from core.connections import auth as key_auth
from core.schemas.production import (
    FIXTURE_CONNECTION,
    FIXTURE_CONNECTION_TEST,
    FIXTURE_INGEST_RESULT,
    FIXTURE_KEY,
    FIXTURE_SENTRY_RESULT,
    Connection,
    ConnectionCreate,
    ConnectionCreated,
    ConnectionList,
    ConnectionTest,
    EnabledResult,
    IngestLogsIn,
    IngestResult,
    PauseState,
    SentryAccepted,
)

router = APIRouter()


def _connect_enabled() -> bool:
    raw = os.environ.get("PRODUCTION_CONNECT_ENABLED", "1").strip().lower()
    return raw not in ("0", "false", "no", "off", "")


def _require_mobile_token(request: Request) -> None:
    token = mobile_token()
    if not token:
        return
    if request.headers.get("X-Mobile-Token", "") != token:
        raise HTTPException(
            status_code=401, detail="bad or missing mobile token"
        )


def _bearer_key(request: Request) -> str:
    scheme, _, value = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        raise HTTPException(
            status_code=401, detail="missing Bearer [REDACTED] key"
        )
    return value.strip()


@router.get("/api/connections/enabled", response_model=EnabledResult)
async def connections_enabled() -> EnabledResult:
    """Emergency switch for the `/connect` door (John reads, not NEXT_PUBLIC)."""
    return EnabledResult(enabled=_connect_enabled())


@router.post("/api/connections", response_model=ConnectionCreated)
async def create_connection(payload: ConnectionCreate) -> ConnectionCreated:
    connection = Connection.model_validate(
        {**FIXTURE_CONNECTION, "system_id": payload.system_id, "kind": payload.kind}
    )
    return ConnectionCreated(connection=connection, key=FIXTURE_KEY)


@router.get("/api/connections", response_model=ConnectionList)
async def list_connections(system_id: Optional[str] = None) -> ConnectionList:
    _ = system_id
    return ConnectionList(
        connections=[Connection.model_validate(FIXTURE_CONNECTION)]
    )


@router.post(
    "/api/connections/{connection_id}/test", response_model=ConnectionTest
)
async def test_connection(connection_id: str) -> ConnectionTest:
    _ = connection_id
    return ConnectionTest.model_validate(FIXTURE_CONNECTION_TEST)


@router.delete("/api/connections/{connection_id}")
async def delete_connection(connection_id: str) -> dict:
    _ = connection_id
    return {"deleted": True}


@router.post("/api/ingest/logs", response_model=IngestResult)
async def ingest_logs(request: Request, payload: IngestLogsIn) -> IngestResult:
    _ = payload
    if key_auth.system_for_key(_bearer_key(request), "logs") is None:
        raise HTTPException(status_code=401, detail="unknown ingest key")
    return IngestResult.model_validate(FIXTURE_INGEST_RESULT)


@router.post(
    "/api/ingest/sentry/{key}", response_model=SentryAccepted
)
async def ingest_sentry(key: str, payload: dict) -> SentryAccepted:
    _ = payload
    if key_auth.system_for_key(key, "sentry") is None:
        raise HTTPException(status_code=401, detail="unknown sentry key")
    return SentryAccepted.model_validate(FIXTURE_SENTRY_RESULT)


@router.get("/api/actions/pause", response_model=PauseState)
async def get_pause() -> PauseState:
    return PauseState(paused=False)


@router.post("/api/actions/pause", response_model=PauseState)
async def set_pause(request: Request, payload: PauseState) -> PauseState:
    _require_mobile_token(request)
    return PauseState(paused=payload.paused)
