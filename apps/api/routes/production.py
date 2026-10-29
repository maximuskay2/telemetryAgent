"""Production connections, ingest and pause routes (James owns this file).

Connections are real (J-R0 store); ingest answers from fixtures until J-R1
and pause until J-R4. Shapes always match §3.4.
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from core.actions.auto_action import mobile_token
from core.connections import auth as key_auth
from core.connections import store as connection_store
from core.schemas.production import (
    FIXTURE_INGEST_RESULT,
    FIXTURE_SENTRY_RESULT,
    FIXTURE_SYSTEM_ID,
    ConnectionCreate,
    ConnectionCreated,
    ConnectionList,
    ConnectionTest,
    EnabledResult,
    IngestLogsIn,
    IngestResult,
    PauseState,
    SentryAccepted,
    TestPermissions,
)
from core.setup import store as setup_store

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


#: Kinds whose secret the customer pastes (no generated key).
PASTED_SECRET_KINDS = ("github", "railway", "webhook")


@router.post("/api/connections", response_model=ConnectionCreated)
async def create_connection(payload: ConnectionCreate) -> ConnectionCreated:
    """Store a connection; a generated key is shown once, never again."""
    known = setup_store.get_profile(payload.system_id) is not None
    fixture_ok = (
        payload.system_id == FIXTURE_SYSTEM_ID
        and key_auth.fixture_keys_allowed()
    )
    if not known and not fixture_ok:
        raise HTTPException(status_code=404, detail="unknown system_id")
    if payload.kind in PASTED_SECRET_KINDS and not (payload.secret or "").strip():
        raise HTTPException(
            status_code=400, detail=f"kind {payload.kind} needs a secret"
        )
    connection, key = connection_store.create_connection(
        payload.system_id, payload.kind, payload.config, payload.secret
    )
    return ConnectionCreated(connection=connection, key=key)


@router.get("/api/connections", response_model=ConnectionList)
async def list_connections(system_id: Optional[str] = None) -> ConnectionList:
    """List connections; secrets are never returned (hint only)."""
    return ConnectionList(
        connections=connection_store.list_connections(system_id)
    )


@router.post(
    "/api/connections/{connection_id}/test", response_model=ConnectionTest
)
async def test_connection(connection_id: str) -> ConnectionTest:
    """J-R0: stored-config check. Live github checks land in J-R2."""
    record = connection_store.get_record(connection_id)
    if record is None:
        raise HTTPException(status_code=404, detail="unknown connection")
    kind = record.get("kind", "")
    config = record.get("config", {}) or {}
    if kind == "github":
        if not str(config.get("repo", "")).strip():
            return ConnectionTest(ok=False, detail="config.repo is missing")
        if not connection_store.get_secret(connection_id):
            return ConnectionTest(ok=False, detail="no token stored")
        return ConnectionTest(
            ok=False,
            detail="stored; live repo/permission checks land in J-R2",
            permissions=TestPermissions(read=False, pull_requests=False),
        )
    return ConnectionTest(ok=True, detail="stored; waiting for first data")


@router.delete("/api/connections/{connection_id}")
async def delete_connection(connection_id: str) -> dict:
    """Delete; the connection's key fails immediately (nothing cached)."""
    if not connection_store.delete_connection(connection_id):
        raise HTTPException(status_code=404, detail="unknown connection")
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
