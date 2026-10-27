from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Set
from uuid import uuid4

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from core.infer.analyzer import diagnose
from core.schemas.diagnosis import Diagnosis, DiagnosisRequest
from core.schemas.events import AgentStep, LogEvent, LogInput
from core.schemas.remediation import (
    ApplianceResult,
    ApplianceRunRequest,
    ExecutionResult,
    RunRequest,
)

app = FastAPI(title="Telemetry Agent API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=(
        r"http://(localhost|127\.0\.0\.1|192\.168\.\d{1,3}\.\d{1,3}"
        r"|10\.\d{1,3}\.\d{1,3}\.\d{1,3}):3000"
    ),
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class EventHub:
    def __init__(self) -> None:
        self.clients: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.clients.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self.clients.discard(websocket)

    async def broadcast(self, event: BaseModel) -> None:
        stale: list[WebSocket] = []
        for client in self.clients:
            try:
                await client.send_json(event.model_dump(mode="json"))
            except (RuntimeError, WebSocketDisconnect):
                stale.append(client)
        for client in stale:
            self.disconnect(client)


hub = EventHub()


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/logs", response_model=LogEvent)
async def ingest_log(payload: LogInput) -> LogEvent:
    event = LogEvent(
        id=str(uuid4()),
        timestamp=datetime.now(timezone.utc),
        source=payload.source,
        message=payload.message,
        level=payload.level or infer_level(payload.message),
    )
    await hub.broadcast(event)
    return event


@app.post("/api/diagnose", response_model=Diagnosis)
async def diagnose_logs(payload: DiagnosisRequest) -> Diagnosis:
    return await diagnose(payload.log_text)


def _step_bridge(loop: asyncio.AbstractEventLoop, source: str):
    def on_event(event: dict) -> None:
        step = AgentStep(
            step=str(event.get("step", "")),
            attempt=int(event.get("attempt", 0)),
            model=str(event.get("model", "")),
            status=str(event.get("status", "")),
            message=str(event.get("message", "")),
            duration_ms=float(event.get("duration_ms", 0.0)),
            run_id=str(event.get("run_id", "")),
            domain=str(event.get("domain", "")),
            detail=str(event.get("detail", "")),
            source=source,
            suggestions=[s for s in (event.get("suggestions") or []) if isinstance(s, str)],
        )
        asyncio.run_coroutine_threadsafe(hub.broadcast(step), loop)

    return on_event


@app.post("/api/run", response_model=ExecutionResult)
async def run_agent(payload: RunRequest) -> ExecutionResult:
    from core.agent.loop import run_diagnostic_loop

    run_id = uuid4().hex[:8]
    on_event = _step_bridge(asyncio.get_running_loop(), payload.source)

    original_code = payload.original_code
    code_path = "solution.py"
    if payload.target_path:
        from core.verify.targets import read_target_file, resolve_target_path

        try:
            resolved = resolve_target_path(payload.target_path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if original_code is None:
            original_code = read_target_file(payload.target_path)
        code_path = resolved.name

    opener = None
    if os.environ.get("GITHUB_TOKEN"):
        from core.actions.github_pr import open_fix_pr

        if payload.target_path:
            def opener(**kwargs):
                return open_fix_pr(**kwargs, code_path=code_path)
        else:
            opener = open_fix_pr

    try:
        result = await asyncio.to_thread(
            run_diagnostic_loop,
            payload.log_text,
            3,
            on_event,
            original_code,
            opener,
            run_id,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    await hub.broadcast(
        AgentStep(
            step="done",
            attempt=result.attempts,
            model=result.model_used,
            status=result.status,
            message=result.pr_url or "",
            run_id=run_id,
            domain="software",
            source=payload.source,
        )
    )
    return result


@app.post("/api/run/appliance", response_model=ApplianceResult)
async def run_appliance(payload: ApplianceRunRequest) -> ApplianceResult:
    from core.actions.notify import send_alert
    from core.agent.loop import run_appliance_loop
    from core.simulate.appliance import generate_window

    run_id = uuid4().hex[:8]
    on_event = _step_bridge(asyncio.get_running_loop(), payload.source)
    telemetry = generate_window(
        appliance_type=payload.appliance_type,
        fault=payload.fault,
        n_readings=payload.n_readings,
        source_id=payload.source_id,
    )
    try:
        result = await asyncio.to_thread(
            run_appliance_loop, telemetry, 3, on_event, send_alert, run_id
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    message = ""
    if result.alert is not None:
        message = f"{result.alert.alert_id} · {result.alert.work_order_id}"
    await hub.broadcast(
        AgentStep(
            step="done",
            attempt=result.attempts,
            model=result.model_used,
            status=result.status,
            message=message,
            run_id=run_id,
            domain="appliance",
            source=payload.source,
        )
    )
    return result


@app.get("/api/samples/deadlock")
async def deadlock_sample() -> dict[str, str]:
    path = (
        Path(__file__).resolve().parent.parent.parent
        / "samples"
        / "database_deadlock.log"
    )
    return {"name": "database_deadlock.log", "log_text": path.read_text(encoding="utf-8")}


@app.websocket("/api/ws")
async def stream_events(websocket: WebSocket) -> None:
    await hub.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        hub.disconnect(websocket)


def infer_level(message: str) -> str:
    normalized = message.lower()
    if any(token in normalized for token in ("critical", "fatal")):
        return "CRITICAL"
    if any(token in normalized for token in ("error", "failed", "exception", "fault")):
        return "ERROR"
    if any(token in normalized for token in ("warning", "timeout", "deadlock")):
        return "WARNING"
    return "INFO"
