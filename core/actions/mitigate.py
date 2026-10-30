"""Safe production mitigations: rollback + restart ONLY (J-R4).

Allowlist (`rollback`, `restart`) is checked first, so `stop`, `delete`,
`scale-0` and anything else the model suggests is impossible. Two paths:

* human: John's options route calls `execute()` directly (explicit tap);
* server-proposed: `propose()` opens a 20 s window (existing PendingAction
  shape + `action_pending/tick/resolved` events John's app already shows);
  approve runs the adapter, disapprove/expiry cancels, pause freezes all.

Gates, in order: allowlist → paused → learning → rate (1/system/10 min) →
policy (proposals) → hosting connection. Executions stamp the rate file,
append the audit log, and set the run's `mitigation` summary (§3.4).

Adapters: Railway GraphQL (redeploy previous SUCCESS / restart latest) and
a signed webhook (HMAC-SHA256 POST the customer's script verifies).
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

import httpx

from core.actions.auto_action import (
    PendingAction,
    auto_enabled,
    window_seconds,
)
from core.schemas.production import Option, OptionSafety

log = logging.getLogger(__name__)

#: The ONLY actions that can ever run. Everything else is refused.
ALLOWLIST = ("rollback", "restart")

#: 1 automatic-or-human mitigation per system per 10 minutes (§2.6).
RATE_LIMIT_S = 600.0

#: Audit ring size in the state file.
MAX_AUDIT_ENTRIES = 500

RAILWAY_API = "https://backboard.railway.app/graphql/v2"
WEBHOOK_TIMEOUT_S = 15.0
RAILWAY_TIMEOUT_S = 20.0

#: In-memory rate stamps (atomic check-and-set; file is for restarts).
_last_action: Dict[str, float] = {}

#: Open mitigation windows + their action/system (keyed by run_id).
_windows: Dict[str, PendingAction] = {}
_window_actions: Dict[str, str] = {}
_window_systems: Dict[str, str] = {}
_ticker_task: Optional["asyncio.Task"] = None


def _data_root() -> str:
    from core.setup.store import data_root

    return str(data_root())


def _state_path() -> str:
    return os.path.join(_data_root(), "mitigations.json")


def _pause_path() -> str:
    return os.path.join(_data_root(), "pause.json")


def _read_json(path: str, default: dict) -> dict:
    try:
        with open(path, encoding="utf-8") as handle:
            loaded = json.load(handle)
    except (OSError, ValueError):
        return dict(default)
    return loaded if isinstance(loaded, dict) else dict(default)


def _write_json(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


# --- pause ---------------------------------------------------------------


def is_paused() -> bool:
    """Global pause switch (persisted; survives restarts)."""
    return bool(_read_json(_pause_path(), {}).get("paused", False))


def set_paused(paused: bool) -> bool:
    _write_json(_pause_path(), {"paused": bool(paused), "at": time.time()})
    return bool(paused)


# --- rate limit + audit ----------------------------------------------------


def _rate_state() -> dict:
    return _read_json(_state_path(), {"last": {}, "log": []})


def _rate_limited(system_id: str) -> Optional[float]:
    """Seconds until the next mitigation may run, or None when clear."""
    now = time.time()
    last = _last_action.get(system_id)
    if last is None:
        file_last = _rate_state().get("last", {}).get(system_id, 0.0)
        try:
            last = float(file_last)
        except (TypeError, ValueError):
            last = 0.0
        _last_action[system_id] = last
    wait = RATE_LIMIT_S - (now - last)
    return wait if wait > 0 else None


def _stamp_rate(system_id: str) -> None:
    now = time.time()
    _last_action[system_id] = now
    state = _rate_state()
    last = state.get("last", {})
    last[system_id] = now
    state["last"] = last
    _write_json(_state_path(), state)


def audit(entry: Dict[str, Any]) -> None:
    state = _rate_state()
    items = state.get("log", [])
    items.append({"ts": time.time(), **entry})
    state["log"] = items[-MAX_AUDIT_ENTRIES:]
    _write_json(_state_path(), state)


def reset_mitigate_state() -> None:
    """Clear in-memory rate stamps + windows (tests only)."""
    _last_action.clear()
    _windows.clear()
    _window_actions.clear()
    _window_systems.clear()


# --- profile / policy / hosting --------------------------------------------


def _profile(system_id: str) -> Optional[Any]:
    from core.setup import store as setup_store

    return setup_store.get_profile(system_id)


def policy_allows(profile: Any, action: str) -> bool:
    """Proposals need the action in policy.allowed_actions (/connect sets)."""
    if profile is None:
        return False
    allowed = getattr(profile.policy, "allowed_actions", []) or []
    return action in allowed


def hosting_for(system_id: str) -> Optional[Dict[str, Any]]:
    """Railway connection first, else webhook; None when neither."""
    from core.connections import store as connection_store

    connections = connection_store.list_connections(system_id)
    for kind in ("railway", "webhook"):
        for connection in connections:
            if connection.kind == kind:
                return {
                    "kind": kind,
                    "connection_id": connection.id,
                    "config": dict(connection.config or {}),
                    "secret": connection_store.get_secret(connection.id),
                }
    return None


def _refuse(reason: str, **extra: Any) -> Dict[str, Any]:
    return {"status": "refused", "reason": reason, **extra}


def _gate(
    system_id: str, action: str, *, check_policy: bool
) -> Optional[Dict[str, Any]]:
    """Shared gates; None when clear, else the refusal dict."""
    if action not in ALLOWLIST:
        return _refuse(
            f"action {action!r} is not allowlisted (rollback/restart only)"
        )
    if is_paused():
        return _refuse("actions are paused")
    profile = _profile(system_id)
    if profile is None:
        return _refuse("unknown system_id")
    if getattr(profile, "status", "") == "learning":
        return _refuse("system is still learning its baseline")
    wait = _rate_limited(system_id)
    if wait is not None:
        return _refuse(
            f"1 mitigation per 10 min; retry in {int(wait)}s",
            retry_in_s=int(wait),
        )
    if check_policy and not policy_allows(profile, action):
        return _refuse(f"policy does not allow {action}")
    if hosting_for(system_id) is None:
        return _refuse("no railway or webhook connection")
    return None


# --- adapters ----------------------------------------------------------------


def _railway_graphql(
    token: str,
    query: str,
    variables: Optional[dict] = None,
    client: Optional[httpx.Client] = None,
) -> dict:
    owned = client is None
    http = client or httpx.Client(timeout=RAILWAY_TIMEOUT_S)
    try:
        response = http.post(
            RAILWAY_API,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={"query": query, "variables": variables or {}},
        )
    except httpx.HTTPError as exc:
        raise RuntimeError(f"cannot reach Railway: {exc}") from exc
    finally:
        if owned:
            http.close()
    if response.status_code == 401:
        raise RuntimeError("Railway rejected the token (401)")
    if response.status_code != 200:
        raise RuntimeError(
            f"Railway error ({response.status_code}): "
            f"{response.text[:300]}"
        )
    try:
        body = response.json()
    except ValueError as exc:
        raise RuntimeError("Railway returned non-JSON") from exc
    errors = body.get("errors") or []
    if errors:
        raise RuntimeError(
            "Railway: " + "; ".join(
                str(item.get("message", item)) for item in errors[:3]
            )
        )
    return body.get("data", {}) or {}


def railway_check(
    token: str,
    client: Optional[httpx.Client] = None,
    service_id: str = "",
) -> dict:
    """Validate a Railway token; used by connection test."""
    if service_id:
        # Workspace tokens cannot query `me`; reading the service's
        # deployments is exactly what rollback needs anyway.
        try:
            deployments = _railway_deployments(token, service_id, client)
        except RuntimeError as exc:
            return {"ok": False, "detail": str(exc)}
        return {
            "ok": True,
            "detail": f"token can read service ({len(deployments)} deployments)",
        }
    try:
        data = _railway_graphql(
            token, "query { me { id email } }", client=client
        )
    except RuntimeError as exc:
        return {"ok": False, "detail": str(exc)}
    email = ((data.get("me") or {}).get("email")) or "unknown user"
    return {"ok": True, "detail": f"token valid ({email})"}


def _railway_deployments(
    token: str, service_id: str, client: Optional[httpx.Client]
) -> List[dict]:
    data = _railway_graphql(
        token,
        "query ($serviceId: String!) { deployments(first: 10, "
        "input: { serviceId: $serviceId }) { edges { node { id status "
        "createdAt } } } }",
        {"serviceId": service_id},
        client,
    )
    edges = ((data.get("deployments") or {}).get("edges")) or []
    return [edge.get("node", {}) for edge in edges if edge.get("node")]


def railway_rollback(
    config: Dict[str, Any],
    token: str,
    client: Optional[httpx.Client] = None,
) -> Dict[str, Any]:
    """Redeploy the newest SUCCESSFUL deployment (zero-downtime swap)."""
    service_id = str(config.get("service_id", "") or "").strip()
    if not service_id:
        return {
            "status": "failed",
            "detail": "railway connection needs config.service_id",
        }
    try:
        deployments = _railway_deployments(token, service_id, client)
    except RuntimeError as exc:
        return {"status": "failed", "detail": str(exc)}
    successful = [
        item
        for item in deployments
        if str(item.get("status", "")).upper() == "SUCCESS"
    ]
    if not successful:
        return {
            "status": "failed",
            "detail": "no successful deployment to roll back to",
        }
    target = sorted(
        successful, key=lambda item: str(item.get("createdAt", ""))
    )[-1]
    try:
        data = _railway_graphql(
            token,
            "mutation Redeploy($id: String!) { deploymentRedeploy(id: $id) "
            "{ id status } }",
            {"id": target["id"]},
            client,
        )
    except RuntimeError as exc:
        return {"status": "failed", "detail": str(exc)}
    redeployed = data.get("deploymentRedeploy", {}) or {}
    return {
        "status": "done",
        "detail": f"redeployed {target['id']} "
        f"(status {redeployed.get('status', '?')})",
        "deployment_id": target["id"],
    }


def railway_restart(
    config: Dict[str, Any],
    token: str,
    client: Optional[httpx.Client] = None,
) -> Dict[str, Any]:
    """Restart the latest deployment."""
    service_id = str(config.get("service_id", "") or "").strip()
    if not service_id:
        return {
            "status": "failed",
            "detail": "railway connection needs config.service_id",
        }
    try:
        deployments = _railway_deployments(token, service_id, client)
    except RuntimeError as exc:
        return {"status": "failed", "detail": str(exc)}
    if not deployments:
        return {"status": "failed", "detail": "no deployments found"}
    target = sorted(
        deployments, key=lambda item: str(item.get("createdAt", ""))
    )[-1]
    try:
        _railway_graphql(
            token,
            'mutation Restart($id: String!) { deploymentRestart(id: $id) }',
            {"id": target["id"]},
            client,
        )
    except RuntimeError as exc:
        return {"status": "failed", "detail": str(exc)}
    return {
        "status": "done",
        "detail": f"restarted {target['id']}",
        "deployment_id": target["id"],
    }


def webhook_signature(secret: str, raw_body: bytes) -> str:
    """`sha256=<hex>` HMAC the customer's script verifies."""
    digest = hmac.new(
        secret.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    return f"sha256={digest}"


def webhook_call(
    url: str,
    secret: str,
    payload: Dict[str, Any],
    client: Optional[httpx.Client] = None,
) -> Dict[str, Any]:
    """Signed POST to the customer's URL; 2xx is done."""
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-Telemetry-Signature": webhook_signature(secret, raw),
        "X-Telemetry-Timestamp": str(payload.get("ts", "")),
    }
    owned = client is None
    http = client or httpx.Client(timeout=WEBHOOK_TIMEOUT_S)
    try:
        try:
            response = http.post(url, content=raw, headers=headers)
        except httpx.HTTPError as exc:
            return {"status": "failed", "detail": f"webhook unreachable: {exc}"}
    finally:
        if owned:
            http.close()
    if 200 <= response.status_code < 300:
        return {
            "status": "done",
            "detail": f"webhook accepted ({response.status_code})",
        }
    return {
        "status": "failed",
        "detail": f"webhook error ({response.status_code}): "
        f"{response.text[:300]}",
    }


