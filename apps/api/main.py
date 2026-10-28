from __future__ import annotations

import asyncio
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from typing import Dict, Literal, Optional, Set
from uuid import uuid4

from fastapi import (
    FastAPI,
    File,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from core.actions.auto_action import (
    PendingAction,
    action_summary_for,
    auto_enabled,
    mobile_token,
    window_seconds,
)
from core.infer.analyzer import diagnose
from core.schemas.diagnosis import Diagnosis, DiagnosisRequest
from core.schemas.events import AgentStep, LogEvent, LogInput, SimEvent
from core.schemas.profile import SystemProfile
from core.setup import extract as setup_extract
from core.setup import store as setup_store
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


# M0 + U2 reports: streamed steps and auto-action windows by run_id.
run_steps: Dict[str, list] = {}
pending_actions: Dict[str, PendingAction] = {}
_MAX_STEPS_PER_RUN = 50


def _record_step(step: AgentStep) -> None:
    if not step.run_id:
        return
    steps = run_steps.setdefault(step.run_id, [])
    steps.append(step)
    if len(steps) > _MAX_STEPS_PER_RUN:
        del steps[:-_MAX_STEPS_PER_RUN]
    if len(run_steps) > _MAX_STORED_RUNS:
        run_steps.pop(next(iter(run_steps)), None)


def _mobile_authorized(request: Request) -> bool:
    token = mobile_token()
    if not token:
        return True
    return request.headers.get("X-Mobile-Token", "") == token


def _require_mobile_token(request: Request) -> None:
    if not _mobile_authorized(request):
        raise HTTPException(status_code=401, detail="bad or missing mobile token")


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
    global action_ticker_task
    if os.environ.get("FRIDGE_STREAM") == "1":
        ensure_fridge_stream()
    action_ticker_task = asyncio.get_running_loop().create_task(_action_ticker())
    yield
    global fridge_task
    if fridge_task is not None:
        fridge_task.cancel()
        fridge_task = None
    if action_ticker_task is not None:
        action_ticker_task.cancel()
        action_ticker_task = None


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
        _record_step(step)

    return on_event


@app.post("/api/run", response_model=ExecutionResult)
async def run_agent(payload: RunRequest) -> ExecutionResult:
    from core.agent.loop import run_diagnostic_loop

    run_id = uuid4().hex[:8]
    on_event = _step_bridge(asyncio.get_running_loop(), payload.source)

    original_code = payload.original_code
    code_path = "solution.py"
    test_path = "test_solution.py"
    contract = None
    harness = None
    if payload.target == "inventory":
        from core.verify.contracts import contract_for_target
        from core.verify.targets import read_target_file

        if original_code is None:
            original_code = read_target_file("inventory.py")
        contract, harness = contract_for_target("inventory", original_code)
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
            contract,
            harness,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    done = AgentStep(
        step="done",
        attempt=result.attempts,
        model=result.model_used,
        status=result.status,
        message=result.pr_url or "",
        run_id=run_id,
        domain="software",
        source=payload.source,
    )
    _record_step(done)
    await hub.broadcast(done)
    _remember(software_runs, run_id, {"target": payload.target, "result": result})
    await _maybe_open_action(run_id, "software")
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
    done = AgentStep(
        step="done",
        attempt=result.attempts,
        model=result.model_used,
        status=result.status,
        message=message,
        run_id=run_id,
        domain="appliance",
        source=payload.source,
    )
    _record_step(done)
    await hub.broadcast(done)
    _remember(
        appliance_runs,
        run_id,
        {"appliance_type": payload.appliance_type, "result": result},
    )
    await _maybe_open_action(run_id, "appliance")
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
    done = AgentStep(
        step="done",
        attempt=result.attempts,
        model=result.model_used,
        status=result.status,
        message=message,
        run_id=run_id,
        domain="appliance",
        source=source,
    )
    _record_step(done)
    await hub.broadcast(done)
    _remember(
        appliance_runs,
        run_id,
        {"appliance_type": telemetry.appliance_type, "result": result},
    )
    await _maybe_open_action(run_id, "appliance")
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
        done = AgentStep(
            step="done",
            status="error",
            message=str(exc)[:300],
            run_id=uuid4().hex[:8],
            domain="appliance",
            source="watcher",
        )
        _record_step(done)
        await hub.broadcast(done)


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


@app.get("/api/pairing")
async def pairing() -> dict:
    """LAN URL for phone pairing (M1): best-effort local IP + API port."""
    import socket

    ip = "127.0.0.1"
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("8.8.8.8", 80))
        ip = probe.getsockname()[0]
        probe.close()
    except OSError:
        pass
    port = os.environ.get("PORT", "8001")
    return {"api_url": f"http://{ip}:{port}"}


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


