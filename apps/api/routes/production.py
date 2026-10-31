"""Production connections, ingest and pause routes (James owns this file).

Connections (J-R0) and ingest (J-R1) are real; pause answers from fixtures
until J-R4. Shapes always match §3.4.
"""

from __future__ import annotations

import asyncio
import hmac
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

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


def _hosted() -> bool:
    from core.commerce import auth as auth_module

    return auth_module.hosted()


def _need(request: Request, *roles: str):
    from core.commerce import auth as auth_module

    try:
        return auth_module.need(request, *roles)
    except auth_module.AuthError as exc:
        raise HTTPException(
            status_code=exc.status, detail=exc.detail
        ) from exc


def _conn_store(org_id: str):
    """Connection store: org Postgres hosted, files otherwise."""
    from core.commerce import repo as repo_module

    if org_id and _hosted():
        return repo_module.PostgresBackend().scoped(org_id)
    return repo_module.FileBackend()


def _usage(org_id: str, kind: str, **fields) -> None:
    if not org_id or not _hosted():
        return
    try:
        from core.commerce import usage as usage_module

        usage_module.record_usage(org_id, kind, **fields)
    except Exception as exc:
        logger.warning("usage hook skipped: %s", exc)


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
    if _hosted():
        ctx = _need(request, "admin")
        return await _create_connection_hosted(ctx.org_id, payload)
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


async def _create_connection_hosted(
    org_id: str, payload: ConnectionCreate
) -> ConnectionCreated:
    from core.commerce import repo as repo_module

    store = _conn_store(org_id)
    known = await asyncio.to_thread(
        repo_module.get_profile, payload.system_id, org_id
    ) is not None
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
    connection, key = await asyncio.to_thread(
        store.create_connection,
        org_id,
        payload.system_id,
        payload.kind,
        dict(payload.config or {}),
        payload.secret,
    )
    return ConnectionCreated(connection=connection, key=key)


@router.get("/api/connections", response_model=ConnectionList)
async def list_connections(
    request: Request, system_id: Optional[str] = None
) -> ConnectionList:
    """List connections; secrets are never returned (hint only)."""
    if _hosted():
        ctx = _need(request)  # any member reads (viewer included)
        store = _conn_store(ctx.org_id)
        rows = await asyncio.to_thread(
            store.list_connections, ctx.org_id, system_id
        )
        return ConnectionList(connections=rows)
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
    if _hosted():
        ctx = _need(request, "admin")
        return await _test_connection_hosted(ctx.org_id, connection_id)
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


async def _test_connection_hosted(
    org_id: str, connection_id: str
) -> ConnectionTest:
    """Same checks against the org's Postgres rows (decrypted in-process)."""
    store = _conn_store(org_id)
    record = await asyncio.to_thread(
        store.get_connection, org_id, connection_id
    )
    if record is None:
        raise HTTPException(status_code=404, detail="unknown connection")
    kind = record.get("kind", "")
    config = record.get("config", {}) or {}
    secret = await asyncio.to_thread(
        store.get_connection_secret, org_id, connection_id
    )
    if kind == "railway":
        if not secret:
            return await _record_test(
                record, ConnectionTest(ok=False, detail="no token stored"),
                org_id,
            )
        result = await asyncio.to_thread(
            mitigate_actions.railway_check,
            secret,
            None,
            str(config.get("service_id", "") or "").strip(),
        )
        return await _record_test(
            record, ConnectionTest(ok=result["ok"], detail=result["detail"]),
            org_id,
        )
    if kind == "webhook":
        url = str(config.get("url", "") or "").strip()
        if not url:
            return await _record_test(
                record,
                ConnectionTest(ok=False, detail="config.url is missing"),
                org_id,
            )
        if not secret:
            return await _record_test(
                record, ConnectionTest(ok=False, detail="no secret stored"),
                org_id,
            )
        result = await asyncio.to_thread(
            mitigate_actions.webhook_ping, url, secret
        )
        return await _record_test(
            record, ConnectionTest(ok=result["ok"], detail=result["detail"]),
            org_id,
        )
    if kind == "github":
        if not str(config.get("repo", "")).strip():
            return await _record_test(
                record,
                ConnectionTest(ok=False, detail="config.repo is missing"),
                org_id,
            )
        if not secret:
            return await _record_test(
                record, ConnectionTest(ok=False, detail="no token stored"),
                org_id,
            )
        result = await asyncio.to_thread(
            github_conn.check_repo,
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
                language=result.get("language"),
                autofix=result.get("autofix"),
            ),
            org_id,
        )
    return ConnectionTest(ok=True, detail="stored; waiting for first data")


async def _record_test(
    record: dict, result: ConnectionTest, org_id: str = ""
) -> ConnectionTest:
    """Live-checked kinds have no first delivery; the test sets status."""
    from apps.api.main import emit_for  # deferred: main loads last

    status = "ok" if result.ok else "error"
    if _hosted():
        store = _conn_store(org_id)
        await asyncio.to_thread(
            store.mark_connection_seen,
            org_id,
            record["id"],
            status,
            result.detail,
        )
    else:
        connection_store.mark_seen(record["id"], status, result.detail)
    await emit_for(
        org_id,
        SimEvent(
            kind="connection_status",
            payload={
                "connection_id": record["id"],
                "system_id": record.get("system_id", ""),
                "status": status,
                "detail": result.detail,
            },
        ),
    )
    return result