def webhook_ping(
    url: str, secret: str, client: Optional[httpx.Client] = None
) -> dict:
    """Test ping for the connection test (never runs an action)."""
    result = webhook_call(
        url,
        secret,
        {"action": "ping", "ts": time.time()},
        client,
    )
    if result["status"] == "done":
        return {"ok": True, "detail": "webhook answered the test ping"}
    return {"ok": False, "detail": result["detail"]}


def _run_adapter(
    hosting: Dict[str, Any],
    action: str,
    system_id: str,
    run_id: str,
    client: Optional[httpx.Client] = None,
) -> Dict[str, Any]:
    if hosting["kind"] == "railway":
        if action == "rollback":
            return railway_rollback(
                hosting["config"], hosting["secret"], client
            )
        return railway_restart(hosting["config"], hosting["secret"], client)
    url = str(hosting["config"].get("url", "") or "").strip()
    if not url:
        return {
            "status": "failed",
            "detail": "webhook connection needs config.url",
        }
    return webhook_call(
        url,
        hosting["secret"],
        {
            "action": action,
            "system_id": system_id,
            "run_id": run_id,
            "ts": time.time(),
        },
        client,
    )


# --- human path: execute now ---------------------------------------------------


def execute(
    system_id: str,
    action: str,
    run_id: str,
    decided_by: str = "",
    client: Optional[httpx.Client] = None,
) -> Dict[str, Any]:
    """Run one allowlisted mitigation now (explicit human tap)."""
    if action == "open_pr":
        return {"status": "noop", "detail": "open the PR url; nothing to run"}
    refused = _gate(system_id, action, check_policy=False)
    if refused is not None:
        refused.update(
            {"system_id": system_id, "action": action, "run_id": run_id}
        )
        return refused
    hosting = hosting_for(system_id)
    assert hosting is not None  # _gate guarantees a connection
    try:
        result = _run_adapter(hosting, action, system_id, run_id, client)
    except Exception as exc:  # adapters must never raise past here
        log.exception("mitigation adapter crashed: %s", exc)
        result = {"status": "failed", "detail": f"adapter error: {exc}"}
    if result["status"] == "done":
        # Only successful runs consume the rate budget; failures are
        # immediately retryable.
        _stamp_rate(system_id)
    _set_run_mitigation(
        run_id,
        {
            "action": action,
            "status": (
                "done" if result["status"] == "done" else result["status"]
            ),
        },
    )
    audit(
        {
            "system_id": system_id,
            "run_id": run_id,
            "action": action,
            "target": f"{hosting['kind']}:{hosting['connection_id']}",
            "status": result["status"],
            "detail": result.get("detail", ""),
            "decided_by": decided_by or "human",
        }
    )
    return {
        "status": result["status"],
        "system_id": system_id,
        "action": action,
        "run_id": run_id,
        **{k: v for k, v in result.items() if k != "status"},
    }