class _ApplyError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


async def _deploy_patch_for_run(run_id: str) -> dict:
    """Shared by the dashboard button and the M0 auto-apply timer."""
    import httpx

    entry = software_runs.get(run_id)
    if entry is None:
        raise _ApplyError(404, "unknown run_id")
    result = entry["result"]
    if result.status != "PASS" or not result.patch_code:
        raise _ApplyError(409, "only verified (PASS) runs can be deployed")
    if entry.get("target") != "inventory":
        raise _ApplyError(409, "only inventory runs deploy to the shop")
    from core.verify.contracts import check_inventory_source

    reason = check_inventory_source(result.patch_code)
    if reason is not None:
        raise _ApplyError(409, f"patch fails inventory contract: {reason}")
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
        raise _ApplyError(502, f"shop reload unreachable: {exc}") from exc
    if response.status_code >= 400:
        raise _ApplyError(
            502,
            f"shop rejected reload ({response.status_code}): "
            f"{response.text[:200]}",
        )
    await hub.broadcast(
        SimEvent(
            kind="fix_applied",
            payload={
                "run_id": run_id,
                "domain": "software",
                "inventory": str(runtime_path),
            },
        )
    )
    return {
        "run_id": run_id,
        "inventory": str(runtime_path),
        "shop": response.json(),
    }


@app.post("/api/sim/shop/apply-fix")
async def shop_apply_fix(payload: ApplyFixIn, request: Request) -> dict:
    """Deploy a verified inventory patch to the shop ("merge and deploy").

    Writes the PASS run's `patch_code` to the gitignored runtime path and
    tells the shop to hot-swap to it. FAIL runs, missing patches, and
    non-inventory runs are rejected; the buggy original is never touched
    (the PR on GitHub is the durable fix).
    """
    _require_mobile_token(request)
    try:
        return await _deploy_patch_for_run(payload.run_id)
    except _ApplyError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail) from exc


class ApplyRunbookIn(BaseModel):
    run_id: str = Field(min_length=1, max_length=64)


async def _apply_runbook_for_run(run_id: str) -> dict:
    """Shared by the technician button and the M0 auto-apply timer."""
    from core.simulate.fridge_stream import map_step_to_action
    from core.verify.safety_rules import validate_runbook

    entry = appliance_runs.get(run_id)
    if entry is None:
        raise _ApplyError(404, "unknown run_id")
    result = entry["result"]
    if result.status != "PASS" or result.runbook is None:
        raise _ApplyError(409, "only validated (PASS) runbooks can run")
    violations = validate_runbook(result.runbook, entry.get("appliance_type", ""))
    if violations:
        raise _ApplyError(
            409, f"runbook rejected by safety rules: {'; '.join(violations)}"
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
            payload={"run_id": run_id, "domain": "appliance",
                     "applied": [a["action"] for a in applied]},
        )
    )
    return {
        "run_id": run_id,
        "applied": applied,
        "skipped": skipped,
        "state": fridge.snapshot(),
    }


@app.post("/api/sim/fridge/apply-runbook")
async def fridge_apply_runbook(payload: ApplyRunbookIn, request: Request) -> dict:
    """Technician applies the validated runbook to the virtual fridge.

    Only PASS runs (runbook already passed `validate_runbook`) execute, and
    the runbook is re-validated here; unmappable steps are reported skipped,
    never force-executed.
    """
    _require_mobile_token(request)
    try:
        return await _apply_runbook_for_run(payload.run_id)
    except _ApplyError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail) from exc


action_ticker_task: Optional[asyncio.Task] = None


