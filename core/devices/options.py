"""Production fix options for appliance incidents (John, N-R1).

Builds the roadmap §3.4 Option list from a stored appliance run's runbook +
profile. Pure function of (run entry, profile, now): no I/O, no router
imports, no changes to the agent loop.

Safety posture (fail closed):
- remote options need a runbook that passes the existing deterministic
  `validate_runbook` rules (hard bounds + the system's own profile limits);
- Lower setpoint re-validates a runbook copy at the new target, so profile
  hard limits and policy ceilings apply to the *new* setpoint;
- Power-cycle is additionally time-gated on the runbook's restart_delay_s
  measured from the run's `started_at`, and refused when that is unknown;
- anything unsafe gets `safety.ok=false` and is never executable.
"""

from __future__ import annotations

import re
import time
from typing import Any, Optional

from core.schemas.profile import SystemProfile
from core.schemas.remediation import ApplianceResult, Runbook
from core.verify.safety_rules import validate_runbook

#: Phone-number-ish owner contacts become tel: links on the dispatch option.
_PHONE_RE = re.compile(r"^\+?\d{7,}$")

#: Policy keywords (matched against profile.policy.forbidden_actions, case
#: insensitive) that disable one remote option. Fail-closed by design.
_POLICY_KEYWORDS = {
    "opt_defrost": ("defrost",),
    "opt_power_cycle": (
        "power-cycle",
        "power cycle",
        "powercycle",
        "power off",
        "power-off",
        "poweroff",
        "restart",
        "reboot",
    ),
    "opt_backup": (
        "backup unit",
        "switch to backup",
        "failover",
        "switch over",
        "switchover",
    ),
}


def _as_runbook(result: Any) -> Optional[Runbook]:
    runbook = None
    if isinstance(result, ApplianceResult):
        runbook = result.runbook
    elif isinstance(result, dict):
        runbook = result.get("runbook")
    if isinstance(runbook, Runbook):
        return runbook
    if isinstance(runbook, dict):
        try:
            return Runbook(**runbook)
        except Exception:
            return None
    return None


def _alert_work_order(result: Any) -> str:
    alert = None
    if isinstance(result, ApplianceResult):
        alert = result.alert
    elif isinstance(result, dict):
        alert = result.get("alert")
    if alert is None:
        return ""
    if isinstance(alert, dict):
        return str(alert.get("work_order") or "")
    return str(getattr(alert, "work_order", "") or "")


def _policy_hit(profile: Optional[SystemProfile], option_id: str) -> str:
    """The forbidden_actions entry disabling this option, or ''."""
    if profile is None:
        return ""
    keywords = _POLICY_KEYWORDS.get(option_id, ())
    for forbidden in profile.policy.forbidden_actions:
        text = forbidden.lower()
        if any(keyword in text for keyword in keywords):
            return forbidden
    return ""


def _option(
    id: str,
    kind: str,
    title: str,
    detail: str = "",
    url: str = "",
    ok: bool = True,
    reason: str = "",
) -> dict:
    return {
        "id": id,
        "kind": kind,
        "title": title,
        "detail": detail,
        "url": url,
        "safety": {"ok": ok, "reason": reason},
        "status": "available",
    }


def _tel_url(owner_contact: str) -> str:
    digits = re.sub(r"[\s\-().]", "", owner_contact)
    if digits and _PHONE_RE.match(digits):
        return f"tel:{digits}"
    return ""


