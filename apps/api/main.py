from __future__ import annotations

from datetime import datetime, timezone
from typing import Set
from uuid import uuid4

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from core.infer.analyzer import diagnose
from core.schemas.diagnosis import Diagnosis, DiagnosisRequest
from core.schemas.events import LogEvent, LogInput

app = FastAPI(title="Telemetry Agent API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
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

    async def broadcast(self, event: LogEvent) -> None:
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