def _set_run_mitigation(run_id: str, mitigation: dict) -> None:
    try:
        from apps.api.main import software_runs
    except Exception:
        return
    entry = software_runs.get(run_id)
    if entry is None:
        return
    try:
        from core.schemas.production import MitigationSummary

        entry["result"].mitigation = MitigationSummary(**mitigation)
    except Exception:
        pass


# --- server-proposed path: 20 s windows ----------------------------------------


def _summary_for(action: str, system_id: str, hosting: Dict[str, Any]) -> str:
    if hosting["kind"] == "railway":
        service = hosting["config"].get("service_id", "?")
        target = f"Railway service {service}"
    else:
        target = f"webhook {hosting['config'].get('url', '?')}"
    verb = "Roll back" if action == "rollback" else "Restart"
    return f"{verb} {system_id} ({target})"


async def propose(
    system_id: str,
    run_id: str,
    action: str,
    auto_apply: bool = False,
    start_ticker: bool = True,
) -> Dict[str, Any]:
    """Open a veto window for one mitigation (policy-gated, approve-to-run).

    `auto_apply=False` (the default) means the window EXPIRES unless a
    human approves — nothing runs by itself until an error-rate feed can
    justify automatic action.
    """
    from apps.api.main import hub
    from core.schemas.events import SimEvent

    refused = _gate(system_id, action, check_policy=True)
    if refused is not None:
        refused.update(
            {"system_id": system_id, "action": action, "run_id": run_id}
        )
        return refused
    existing = _windows.get(run_id)
    if existing is not None and existing.state == "pending":
        return {
            "status": "proposed",
            "run_id": run_id,
            "deadline": existing.deadline,
            "detail": "window already open",
        }
    hosting = hosting_for(system_id)
    assert hosting is not None  # _gate guarantees a connection
    now = time.time()
    window = PendingAction(
        run_id=run_id,
        domain="software",
        action=_summary_for(action, system_id, hosting),
        opened_at=now,
        deadline=now + window_seconds(),
        auto_apply=auto_apply,
    )
    # The action/system ride alongside (PendingAction has no slot).
    _windows[run_id] = window
    _window_actions[run_id] = action
    _window_systems[run_id] = system_id
    await hub.broadcast(
        SimEvent(
            kind="action_pending",
            payload={
                **window.model_dump(mode="json"),
                "seconds": window_seconds(),
            },
        )
    )
    if start_ticker:
        _ensure_ticker()
    audit(
        {
            "system_id": system_id,
            "run_id": run_id,
            "action": f"proposed:{action}",
            "target": f"{hosting['kind']}:{hosting['connection_id']}",
            "status": "proposed",
            "detail": window.action,
            "decided_by": "server",
        }
    )
    return {"status": "proposed", "run_id": run_id, "deadline": window.deadline}