async def _maybe_open_action(run_id: str, domain: str) -> Optional[PendingAction]:
    """Open a veto window when a finished run is eligible; idempotent."""
    store = software_runs if domain == "software" else appliance_runs
    entry = store.get(run_id)
    if entry is None:
        return None
    existing = pending_actions.get(run_id)
    if existing is not None:
        return existing
    summary = action_summary_for(domain, entry)
    if summary is None:
        return None
    now = time.time()
    action = PendingAction(
        run_id=run_id,
        domain=domain,  # type: ignore[arg-type]
        action=summary,
        opened_at=now,
        deadline=now + window_seconds(),
    )
    pending_actions[run_id] = action
    await hub.broadcast(
        SimEvent(
            kind="action_pending",
            payload={
                **action.model_dump(mode="json"),
                "seconds": window_seconds(),
            },
        )
    )
    return action


async def _settle_window(run_id: str) -> Optional[PendingAction]:
    """Apply or expire a due window. Check-and-set is atomic (no await inside)."""
    action = pending_actions.get(run_id)
    if action is None or action.state != "pending":
        return action
    if time.time() < action.deadline:
        return action
    if not auto_enabled():
        action.state = "expired"
        action.detail = "auto-apply disabled; approval required"
        action.resolved_at = time.time()
    else:
        apply = (
            _deploy_patch_for_run
            if action.domain == "software"
            else _apply_runbook_for_run
        )
        try:
            await apply(run_id)
        except _ApplyError as exc:
            action.state = "failed"
            action.detail = exc.detail
        except Exception as exc:  # noqa: BLE001 - apply must not kill the ticker
            action.state = "failed"
            action.detail = f"{type(exc).__name__}: {exc}"
        else:
            action.state = "auto_applied"
            action.detail = action.action
        action.resolved_at = time.time()
    await hub.broadcast(
        SimEvent(kind="action_resolved",
                 payload=action.model_dump(mode="json"))
    )
    return action


async def _decide_action(
    run_id: str, approve: bool, device: str
) -> PendingAction:
    """First decision wins; late or repeat decisions get 409."""
    action = pending_actions.get(run_id)
    if action is None:
        raise _ApplyError(404, "unknown run_id")
    if action.state != "pending":
        raise _ApplyError(409, f"window already {action.state}")
    if time.time() >= action.deadline:
        raise _ApplyError(409, "too late: deadline passed")
    action.state = "approved" if approve else "disapproved"
    action.decided_by = device
    if not approve:
        action.detail = f"cancelled by {device}"
        action.resolved_at = time.time()
        await hub.broadcast(
            SimEvent(kind="action_resolved",
                     payload=action.model_dump(mode="json"))
        )
        return action
    apply = (
        _deploy_patch_for_run
        if action.domain == "software"
        else _apply_runbook_for_run
    )
    try:
        await apply(run_id)
    except _ApplyError as exc:
        action.state = "failed"
        action.detail = exc.detail
    except Exception as exc:  # noqa: BLE001 - report, don't crash
        action.state = "failed"
        action.detail = f"{type(exc).__name__}: {exc}"
    else:
        action.detail = f"applied by {device}"
    action.resolved_at = time.time()
    await hub.broadcast(
        SimEvent(kind="action_resolved", payload=action.model_dump(mode="json"))
    )
    return action


async def _action_ticker() -> None:
    while True:
        await asyncio.sleep(1.0)
        for run_id, action in list(pending_actions.items()):
            if action.state != "pending":
                continue
            seconds_left = max(0, int(action.deadline - time.time()))
            await hub.broadcast(
                SimEvent(kind="action_tick",
                         payload={"run_id": run_id,
                                  "seconds_left": seconds_left})
            )
            await _settle_window(run_id)


class DecisionIn(BaseModel):
    device: str = Field(default="phone", min_length=1, max_length=64)


@app.post("/api/actions/{run_id}/approve")
async def approve_action(
    run_id: str, payload: DecisionIn, request: Request
) -> dict:
    """Apply the verified fix now, ending the veto window."""
    _require_mobile_token(request)
    try:
        action = await _decide_action(run_id, True, payload.device)
    except _ApplyError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail) from exc
    return action.model_dump(mode="json")