def build_appliance_options(
    run: dict,
    profile: Optional[SystemProfile] = None,
    now: Optional[float] = None,
) -> list[dict]:
    """§3.4 options for one stored appliance run entry.

    `run` is the stored entry (`appliance_type`, `result`, `started_at`,
    `run_id`). `profile` is the system's profile or None when the run
    cannot be linked to one (degraded: hard bounds only).
    """
    now = time.time() if now is None else now
    appliance_type = str(run.get("appliance_type") or "")
    result = run.get("result")
    runbook = _as_runbook(result)
    validated = (
        runbook is not None
        and validate_runbook(runbook, appliance_type, profile) == []
    )
    no_runbook = "no validated runbook for this run"

    options: list[dict] = []

    # --- remote: Start defrost -------------------------------------------
    reason = ""
    if not validated:
        reason = no_runbook
    else:
        hit = _policy_hit(profile, "opt_defrost")
        if hit:
            reason = f"profile policy forbids it: {hit!r}"
    options.append(
        _option(
            "opt_defrost",
            "remote",
            "Start defrost",
            detail="Run the defrost cycle now.",
            ok=not reason,
            reason=reason,
        )
    )

    # --- remote: Lower setpoint 1 °C --------------------------------------
    reason = ""
    detail = ""
    if not validated or runbook is None:
        reason = no_runbook
    else:
        new_target = round(runbook.target_temperature_c - 1.0, 1)
        detail = (
            f"Hold {new_target:g} °C "
            f"(from {runbook.target_temperature_c:g} °C)."
        )
        moved = runbook.model_copy(
            update={"target_temperature_c": new_target}
        )
        violations = validate_runbook(moved, appliance_type, profile)
        if violations:
            reason = violations[0]
    options.append(
        _option(
            "opt_setpoint_minus_1",
            "remote",
            "Lower setpoint 1 °C",
            detail=detail,
            ok=not reason,
            reason=reason,
        )
    )

    # --- remote: Power-cycle compressor -----------------------------------
    reason = ""
    detail = ""
    delay = runbook.restart_delay_s if runbook is not None else 0
    if not validated or runbook is None:
        reason = no_runbook
    else:
        detail = f"Respecting the {delay}s restart delay."
        hit = _policy_hit(profile, "opt_power_cycle")
        started_at = run.get("started_at")
        if hit:
            reason = f"profile policy forbids it: {hit!r}"
        elif not isinstance(started_at, (int, float)):
            reason = "compressor stop time unknown — refusing to restart blind"
        elif now - float(started_at) < delay:
            wait = delay - (now - float(started_at))
            reason = f"wait {wait:.0f}s more (restart delay {delay}s)"
    options.append(
        _option(
            "opt_power_cycle",
            "remote",
            "Power-cycle compressor",
            detail=detail,
            ok=not reason,
            reason=reason,
        )
    )

    # --- remote: Switch to backup unit ------------------------------------
    reason = ""
    if not validated:
        reason = no_runbook
    else:
        hit = _policy_hit(profile, "opt_backup")
        if hit:
            reason = f"profile policy forbids it: {hit!r}"
    options.append(
        _option(
            "opt_backup",
            "remote",
            "Switch to backup unit",
            detail="Move the load to the backup unit.",
            ok=not reason,
            reason=reason,
        )
    )

    # --- manual: the runbook steps as an on-site checklist -----------------
    if runbook is not None:
        position = 0
        for step in runbook.steps:
            text = str(step).strip()
            if not text:
                continue
            position += 1
            options.append(
                _option(
                    f"opt_manual_{position}",
                    "manual",
                    text,
                    ok=validated,
                    reason="" if validated else "runbook failed safety validation",
                )
            )

    # --- dispatch: always available, never gated ---------------------------
    work_order = _alert_work_order(result)
    run_id = str(run.get("run_id") or "")
    if work_order:
        dispatch_detail = work_order
    elif run_id:
        dispatch_detail = f"On-call technician dispatch for run {run_id}."
    else:
        dispatch_detail = "On-call technician dispatch."
    contact = profile.owner_contact if profile is not None else ""
    options.append(
        _option(
            "opt_dispatch",
            "dispatch",
            "Call or WhatsApp the technician",
            detail=dispatch_detail,
            url=_tel_url(contact),
        )
    )
    return options


def device_command_for(
    option_id: str,
    run: dict,
    profile: Optional[SystemProfile] = None,
    now: Optional[float] = None,
) -> Optional[dict]:
    """Device command for a remote option, re-validated at execute time.

    Returns {"action", "params"} with an action from the §3.4 command
    vocabulary (defrost|setpoint|power_cycle|backup_on), or None when the
    option is unknown, not remote, or no longer safe.
    """
    options = {option["id"]: option for option in build_appliance_options(
        run, profile, now
    )}
    option = options.get(option_id)
    if option is None or option["kind"] != "remote":
        return None
    if not option["safety"]["ok"]:
        return None
    runbook = _as_runbook(run.get("result"))
    if runbook is None:  # unreachable when safety passed; fail closed anyway
        return None
    if option_id == "opt_defrost":
        return {"action": "defrost", "params": {}}
    if option_id == "opt_setpoint_minus_1":
        return {
            "action": "setpoint",
            "params": {
                "target_c": round(runbook.target_temperature_c - 1.0, 1)
            },
        }
    if option_id == "opt_power_cycle":
        return {
            "action": "power_cycle",
            "params": {"min_off_s": runbook.restart_delay_s},
        }
    if option_id == "opt_backup":
        return {"action": "backup_on", "params": {}}
    return None
