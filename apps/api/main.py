from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from typing import Dict, Literal, Optional, Set
from uuid import uuid4

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from core.infer.analyzer import diagnose
from core.schemas.diagnosis import Diagnosis, DiagnosisRequest
from core.schemas.events import AgentStep, LogEvent, LogInput, SimEvent
from core.schemas.remediation import (
    ApplianceResult,
    ApplianceRunRequest,
    ExecutionResult,
    RunRequest,
    RunSource,
)
from core.schemas.telemetry import ApplianceTelemetry, SensorReading
from core.simulate.fridge_stream import VirtualFridge
from core.watch.sensor_watcher import SensorHit, SensorWatcher

# Sim 4 world: one live fridge + sensor watcher per API process.
fridge = VirtualFridge()
sensor_watcher = SensorWatcher()
fridge_task: Optional[asyncio.Task] = None

# Sim 7: hardware sensor nodes (Wokwi/ESP32) get their own watcher instances
# sharing the same rules engine; interleaved sources would break streaks.
external_watchers: Dict[str, SensorWatcher] = {}
_MAX_EXTERNAL_WATCHERS = 50


def external_watcher_for(source_id: str, appliance_type: str) -> SensorWatcher:
    watcher = external_watchers.get(source_id)
    if watcher is None:
        if len(external_watchers) >= _MAX_EXTERNAL_WATCHERS:
            external_watchers.pop(next(iter(external_watchers)), None)
        watcher = SensorWatcher(
            appliance_type=appliance_type, source_id=source_id
        )
        external_watchers[source_id] = watcher
    return watcher

# Sim 5 deploy: recent results by run_id so apply-fix/apply-runbook can gate
# on a verified PASS. Bounded; demo scale only.
software_runs: Dict[str, dict] = {}
appliance_runs: Dict[str, dict] = {}
_MAX_STORED_RUNS = 200


def _remember(store: Dict[str, dict], run_id: str, entry: dict) -> None:
    if len(store) >= _MAX_STORED_RUNS:
        store.pop(next(iter(store)), None)
    store[run_id] = entry


def shop_base_url() -> str:
    port = os.environ.get("SHOP_PORT", "8002")
    return os.environ.get("SHOP_URL", f"http://localhost:{port}")


def shop_runtime_path() -> Path:
    return (
        Path(__file__).resolve().parent.parent.parent
        / "demo"
        / "shop"
        / ".runtime"
        / "inventory_active.py"
    )


# Sim 6 demo: spawned load processes + scenario player state.
load_procs: list = []
scenario_task: Optional[asyncio.Task] = None
scenario_state: Dict[str, object] = {
    "playing": False,
    "done": 0,
    "total": 0,
    "current": "",
}