@app.post("/api/actions/{run_id}/disapprove")
async def disapprove_action(
    run_id: str, payload: DecisionIn, request: Request
) -> dict:
    """Cancel the auto-apply; the incident stays open for a human."""
    _require_mobile_token(request)
    try:
        action = await _decide_action(run_id, False, payload.device)
    except _ApplyError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail) from exc
    return action.model_dump(mode="json")


@app.get("/api/actions")
async def list_actions() -> dict:
    """Open veto windows plus recent decisions (mobile + U2)."""
    ordered = sorted(
        pending_actions.values(), key=lambda a: a.opened_at, reverse=True
    )
    now = time.time()

    def dump_open(action: PendingAction) -> dict:
        dumped = action.model_dump(mode="json")
        dumped["seconds_left"] = max(0, int(action.deadline - now))
        return dumped

    return {
        "open": [
            dump_open(a) for a in ordered if a.state == "pending"
        ],
        "recent": [
            a.model_dump(mode="json") for a in ordered if a.state != "pending"
        ][:20],
    }


def _run_entry(run_id: str):
    if run_id in software_runs:
        return "software", software_runs[run_id]
    if run_id in appliance_runs:
        return "appliance", appliance_runs[run_id]
    return None, None


@app.get("/api/runs")
async def list_runs() -> dict:
    """Recent runs with step counts and decision states (mobile + U2)."""
    runs = []
    for domain, store in (
        ("software", software_runs),
        ("appliance", appliance_runs),
    ):
        for run_id, entry in store.items():
            result = entry["result"]
            steps = run_steps.get(run_id, [])
            decision = pending_actions.get(run_id)
            runs.append(
                {
                    "run_id": run_id,
                    "domain": domain,
                    "status": result.status,
                    "attempts": result.attempts,
                    "model_used": result.model_used,
                    "source": steps[0].source if steps else "",
                    "n_steps": len(steps),
                    "decision": decision.state if decision else None,
                }
            )
    return {"runs": runs}


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str) -> dict:
    """One run: full result, streamed steps, decision record."""
    domain, entry = _run_entry(run_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="unknown run_id")
    decision = pending_actions.get(run_id)
    return {
        "run_id": run_id,
        "domain": domain,
        "result": entry["result"].model_dump(mode="json"),
        "steps": [s.model_dump(mode="json") for s in run_steps.get(run_id, [])],
        "decision": decision.model_dump(mode="json") if decision else None,
    }


class SystemCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: Literal["software", "appliance"]
    appliance_type: Optional[Literal["fridge", "freezer"]] = None
    owner_contact: str = Field(default="", max_length=200)


def _slug_system_id(name: str) -> str:
    import re

    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "system"
    return f"{slug[:40]}-{uuid4().hex[:4]}"