def _ensure_ticker() -> None:
    global _ticker_task
    if _ticker_task is not None and not _ticker_task.done():
        return
    loop = asyncio.get_running_loop()
    _ticker_task = loop.create_task(_ticker())


async def _ticker() -> None:
    while True:
        await asyncio.sleep(1.0)
        await settle_due()


async def settle_due(
    client: Optional[httpx.Client] = None,
) -> List[Dict[str, Any]]:
    """Expire or auto-run due windows; returns what settled."""
    from apps.api.main import hub
    from core.schemas.events import SimEvent

    settled: List[Dict[str, Any]] = []
    for run_id, window in list(_windows.items()):
        if window.state != "pending" or time.time() < window.deadline:
            continue
        action = _window_actions.get(run_id, "")
        system_id = _window_systems.get(run_id, "")
        hosting = hosting_for(system_id) if system_id else None
        if is_paused() or not auto_enabled() or not window.auto_apply:
            window.state = "expired"
            window.detail = "window expired without approval"
            window.resolved_at = time.time()
            settled.append({"run_id": run_id, "status": "expired"})
        elif (
            hosting is None
            or action not in ALLOWLIST
            or _rate_limited(system_id) is not None
        ):
            window.state = "expired"
            window.detail = "connection, action or rate no longer valid"
            window.resolved_at = time.time()
            settled.append({"run_id": run_id, "status": "expired"})
        else:
            try:
                result = _run_adapter(
                    hosting, action, system_id, run_id, client
                )
            except Exception as exc:
                result = {"status": "failed", "detail": f"adapter error: {exc}"}
            if result["status"] == "done":
                _stamp_rate(system_id)
            window.state = (
                "auto_applied" if result["status"] == "done" else "failed"
            )
            window.detail = result.get("detail", window.action)
            window.resolved_at = time.time()
            _set_run_mitigation(
                run_id, {"action": action, "status": window.state}
            )
            audit(
                {
                    "system_id": system_id,
                    "run_id": run_id,
                    "action": action,
                    "target": "window:auto",
                    "status": window.state,
                    "detail": window.detail,
                    "decided_by": "deadline",
                }
            )
            settled.append({"run_id": run_id, "status": window.state})
        await hub.broadcast(
            SimEvent(
                kind="action_resolved",
                payload=window.model_dump(mode="json"),
            )
        )
    return settled