def spawn_shop_load(shoppers: int, rate: float, duration: int) -> int:
    """Spawn the shop load generator; return its pid. Never blocks."""
    import subprocess
    import sys

    repo = Path(__file__).resolve().parent.parent.parent
    proc = subprocess.Popen(
        [sys.executable, str(repo / "demo" / "shop" / "load.py"),
         "--shop", shop_base_url(),
         "--shoppers", str(shoppers),
         "--rate", str(rate),
         "--duration", str(duration)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    load_procs.append(proc)
    return proc.pid


def fridge_tick_s() -> float:
    try:
        return max(0.1, float(os.environ.get("FRIDGE_TICK_S", "1.0")))
    except ValueError:
        return 1.0


@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.environ.get("FRIDGE_STREAM") == "1":
        ensure_fridge_stream()
    yield
    global fridge_task
    if fridge_task is not None:
        fridge_task.cancel()
        fridge_task = None


def cors_origin_regex() -> str:
    """Local dashboard origins; `CORS_ORIGIN_REGEX` overrides for deploys."""
    override = os.environ.get("CORS_ORIGIN_REGEX")
    if override:
        return override
    return (
        r"http://(localhost|127\.0\.0\.1|192\.168\.\d{1,3}\.\d{1,3}"
        r"|10\.\d{1,3}\.\d{1,3}\.\d{1,3}):3000"
    )


app = FastAPI(title="Telemetry Agent API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=cors_origin_regex(),
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
    test_path = "test_solution.py"
    if payload.target == "inventory":
        from core.verify.targets import read_target_file

        if original_code is None:
            original_code = read_target_file("inventory.py")
        code_path, test_path = "inventory.py", "test_inventory_regression.py"
    elif payload.target_path:
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

        if payload.target == "inventory" or payload.target_path:
            opener = partial(open_fix_pr, code_path=code_path, test_path=test_path)
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
    _remember(software_runs, run_id, {"target": payload.target, "result": result})
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
    _remember(
        appliance_runs,
        run_id,
        {"appliance_type": payload.appliance_type, "result": result},
    )
    return result


async def _run_appliance_from_telemetry(
    telemetry: ApplianceTelemetry, source: str
) -> ApplianceResult:
    """Shared by the readings endpoint and the sensor-watcher trigger path."""
    from core.actions.notify import send_alert
    from core.agent.loop import run_appliance_loop

    run_id = uuid4().hex[:8]
    on_event = _step_bridge(asyncio.get_running_loop(), source)
    result = await asyncio.to_thread(
        run_appliance_loop, telemetry, 3, on_event, send_alert, run_id
    )
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
            source=source,
        )
    )
    _remember(
        appliance_runs,
        run_id,
        {"appliance_type": telemetry.appliance_type, "result": result},
    )
    return result


@app.post("/api/run/appliance/readings", response_model=ApplianceResult)
async def run_appliance_readings(
    telemetry: ApplianceTelemetry, source: RunSource = "manual"
) -> ApplianceResult:
    try:
        return await _run_appliance_from_telemetry(telemetry, source)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/sim/events", response_model=SimEvent)
async def sim_event(event: SimEvent) -> SimEvent:
    await hub.broadcast(event)
    return event


class FridgeFaultIn(BaseModel):
    fault: Literal["door_open", "condenser_fouling", "power_surge", "rapid_restart"]


class FridgeActionIn(BaseModel):
    action: Literal["close_door", "clean_condenser", "reset"]


def ensure_fridge_stream() -> None:
    """Start the tick loop once; fault/action buttons call this implicitly."""
    global fridge_task
    if fridge_task is None or fridge_task.done():
        fridge_task = asyncio.get_running_loop().create_task(_fridge_loop())


async def _broadcast_sensor_trigger(hit: SensorHit) -> None:
    from core.watch.rules import fingerprint_for

    await hub.broadcast(
        SimEvent(
            kind="watcher_trigger",
            payload={
                "rule": hit.rule,
                "level": hit.level,
                "domain": "appliance",
                "fingerprint": fingerprint_for(
                    hit.rule, hit.resource, hit.detail
                ),
                "matched_lines": [hit.detail],
            },
        )
    )


async def _run_watcher_appliance(watcher: SensorWatcher) -> None:
    try:
        telemetry = watcher.telemetry()
    except ValueError:
        return
    try:
        await _run_appliance_from_telemetry(telemetry, "watcher")
    except RuntimeError as exc:
        await hub.broadcast(
            AgentStep(
                step="done",
                status="error",
                message=str(exc)[:300],
                run_id=uuid4().hex[:8],
                domain="appliance",
                source="watcher",
            )
        )


async def _evaluate_sensor_reading(
    watcher: SensorWatcher, reading: SensorReading
) -> Optional[SensorHit]:
    """Shared trigger path for the virtual fridge and hardware ingest."""
    hit = watcher.observe(reading)
    if hit is None:
        return None
    await _broadcast_sensor_trigger(hit)
    asyncio.get_running_loop().create_task(_run_watcher_appliance(watcher))
    return hit


async def _fridge_loop() -> None:
    while True:
        await asyncio.sleep(fridge_tick_s())
        reading = fridge.tick()
        await hub.broadcast(
            SimEvent(
                kind="fridge_reading",
                payload={
                    "reading": reading.model_dump(mode="json"),
                    "state": fridge.snapshot(),
                },
            )
        )
        await _evaluate_sensor_reading(sensor_watcher, reading)


@app.get("/api/sim/fridge/state")
async def fridge_state() -> dict:
    return fridge.snapshot()


class TelemetryIngestIn(BaseModel):
    source_id: str = Field(min_length=1, max_length=100)
    appliance_type: Literal["fridge", "freezer"] = "fridge"
    temperature_c: float
    current_a: float = Field(ge=0)
    vibration_g: float = Field(default=0.0, ge=0)
    door_open: bool = False
    ambient_c: Optional[float] = Field(
        default=None, description="Ambient reference; display only, never evaluated"
    )


@app.post("/api/telemetry/appliance")
async def ingest_appliance_reading(payload: TelemetryIngestIn) -> dict:
    """Ingest one hardware sensor reading (Sim 7 Wokwi/ESP32).

    The reading reaches the dashboard over the same `fridge_reading` event
    and is evaluated by the same rules engine as the virtual fridge, with a
    per-source watcher so interleaved sources keep their own streaks.
    """
    import time

    reading = SensorReading(
        ts=time.time(),
        temperature_c=payload.temperature_c,
        current_a=payload.current_a,
        vibration_g=payload.vibration_g,
        door_open=payload.door_open,
    )
    watcher = external_watcher_for(payload.source_id, payload.appliance_type)
    await hub.broadcast(
        SimEvent(
            kind="fridge_reading",
            payload={
                "reading": reading.model_dump(mode="json"),
                "state": {
                    "appliance_type": payload.appliance_type,
                    "source_id": payload.source_id,
                    "temp_c": payload.temperature_c,
                    "door_open": payload.door_open,
                    "hardware": True,
                },
            },
        )
    )
    hit = await _evaluate_sensor_reading(watcher, reading)
    return {
        "source_id": payload.source_id,
        "accepted": True,
        "buffered": watcher.buffered,
        "triggered": hit.rule if hit else None,
    }


@app.post("/api/sim/fridge/fault")
async def fridge_fault(payload: FridgeFaultIn) -> dict:
    fridge.apply_fault(payload.fault)
    ensure_fridge_stream()
    return fridge.snapshot()


@app.post("/api/sim/fridge/action")
async def fridge_action(payload: FridgeActionIn) -> dict:
    fridge.apply_action(payload.action)
    if payload.action == "reset":
        sensor_watcher.reset()
    ensure_fridge_stream()
    return fridge.snapshot()


class ApplyFixIn(BaseModel):
    run_id: str = Field(min_length=1, max_length=64)


@app.post("/api/sim/shop/apply-fix")
async def shop_apply_fix(payload: ApplyFixIn) -> dict:
    """Deploy a verified inventory patch to the shop ("merge and deploy").

    Writes the PASS run's `patch_code` to the gitignored runtime path and
    tells the shop to hot-swap to it. FAIL runs, missing patches, and
    non-inventory runs are rejected; the buggy original is never touched
    (the PR on GitHub is the durable fix).
    """
    import httpx

    entry = software_runs.get(payload.run_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="unknown run_id")
    result = entry["result"]
    if result.status != "PASS" or not result.patch_code:
        raise HTTPException(
            status_code=409, detail="only verified (PASS) runs can be deployed"
        )
    if entry.get("target") != "inventory":
        raise HTTPException(
            status_code=409, detail="only inventory runs deploy to the shop"
        )
    runtime_path = shop_runtime_path()
    runtime_path.parent.mkdir(parents=True, exist_ok=True)
    runtime_path.write_text(result.patch_code, encoding="utf-8")
    try:
        response = httpx.post(
            f"{shop_base_url().rstrip('/')}/reload",
            json={"inventory_path": str(runtime_path)},
            timeout=10.0,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail=f"shop reload unreachable: {exc}"
        ) from exc
    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"shop rejected reload ({response.status_code}): "
            f"{response.text[:200]}",
        )
    await hub.broadcast(
        SimEvent(
            kind="fix_applied",
            payload={
                "run_id": payload.run_id,
                "domain": "software",
                "inventory": str(runtime_path),
            },
        )
    )
    return {
        "run_id": payload.run_id,
        "inventory": str(runtime_path),
        "shop": response.json(),
    }