@app.post("/api/systems")
async def create_system(payload: SystemCreateIn) -> dict:
    """Create a watched system; its profile starts as a draft (P0/P1)."""
    try:
        profile = SystemProfile(
            system_id=_slug_system_id(payload.name),
            name=payload.name,
            kind=payload.kind,
            appliance_type=payload.appliance_type,
            owner_contact=payload.owner_contact,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    stored = setup_store.save_profile(profile)
    return stored.model_dump(mode="json")


@app.get("/api/systems")
async def list_systems() -> dict:
    """All systems with their setup status (wizard + Systems chip)."""
    return {
        "systems": [
            profile.model_dump(mode="json")
            for profile in setup_store.list_profiles()
        ]
    }


@app.post("/api/systems/{system_id}/documents")
async def upload_documents(
    system_id: str, files: list[UploadFile] = File(...)
) -> dict:
    """Upload spec docs; extract a draft profile (P1, stub-able model)."""
    from core.infer import meta_client

    profile = setup_store.get_profile(system_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="unknown system_id")
    if len(files) > setup_extract.MAX_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"at most {setup_extract.MAX_FILES} files per upload",
        )
    uploads = setup_store.uploads_dir(system_id)
    uploads.mkdir(parents=True, exist_ok=True)
    partials: list = []
    rejected: list[str] = []
    needs_manual: list[str] = []
    for upload in files:
        filename = Path(upload.filename or "upload").name
        kind = setup_extract.classify_file(filename)
        if kind is None:
            raise HTTPException(
                status_code=400, detail=f"unsupported file type: {filename}"
            )
        data = await upload.read(setup_extract.MAX_FILE_BYTES + 1)
        if len(data) > setup_extract.MAX_FILE_BYTES:
            raise HTTPException(
                status_code=400, detail=f"{filename} exceeds the 10 MB limit"
            )
        digest = setup_extract.sha256_bytes(data)
        stored = uploads / f"{digest[:12]}_{filename}"
        stored.write_bytes(data)
        await hub.broadcast(
            SimEvent(
                kind="setup_progress",
                payload={
                    "system_id": system_id,
                    "stage": "uploaded",
                    "doc": filename,
                },
            )
        )
        try:
            doc = await asyncio.to_thread(
                setup_extract.doc_to_pages,
                filename,
                data,
                meta_client.describe_image,
            )
        except setup_extract.ExtractError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if doc.needs_manual:
            needs_manual.append(filename)
            continue
        await hub.broadcast(
            SimEvent(
                kind="setup_progress",
                payload={
                    "system_id": system_id,
                    "stage": "extracting",
                    "doc": filename,
                },
            )
        )
        try:
            raw = await asyncio.to_thread(
                setup_extract.fill_profile_from_text,
                filename,
                "\n".join(doc.pages),
                setup_extract.default_model_fn,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=502, detail=f"extraction failed: {exc}"
            ) from exc
        partial, skipped = setup_extract.sanitize_extraction(raw, doc)
        rejected.extend(f"{filename}: {reason}" for reason in skipped)
        partials.append((filename, partial))
    merged, conflicts = setup_extract.merge_partials(partials)
    update = {
        key: merged[key]
        for key in setup_extract.ALLOWED_KEYS
        if key in merged
    }
    try:
        updated = SystemProfile.model_validate(
            {**profile.model_dump(mode="json"), **update}
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=502, detail=f"extracted profile invalid: {exc}"
        ) from exc
    stored_profile = setup_store.save_profile(updated)
    setup_store.save_conflicts(system_id, conflicts)
    await hub.broadcast(
        SimEvent(
            kind="setup_progress",
            payload={
                "system_id": system_id,
                "stage": "extracted",
                "conflicts": len(conflicts),
            },
        )
    )
    return {
        "profile": stored_profile.model_dump(mode="json"),
        "conflicts": conflicts,
        "rejected": rejected,
        "needs_manual": needs_manual,
    }


@app.get("/api/systems/{system_id}/profile")
async def get_profile(system_id: str) -> dict:
    """Draft profile plus unresolved extraction conflicts (wizard review)."""
    profile = setup_store.get_profile(system_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="unknown system_id")
    return {
        "profile": profile.model_dump(mode="json"),
        "conflicts": setup_store.get_conflicts(system_id),
    }


