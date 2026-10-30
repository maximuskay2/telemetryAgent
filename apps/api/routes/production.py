"""Production connections, ingest and pause routes (James owns this file).

Connections (J-R0) and ingest (J-R1) are real; pause answers from fixtures
until J-R4. Shapes always match §3.4.
"""

from __future__ import annotations

import asyncio
import hmac
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from core.actions.auto_action import mobile_token
from core.actions import mitigate as mitigate_actions
from core.connections import auth as key_auth
from core.connections import github as github_conn
from core.connections import store as connection_store
from core.ingest import pipeline as ingest_pipeline
from core.repo_fix import run as repo_fix_run
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


def _connect_code() -> str:
    return os.environ.get("CONNECT_ACCESS_CODE", "").strip()


def _require_connect_access(request: Request) -> None:
    """Door for every connection route: switch first, then access code.

    The instance has no accounts; the code is what stops strangers from
    storing tokens, listing connections or burning model/sandbox budget.
    """
    if not _connect_enabled():
        raise HTTPException(
            status_code=403, detail="connecting is switched off here"
        )
    code = _connect_code()
    if not code:
        return
    given = request.headers.get("X-Connect-Code", "").strip()
    if not hmac.compare_digest(given.encode(), code.encode()):
        raise HTTPException(
            status_code=401, detail="bad or missing access code"
        )


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
    return EnabledResult(
        enabled=_connect_enabled(), code_required=bool(_connect_code())
    )


@router.post("/api/connections/code")
async def check_connect_code(request: Request) -> dict:
    """Lets the wizard check an access code before step 1."""
    _require_connect_access(request)
    return {"ok": True}


#: Kinds whose secret the customer pastes (no generated key).
PASTED_SECRET_KINDS = ("github", "railway", "webhook")


@router.post("/api/connections", response_model=ConnectionCreated)
async def create_connection(
    request: Request, payload: ConnectionCreate
) -> ConnectionCreated:
    """Store a connection; a generated key is shown once, never again."""
    _require_connect_access(request)
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
async def list_connections(
    request: Request, system_id: Optional[str] = None
) -> ConnectionList:
    """List connections; secrets are never returned (hint only)."""
    _require_connect_access(request)
    return ConnectionList(
        connections=connection_store.list_connections(system_id)
    )


@router.post(
    "/api/connections/{connection_id}/test", response_model=ConnectionTest
)
async def test_connection(
    request: Request, connection_id: str
) -> ConnectionTest:
    """Stored-config check; github/railway/webhook get live checks."""
    _require_connect_access(request)
    record = connection_store.get_record(connection_id)
    if record is None:
        raise HTTPException(status_code=404, detail="unknown connection")
    kind = record.get("kind", "")
    config = record.get("config", {}) or {}
    if kind == "railway":
        secret = connection_store.get_secret(connection_id)
        if not secret:
            return await _record_test(
                record, ConnectionTest(ok=False, detail="no token stored")
            )
        result = await asyncio.to_thread(
            mitigate_actions.railway_check,
            secret,
            None,
            str(config.get("service_id", "") or "").strip(),
        )
        return await _record_test(
            record, ConnectionTest(ok=result["ok"], detail=result["detail"])
        )
    if kind == "webhook":
        url = str(config.get("url", "") or "").strip()
        if not url:
            return await _record_test(
                record,
                ConnectionTest(ok=False, detail="config.url is missing"),
            )
        secret = connection_store.get_secret(connection_id)
        if not secret:
            return await _record_test(
                record, ConnectionTest(ok=False, detail="no secret stored")
            )
        result = await asyncio.to_thread(
            mitigate_actions.webhook_ping, url, secret
        )
        return await _record_test(
            record, ConnectionTest(ok=result["ok"], detail=result["detail"])
        )
    if kind == "github":
        if not str(config.get("repo", "")).strip():
            return await _record_test(
                record,
                ConnectionTest(ok=False, detail="config.repo is missing"),
            )
        secret = connection_store.get_secret(connection_id)
        if not secret:
            return await _record_test(
                record, ConnectionTest(ok=False, detail="no token stored")
            )
        result = github_conn.check_repo(
            str(config.get("repo", "")),
            secret,
            str(config.get("base_branch", "") or ""),
        )
        return await _record_test(
            record,
            ConnectionTest(
                ok=result["ok"],
                detail=result["detail"],
                permissions=TestPermissions(**result["permissions"]),
                # Languages §3 (L-J0): GitHub fills these; absent on failure.
                language=result.get("language"),
                autofix=result.get("autofix"),
            ),
        )
    return ConnectionTest(ok=True, detail="stored; waiting for first data")


async def _record_test(record: dict, result: ConnectionTest) -> ConnectionTest:
    """Live-checked kinds have no first delivery; the test sets status."""
    from apps.api.main import hub  # deferred: routers load before main ends

    status = "ok" if result.ok else "error"
    connection_store.mark_seen(record["id"], status, result.detail)
    await hub.broadcast(
        SimEvent(
            kind="connection_status",
            payload={
                "connection_id": record["id"],
                "system_id": record.get("system_id", ""),
                "status": status,
                "detail": result.detail,
            },
        )
    )
    return result


@router.delete("/api/connections/{connection_id}")
async def delete_connection(request: Request, connection_id: str) -> dict:
    """Delete; the connection's key fails immediately (nothing cached)."""
    _require_connect_access(request)
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
        commit=payload.commit,
    )
    if record is not None:
        await _mark_first_log(record["id"], system_id)
    await _broadcast_decisions(result["decisions"])
    # J-R3: armed production tracebacks with a repo connection start a
    # background repo-fix run; the response never waits for it.
    await repo_fix_run.maybe_trigger(
        system_id, result["decisions"], payload.commit
    )
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
    await repo_fix_run.maybe_trigger(system_id, result["decisions"], "")
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
    return PauseState(paused=mitigate_actions.is_paused())


@router.post("/api/actions/pause", response_model=PauseState)
async def set_pause(request: Request, payload: PauseState) -> PauseState:
    """Global kill switch (persisted) + `actions_paused` broadcast."""
    from apps.api.main import hub  # deferred: routers load before main ends

    if os.environ.get("DATABASE_URL", "").strip():
        # Hosted (C-J2): admin+ decides; still global until C-J3 per-org.
        from core.commerce import auth as auth_module

        ctx = getattr(request.state, "auth", None)
        if ctx is None or not ctx.user_id:
            raise HTTPException(status_code=401, detail="sign-in required")
        try:
            auth_module.require_roles(ctx, "admin")
        except auth_module.AuthError as exc:
            raise HTTPException(
                status_code=exc.status, detail=exc.detail
            ) from exc
    else:
        _require_mobile_token(request)
    paused = mitigate_actions.set_paused(payload.paused)
    await hub.broadcast(
        SimEvent(kind="actions_paused", payload={"paused": paused})
    )
    return PauseState(paused=paused)