class ApplyRunbookIn(BaseModel):
    run_id: str = Field(min_length=1, max_length=64)


@app.post("/api/sim/fridge/apply-runbook")
async def fridge_apply_runbook(payload: ApplyRunbookIn) -> dict:
    """Technician applies the validated runbook to the virtual fridge.

    Only PASS runs (runbook already passed `validate_runbook`) execute, and
    the runbook is re-validated here; unmappable steps are reported skipped,
    never force-executed.
    """
    from core.simulate.fridge_stream import map_step_to_action
    from core.verify.safety_rules import validate_runbook

    entry = appliance_runs.get(payload.run_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="unknown run_id")
    result = entry["result"]
    if result.status != "PASS" or result.runbook is None:
        raise HTTPException(
            status_code=409, detail="only validated (PASS) runbooks can run"
        )
    violations = validate_runbook(result.runbook, entry.get("appliance_type", ""))
    if violations:
        raise HTTPException(
            status_code=409,
            detail=f"runbook rejected by safety rules: {'; '.join(violations)}",
        )
    applied: list[dict] = []
    skipped: list[str] = []
    for step in result.runbook.steps:
        action = map_step_to_action(step)
        if action is None:
            skipped.append(step)
            continue
        fridge.apply_action(action)
        applied.append({"step": step, "action": action})
    await hub.broadcast(
        SimEvent(
            kind="fix_applied",
            payload={"run_id": payload.run_id, "domain": "appliance",
                     "applied": [a["action"] for a in applied]},
        )
    )
    return {
        "run_id": payload.run_id,
        "applied": applied,
        "skipped": skipped,
        "state": fridge.snapshot(),
    }