@app.put("/api/systems/{system_id}/profile")
async def put_profile(system_id: str, payload: SystemProfile) -> dict:
    """Human edits; any edit returns the system to draft (re-confirm)."""
    current = setup_store.get_profile(system_id)
    if current is None:
        raise HTTPException(status_code=404, detail="unknown system_id")
    if payload.system_id != system_id:
        raise HTTPException(status_code=400, detail="system_id mismatch")
    updated = payload.model_copy(
        update={"system_id": system_id, "status": "draft"}
    )
    try:
        SystemProfile.model_validate(updated.model_dump(mode="json"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    stored = setup_store.save_profile(updated)
    return stored.model_dump(mode="json")


class ConfirmIn(BaseModel):
    confirmed_by: str = Field(min_length=1, max_length=120)
    resolve: list[dict] = Field(
        default_factory=list,
        description="[{'field','key','pick'}] conflict picks by index",
    )


@app.post("/api/systems/{system_id}/profile/confirm")
async def confirm_profile(system_id: str, payload: ConfirmIn) -> dict:
    """Resolve conflicts, stamp the human, move draft → confirmed."""
    from datetime import datetime, timezone

    profile = setup_store.get_profile(system_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="unknown system_id")
    if profile.status != "draft":
        raise HTTPException(status_code=409, detail="only drafts confirm")
    conflicts = setup_store.get_conflicts(system_id)
    data = profile.model_dump(mode="json")
    for pick in payload.resolve:
        match = next(
            (
                conflict
                for conflict in conflicts
                if conflict.get("field") == pick.get("field")
                and conflict.get("key") == pick.get("key")
            ),
            None,
        )
        if match is None:
            raise HTTPException(status_code=400, detail="unknown conflict")
        try:
            chosen = match["values"][pick["pick"]]
        except (KeyError, IndexError, TypeError) as exc:
            raise HTTPException(status_code=400, detail="bad pick") from exc
        field = match["field"]
        if field == "environment":
            data["environment"][match["key"]] = chosen["value"]
        else:
            id_key = {
                "normal_ranges": "metric",
                "expected_behaviours": "name",
                "modes": "mode",
                "failure_definitions": "name",
            }[field]
            entry = dict(chosen["value"])
            entry[id_key] = match["key"]
            entry["provenance"] = {
                "source_doc": chosen["doc"],
                "page_or_region": "",
                "quote": chosen.get("quote", ""),
                "confidence": 0.9,
                "confirmed_by": payload.confirmed_by,
                "confirmed_at": datetime.now(timezone.utc).isoformat(),
            }
            data[field] = [
                item
                for item in data.get(field, [])
                if item.get(id_key) != match["key"]
            ] + [entry]
        conflicts = [c for c in conflicts if c is not match]
    if conflicts:
        raise HTTPException(
            status_code=409,
            detail=f"{len(conflicts)} conflict(s) still unresolved",
        )
    stamped = datetime.now(timezone.utc).isoformat()
    for section in (
        "normal_ranges",
        "expected_behaviours",
        "modes",
        "failure_definitions",
        "hard_limits",
    ):
        for entry in data.get(section, []):
            provenance = entry.setdefault("provenance", {})
            provenance.setdefault("confirmed_by", payload.confirmed_by)
            provenance.setdefault("confirmed_at", stamped)
    data["status"] = "confirmed"
    try:
        confirmed = SystemProfile.model_validate(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    stored = setup_store.save_profile(confirmed)
    setup_store.save_conflicts(system_id, [])
    await hub.broadcast(
        SimEvent(
            kind="setup_progress",
            payload={
                "system_id": system_id,
                "stage": "confirmed",
                "version": stored.version,
            },
        )
    )
    return stored.model_dump(mode="json")


@app.post("/api/systems/{system_id}/arm")
async def arm_system(system_id: str) -> dict:
    """Confirmed → armed: watchers start acting on this system."""
    profile = setup_store.get_profile(system_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="unknown system_id")
    if profile.status != "confirmed":
        raise HTTPException(
            status_code=409,
            detail=f"only confirmed systems arm (now {profile.status})",
        )
    stored = setup_store.save_profile(
        profile.model_copy(update={"status": "armed"})
    )
    await hub.broadcast(
        SimEvent(
            kind="setup_progress",
            payload={"system_id": system_id, "stage": "armed"},
        )
    )
    return stored.model_dump(mode="json")


class SampleIn(BaseModel):
    sample: str = Field(pattern=r"^(shop|coldchain)$")


@app.post("/api/systems/{system_id}/profile/sample")
async def load_sample_profile(system_id: str, payload: SampleIn) -> dict:
    """Skip extraction in the demo: load a pre-confirmed sample as draft."""
    profile = setup_store.get_profile(system_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="unknown system_id")
    sample_path = (
        Path(__file__).resolve().parent.parent.parent
        / "demo"
        / "setup"
        / "profiles"
        / f"{payload.sample}.json"
    )
    try:
        sample = SystemProfile.model_validate_json(
            sample_path.read_text(encoding="utf-8")
        )
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if sample.kind != profile.kind:
        raise HTTPException(
            status_code=400,
            detail=f"sample is {sample.kind}, system is {profile.kind}",
        )
    draft = sample.model_copy(
        update={
            "system_id": system_id,
            "name": profile.name,
            "status": "draft",
        }
    )
    stored = setup_store.save_profile(draft)
    setup_store.save_conflicts(system_id, [])
    return stored.model_dump(mode="json")


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
    run_steps.clear()
    pending_actions.clear()
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