@router.delete("/api/connections/{connection_id}")
async def delete_connection(request: Request, connection_id: str) -> dict:
    """Delete; the connection's key fails immediately (nothing cached)."""
    if _hosted():
        ctx = _need(request, "admin")
        store = _conn_store(ctx.org_id)
        ok = await asyncio.to_thread(
            store.delete_connection, ctx.org_id, connection_id
        )
        if not ok:
            raise HTTPException(status_code=404, detail="unknown connection")
        return {"deleted": True}
    _require_connect_access(request)
    if not connection_store.delete_connection(connection_id):
        raise HTTPException(status_code=404, detail="unknown connection")
    return {"deleted": True}


async def _resolve_key(key: str, kind: str):
    """(org_id, system_id, record) for an ingest key (None when unknown)."""
    if _hosted():
        from core.commerce import repo as repo_module

        record = await asyncio.to_thread(
            repo_module.get_store().find_record_for_key, key, kind
        )
        if record is None:
            return None
        return record.get("org_id", ""), record["system_id"], record
    system_id = key_auth.system_for_key(key, kind)
    if system_id is None:
        return None
    record = connection_store.find_record_for_key(key, kind)
    return "", system_id, record


async def _mark_first_log(
    connection_id: str, system_id: str, org_id: str = ""
) -> None:
    """Flip waiting → ok + emit connection_status on the first delivery."""
    from apps.api.main import emit_for  # deferred: main loads last

    if _hosted():
        store = _conn_store(org_id)
        record = await asyncio.to_thread(
            store.get_connection, org_id, connection_id
        )
        if record is None:
            return
        first = record.get("status") != "ok"
        await asyncio.to_thread(
            store.mark_connection_seen, org_id, connection_id
        )
    else:
        record = connection_store.get_record(connection_id)
        if record is None:
            return
        first = record.get("status") != "ok"
        connection_store.mark_seen(connection_id)
    if first:
        await emit_for(
            org_id,
            SimEvent(
                kind="connection_status",
                payload={
                    "connection_id": connection_id,
                    "system_id": system_id,
                    "status": "ok",
                    "detail": "first log received",
                },
            ),
        )


async def _broadcast_decisions(decisions: list) -> None:
    from apps.api.main import emit_for  # deferred: main loads last

    for body in decisions:
        await emit_for(
            str(body.get("org_id", "") or ""),
            SimEvent(kind="gate_decision", payload=body),
        )


@router.post("/api/ingest/logs", response_model=IngestResult)
async def ingest_logs(request: Request, payload: IngestLogsIn) -> IngestResult:
    """Accept forwarder batches; tracebacks become one candidate each."""
    key = _bearer_key(request)
    resolved = await _resolve_key(key, "logs")
    if resolved is None:
        raise HTTPException(status_code=401, detail="unknown ingest key")
    org_id, system_id, record = resolved
    lines = [line.message for line in payload.lines]
    result = await ingest_pipeline.process_lines(
        system_id,
        payload.service,
        lines,
        commit=payload.commit,
        org_id=org_id,
    )
    _usage(
        org_id, "ingest", quantity=len(lines), unit="lines",
        system_id=system_id,
    )
    if record is not None:
        await _mark_first_log(record["id"], system_id, org_id)
    await _broadcast_decisions(result["decisions"])
    # J-R3: armed production tracebacks with a repo connection start a
    # background repo-fix run; the response never waits for it.
    await repo_fix_run.maybe_trigger(
        system_id, result["decisions"], payload.commit, org_id
    )
    return IngestResult(
        accepted=result["accepted"], candidates=result["candidates"]
    )


@router.post("/api/ingest/sentry/{key}", response_model=SentryAccepted)
async def ingest_sentry(key: str, payload: dict) -> SentryAccepted:
    """Accept a Sentry issue-alert webhook as one error event."""
    resolved = await _resolve_key(key, "sentry")
    if resolved is None:
        raise HTTPException(status_code=401, detail="unknown sentry key")
    org_id, system_id, record = resolved
    texts = ingest_pipeline.sentry_texts(payload)
    result = await ingest_pipeline.process_lines(
        system_id, "sentry", texts, org_id=org_id
    )
    _usage(
        org_id, "ingest", quantity=len(texts), unit="lines",
        system_id=system_id,
    )
    if record is not None:
        await _mark_first_log(record["id"], system_id, org_id)
    await _broadcast_decisions(result["decisions"])
    await repo_fix_run.maybe_trigger(system_id, result["decisions"], "", org_id)
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
async def get_pause(request: Request) -> PauseState:
    if _hosted():
        from core.commerce import auth as auth_module

        org_id = auth_module.read_org(request)
        if not org_id:
            return PauseState(paused=False)  # demo channel has no pause
        return PauseState(
            paused=await asyncio.to_thread(
                mitigate_actions.is_paused, org_id
            )
        )
    return PauseState(paused=mitigate_actions.is_paused())


@router.post("/api/actions/pause", response_model=PauseState)
async def set_pause(request: Request, payload: PauseState) -> PauseState:
    """Kill switch, per-org hosted (persisted) + `actions_paused` event."""
    from apps.api.main import emit_for  # deferred: main loads last

    if _hosted():
        ctx = _need(request, "admin")
        user = ctx.user_id
        paused = await asyncio.to_thread(
            mitigate_actions.set_paused, payload.paused, ctx.org_id, user
        )
        await emit_for(
            ctx.org_id,
            SimEvent(kind="actions_paused", payload={"paused": paused}),
        )
        return PauseState(paused=paused)
    _require_mobile_token(request)
    paused = mitigate_actions.set_paused(payload.paused)
    await emit_for(
        "",
        SimEvent(kind="actions_paused", payload={"paused": paused}),
    )
    return PauseState(paused=paused)