class ShopLoadIn(BaseModel):
    shoppers: int = Field(default=8, ge=1, le=32)
    rate: float = Field(default=30.0, ge=1.0, le=200.0)
    duration: int = Field(default=30, ge=1, le=300)


@app.post("/api/sim/shop/load")
async def shop_load(payload: ShopLoadIn) -> dict:
    """Start a shop load burst in the background (scenario + dashboard)."""
    pid = spawn_shop_load(payload.shoppers, payload.rate, payload.duration)
    return {"pid": pid, "shoppers": payload.shoppers, "rate": payload.rate,
            "duration": payload.duration}


async def _play_and_track(steps: list) -> None:
    from core.simulate.scenario import play_timeline

    async def on_step(done: int, total: int, step: dict) -> None:
        scenario_state.update({"done": done, "total": total,
                               "current": str(step.get("action", ""))})
        await hub.broadcast(
            SimEvent(kind="scenario_step",
                     payload={"done": done, "total": total,
                              "action": step.get("action", ""),
                              "at": step.get("at", 0)})
        )

    def apply_fault(name: str) -> None:
        fridge.apply_fault(name)
        ensure_fridge_stream()

    def apply_action(name: str) -> None:
        fridge.apply_action(name)
        ensure_fridge_stream()

    try:
        await play_timeline(steps, spawn_shop_load, apply_fault, apply_action,
                            on_step=on_step)
    finally:
        scenario_state.update({"playing": False, "current": ""})


@app.post("/api/sim/scenario/play")
async def scenario_play() -> dict:
    """Play `demo/timeline.yaml` on schedule; one scenario at a time."""
    global scenario_task
    from core.simulate.scenario import TIMELINE_PATH, load_timeline

    if scenario_task is not None and not scenario_task.done():
        raise HTTPException(status_code=409, detail="scenario already playing")
    if not TIMELINE_PATH.exists():
        raise HTTPException(status_code=500, detail="timeline.yaml missing")
    try:
        steps = load_timeline()
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    scenario_state.update({"playing": True, "done": 0, "total": len(steps),
                           "current": "starting"})
    scenario_task = asyncio.get_running_loop().create_task(
        _play_and_track(steps)
    )
    return {"steps": len(steps), "total_s": max(s["at"] for s in steps)}


@app.get("/api/sim/scenario/status")
async def scenario_status() -> dict:
    return dict(scenario_state)


@app.post("/api/sim/reset")
async def sim_reset() -> dict:
    """Reset the world: stop scenario/load, clear patch, reset fridge/runs."""
    import httpx

    global scenario_task
    summary: Dict[str, object] = {}
    if scenario_task is not None and not scenario_task.done():
        scenario_task.cancel()
        summary["scenario"] = "stopped"
    scenario_task = None
    scenario_state.update({"playing": False, "done": 0, "total": 0,
                           "current": ""})
    stopped = 0
    while load_procs:
        proc = load_procs.pop()
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
            stopped += 1
    summary["load_stopped"] = stopped
    runtime_path = shop_runtime_path()
    if runtime_path.exists():
        runtime_path.unlink()
        summary["runtime_patch"] = "cleared"
    else:
        summary["runtime_patch"] = "none"
    try:
        buggy = str(
            Path(__file__).resolve().parent.parent.parent
            / "demo" / "target-service" / "inventory.py"
        )
        response = httpx.post(
            f"{shop_base_url().rstrip('/')}/reload",
            json={"inventory_path": buggy},
            timeout=5.0,
        )
        summary["shop"] = "buggy" if response.status_code < 400 else "reload-failed"
    except httpx.HTTPError:
        summary["shop"] = "unreachable"
    fridge.apply_action("reset")
    sensor_watcher.reset()
    external_watchers.clear()
    software_runs.clear()
    appliance_runs.clear()
    summary["fridge"] = "reset"
    return summary


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