async def decide(
    run_id: str, approve: bool, device: str = "phone",
    client: Optional[httpx.Client] = None,
) -> Dict[str, Any]:
    """Approve (run now) or disapprove (cancel) an open window."""
    from apps.api.main import hub
    from core.schemas.events import SimEvent

    window = _windows.get(run_id)
    if window is None:
        return {"status": "error", "reason": "unknown run_id"}
    if window.state != "pending":
        return {"status": "error", "reason": f"window already {window.state}"}
    if time.time() >= window.deadline:
        return {"status": "error", "reason": "too late: deadline passed"}
    action = _window_actions.get(run_id, "")
    system_id = _window_systems.get(run_id, "")
    if not approve:
        window.state = "disapproved"
        window.detail = f"cancelled by {device}"
        window.decided_by = device
        window.resolved_at = time.time()
        await hub.broadcast(
            SimEvent(
                kind="action_resolved",
                payload=window.model_dump(mode="json"),
            )
        )
        return {"status": "cancelled", "run_id": run_id}
    if is_paused():
        return {"status": "error", "reason": "actions are paused"}
    hosting = hosting_for(system_id) if system_id else None
    if hosting is None or action not in ALLOWLIST:
        window.state = "failed"
        window.detail = "connection removed or action invalid"
        window.resolved_at = time.time()
        return {"status": "failed", "reason": window.detail}
    wait = _rate_limited(system_id) if system_id else None
    if wait is not None:
        return {
            "status": "error",
            "reason": f"1 mitigation per 10 min; retry in {int(wait)}s",
        }
    try:
        result = _run_adapter(hosting, action, system_id, run_id, client)
    except Exception as exc:
        result = {"status": "failed", "detail": f"adapter error: {exc}"}
    if result["status"] == "done":
        _stamp_rate(system_id)
    window.state = "approved" if result["status"] == "done" else "failed"
    window.decided_by = device
    window.detail = (
        f"applied by {device}"
        if result["status"] == "done"
        else result.get("detail", "")
    )
    window.resolved_at = time.time()
    _set_run_mitigation(
        run_id, {"action": action, "status": window.state}
    )
    audit(
        {
            "system_id": system_id,
            "run_id": run_id,
            "action": action,
            "target": f"{hosting['kind']}:{hosting['connection_id']}",
            "status": window.state,
            "detail": window.detail,
            "decided_by": device,
        }
    )
    await hub.broadcast(
        SimEvent(
            kind="action_resolved",
            payload=window.model_dump(mode="json"),
        )
    )
    return {
        "status": result["status"],
        "run_id": run_id,
        **{k: v for k, v in result.items() if k != "status"},
    }


