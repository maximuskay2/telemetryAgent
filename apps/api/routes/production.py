"""Production connections, ingest and pause routes (James owns this file).

Connections (J-R0) and ingest (J-R1) are real; pause answers from fixtures
until J-R4. Shapes always match §3.4.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from core.actions.auto_action import mobile_token
from core.connections import auth as key_auth
from core.connections import github as github_conn
from core.connections import store as connection_store
from core.ingest import pipeline as ingest_pipeline
from core.schemas.events import SimEvent
from core.schemas.production import (
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
    """Stored-config check; github gets live repo/permission checks (J-R2)."""
    record = connection_store.get_record(connection_id)
    if record is None:
        raise HTTPException(status_code=404, detail="unknown connection")
    kind = record.get("kind", "")
    config = record.get("config", {}) or {}
    if kind == "github":
        if not str(config.get("repo", "")).strip():
            return ConnectionTest(ok=False, detail="config.repo is missing")
        secret = connection_store.get_secret(connection_id)
        if not secret:
            return ConnectionTest(ok=False, detail="no token stored")
        result = github_conn.check_repo(
            str(config.get("repo", "")),
            secret,
            str(config.get("base_branch", "") or ""),
        )
        return ConnectionTest(
            ok=result["ok"],
            detail=result["detail"],
            permissions=TestPermissions(**result["permissions"]),
        )
    return ConnectionTest(ok=True, detail="stored; waiting for first data")


@router.delete("/api/connections/{connection_id}")
async def delete_connection(connection_id: str) -> dict:
    """Delete; the connection's key fails immediately (nothing cached)."""
    if not connection_store.delete_connection(connection_id):
        raise HTTPException(status_code=404, detail="unknown connection")
    return {"deleted": True}


async def _mark_first_log(connection_id: str, system_id: str) -> None:
    """Flip waiting → ok + emit connection_status on the first delivery."""
    from apps.api.main import hub  # deferred: routers load before main ends

    record = connection_store.get_record(connection_id)
    if record is None:
        return
    first = record.get("status") != "ok"
    connection_store.mark_seen(connection_id)
    if first:
        await hub.broadcast(
            SimEvent(
                kind="connection_status",
                payload={
                    "connection_id": connection_id,
                    "system_id": system_id,
                    "status": "ok",
                    "detail": "first log received",
                },
            )
        )


async def _broadcast_decisions(decisions: list) -> None:
    from apps.api.main import hub  # deferred: routers load before main ends

    for body in decisions:
        await hub.broadcast(SimEvent(kind="gate_decision", payload=body))


@router.post("/api/ingest/logs", response_model=IngestResult)
async def ingest_logs(request: Request, payload: IngestLogsIn) -> IngestResult:
    """Accept forwarder batches; tracebacks become one candidate each."""
    key = _bearer_key(request)
    system_id = key_auth.system_for_key(key, "logs")
    if system_id is None:
        raise HTTPException(status_code=401, detail="unknown ingest key")
    record = connection_store.find_record_for_key(key, "logs")
    result = await ingest_pipeline.process_lines(
        system_id,
        payload.service,
        [line.message for line in payload.lines],
    )
    if record is not None:
        await _mark_first_log(record["id"], system_id)
    await _broadcast_decisions(result["decisions"])
    return IngestResult(
        accepted=result["accepted"], candidates=result["candidates"]
    )


@router.post("/api/ingest/sentry/{key}", response_model=SentryAccepted)
async def ingest_sentry(key: str, payload: dict) -> SentryAccepted:
    """Accept a Sentry issue-alert webhook as one error event."""
    system_id = key_auth.system_for_key(key, "sentry")
    if system_id is None:
        raise HTTPException(status_code=401, detail="unknown sentry key")
    record = connection_store.find_record_for_key(key, "sentry")
    texts = ingest_pipeline.sentry_texts(payload)
    result = await ingest_pipeline.process_lines(system_id, "sentry", texts)
    if record is not None:
        await _mark_first_log(record["id"], system_id)
    await _broadcast_decisions(result["decisions"])
    return SentryAccepted(accepted=1)


@router.get("/forwarder.py", response_class=PlainTextResponse)
async def forwarder_script() -> str:
    """Serve the stdlib-only forwarder for the /connect one-liner."""
    path = (
        Path(__file__).resolve().parent.parent.parent.parent
        / "agent"
        / "ta_forward.py"
    )
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise HTTPException(
            status_code=500, detail="forwarder script missing"
        ) from exc


@router.get("/api/actions/pause", response_model=PauseState)
async def get_pause() -> PauseState:
    return PauseState(paused=False)


@router.post("/api/actions/pause", response_model=PauseState)
async def set_pause(request: Request, payload: PauseState) -> PauseState:
    _require_mobile_token(request)
    return PauseState(paused=payload.paused)