# --- John's options ------------------------------------------------------------


def _run_result(run: dict) -> Any:
    result = run.get("result", run)
    return result


def _result_field(result: Any, name: str, default: Any = "") -> Any:
    if isinstance(result, dict):
        return result.get(name, default)
    return getattr(result, name, default)


def software_options(run: dict) -> List[Option]:
    """open_pr / rollback / restart options in the §3.4 Option shape."""
    if not isinstance(run, dict):
        return []
    if run.get("domain") == "appliance":
        return []
    result = _run_result(run)
    gate = run.get("gate", {}) or {}
    system_id = str(
        run.get("system_id", "") or gate.get("system_id", "")
    )
    run_id = str(run.get("run_id", "") or gate.get("run_id", ""))
    options: List[Option] = []
    pr_url = str(_result_field(result, "pr_url", "") or "")
    if pr_url:
        options.append(
            Option(
                id="opt_open_pr",
                kind="open_pr",
                title="Open fix PR",
                detail="Verified fix with fail-to-pass proof",
                url=pr_url,
                safety=OptionSafety(ok=True),
                status="available",
            )
        )
    hosting = hosting_for(system_id) if system_id else None
    for action in ("rollback", "restart"):
        ok, reason = _option_safety(system_id, action, hosting)
        detail = (
            _summary_for(action, system_id, hosting)
            if hosting is not None
            else "Connect Railway or a webhook to enable"
        )
        options.append(
            Option(
                id=f"opt_{action}",
                kind=action,  # type: ignore[arg-type]
                title="Roll back to previous deploy"
                if action == "rollback"
                else "Restart service",
                detail=detail,
                # The safety object is the gate; the option stays listed
                # with its reason so the UI can explain itself.
                safety=OptionSafety(ok=ok, reason=reason),
                status="available",
            )
        )
    return options


def action_for_option_id(option_id: str) -> Optional[str]:
    """Allowlisted action for an option id (John's execute route)."""
    for action in ("open_pr", *ALLOWLIST):
        if option_id == f"opt_{action}":
            return action
    return None


def _option_safety(
    system_id: str, action: str, hosting: Optional[Dict[str, Any]]
) -> tuple:
    if not system_id:
        return False, "unknown system"
    if is_paused():
        return False, "actions are paused"
    profile = _profile(system_id)
    if profile is None:
        return False, "unknown system"
    if getattr(profile, "status", "") == "learning":
        return False, "system is still learning"
    wait = _rate_limited(system_id)
    if wait is not None:
        return False, f"rate limited; retry in {int(wait)}s"
    if hosting is None:
        return False, "no railway or webhook connection"
    return True, ""
