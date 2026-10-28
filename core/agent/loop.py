from __future__ import annotations

import os
import time
from typing import Any, Callable, Optional
from uuid import uuid4

from core.infer import baseten_client, fireworks_client, meta_client
from core.infer.meta_client import DIAGNOSIS_MODEL, ESCALATION_MODEL
from core.schemas.remediation import ApplianceResult, ExecutionResult, VerificationResult
from core.schemas.telemetry import ApplianceTelemetry, SoftwareTelemetry
from core.setup.gate import gate_has_impact
from core.verify.safety_rules import validate_runbook
from core.verify.sandbox import ORIGINAL_PASS_PREFIX, verify_fix, verify_patch

EventCallback = Callable[[dict], None]
MAX_DETAIL_CHARS = 2000


def _emit(on_event: Optional[EventCallback], event: dict) -> None:
    if on_event is not None:
        on_event(event)


def _ms(since: float) -> float:
    return (time.perf_counter() - since) * 1000.0


def _truncate(text: str, limit: int = MAX_DETAIL_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


def _diagnosis_detail(diagnosis: Any) -> str:
    summary = getattr(diagnosis, "summary", "") or ""
    cause = getattr(diagnosis, "likely_cause", "") or ""
    text = summary if not cause else f"{summary} — likely cause: {cause}"
    return _truncate(text)


def _fix_detail(fix: Any) -> str:
    patch_code = getattr(fix, "patch_code", None)
    if isinstance(patch_code, str):
        test_code = getattr(fix, "test_code", "") or ""
        return f"patch ({len(patch_code)} chars) + test ({len(test_code)} chars)"
    steps = getattr(fix, "steps", None)
    if isinstance(steps, list):
        target = getattr(fix, "target_temperature_c", "?")
        return f"runbook: {len(steps)} steps, hold at {target}°C"
    return type(fix).__name__


def _has(value: str) -> bool:
    return bool(value and value.strip())


def run_loop(
    telemetry,
    diagnose,
    generate_fix,
    verify,
    act,
    escalate,
    max_attempts: int = 3,
    on_event: Optional[EventCallback] = None,
    early_stop: Optional[Callable[[Any], Optional[Any]]] = None,
):
    """Shared diagnose → generate → verify → act loop with final-attempt escalation.

    `early_stop` (P6) sees the diagnosis right after the diagnose step; a
    non-None return ends the run immediately with that outcome.
    """
    max_attempts = max(1, max_attempts)
    started = time.perf_counter()
    diagnosis = diagnose(telemetry)
    _emit(on_event, {"step": "diagnose", "status": "ok",
                     "duration_ms": _ms(started),
                     "detail": _diagnosis_detail(diagnosis),
                     "suggestions": list(getattr(diagnosis, "suggested_actions", None) or [])})
    if early_stop is not None:
        stopped = early_stop(diagnosis)
        if stopped is not None:
            return stopped
    feedback = None
    for attempt in range(1, max_attempts + 1):
        generator = escalate if attempt == max_attempts else generate_fix
        gen_started = time.perf_counter()
        fix = generator(diagnosis, feedback)
        _emit(on_event, {"step": "generate", "attempt": attempt, "status": "ok",
                         "duration_ms": _ms(gen_started),
                         "detail": _fix_detail(fix)})
        ver_started = time.perf_counter()
        result = verify(fix)
        _emit(
            on_event,
            {"step": "verify", "attempt": attempt,
             "status": "PASS" if result.passed else "FAIL",
             "duration_ms": _ms(ver_started),
             "detail": _truncate(result.feedback or "")},
        )
        if result.passed:
            return act(fix, diagnosis, result, attempts=attempt)
        feedback = result.feedback
    return {"status": "FAIL", "attempts": max_attempts, "feedback": feedback}


def _software_providers() -> list:
    providers = []
    if _has(os.environ.get("BASETEN_API_KEY", "")):
        providers.append(
            (f"baseten:{baseten_client.GENERATION_MODEL}", baseten_client.generate_patch)
        )
    if _has(os.environ.get("FIREWORKS_API_KEY", "")) and _has(fireworks_client.patch_model()):
        providers.append(
            (f"fireworks:{fireworks_client.patch_model()}", fireworks_client.generate_patch)
        )
    if _has(os.environ.get("MODEL_API_KEY", "")) or _has(
        os.environ.get("META_MODEL_API_KEY", "")
    ):
        providers.append(
            (
                f"meta:{DIAGNOSIS_MODEL}",
                lambda diagnosis, feedback, contract=None: (
                    meta_client.generate_patch(
                        diagnosis, feedback, model=DIAGNOSIS_MODEL,
                        contract=contract,
                    )
                ),
            )
        )
    return providers


def _runbook_providers() -> list:
    providers = []
    if _has(os.environ.get("BASETEN_API_KEY", "")):
        providers.append(
            (f"baseten:{baseten_client.GENERATION_MODEL}", baseten_client.generate_runbook)
        )
    if _has(os.environ.get("FIREWORKS_API_KEY", "")) and _has(fireworks_client.patch_model()):
        providers.append(
            (f"fireworks:{fireworks_client.patch_model()}", fireworks_client.generate_runbook)
        )
    if _has(os.environ.get("MODEL_API_KEY", "")) or _has(
        os.environ.get("META_MODEL_API_KEY", "")
    ):
        providers.append(
            (
                f"meta:{DIAGNOSIS_MODEL}",
                lambda diagnosis, feedback: meta_client.generate_runbook(
                    diagnosis, feedback, model=DIAGNOSIS_MODEL
                ),
            )
        )
    return providers


def run_software_loop(
    telemetry: SoftwareTelemetry,
    max_attempts: int = 3,
    on_event: Optional[EventCallback] = None,
    original_code: Optional[str] = None,
    open_pr: Optional[Callable[..., str]] = None,
    run_id: Optional[str] = None,
    contract: Optional[str] = None,
    harness: Optional[str] = None,
    reference: str = "",
    gate: Optional[dict] = None,
) -> ExecutionResult:
    """Software loop; `open_pr` opens the fix PR and returns its URL.

    When `open_pr` is None the PR step is skipped (pr_url stays None), which
    keeps local runs and unit tests hermetic. Production callers pass
    `core.actions.github_pr.open_fix_pr`.

    `contract` pins the required module interface in every generation call;
    `harness` is repo-owned pytest executed against each patch in the sandbox
    before fail-to-pass, so a patch that ignores the contract fails fast with
    actionable feedback instead of deploying.

    P6: `reference` is profile reference data shown to the diagnosing model;
    `gate` is the gate decision that started the run. A diagnosis of
    expected behaviour with no gate impact ends the run as NO_ACTION.
    """
    run_id = run_id or uuid4().hex[:8]
    state: dict[str, Any] = {"model": "none"}

    def emit(event: dict) -> None:
        _emit(on_event, {"model": state["model"], "domain": "software",
                         "run_id": run_id, **event})

    def diagnose(_telemetry) -> Any:
        state["model"] = f"meta:{DIAGNOSIS_MODEL}"
        if reference:
            return meta_client.diagnose(
                telemetry.model_dump_json(), reference=reference
            )
        return meta_client.diagnose(telemetry.model_dump_json())

    def early_stop(diagnosis: Any) -> Optional[ExecutionResult]:
        if not getattr(diagnosis, "is_expected", False):
            return None
        if gate_has_impact(gate):
            return None
        reason = (
            getattr(diagnosis, "expected_reason", "")
            or "No action: normal behaviour"
        )
        return ExecutionResult(
            status="NO_ACTION",
            stdout=reason,
            stderr="",
            attempts=0,
            model_used=state["model"],
            run_id=run_id,
        )

    def generate_fix(diagnosis, feedback):
        last_error = "No patch provider is configured; set BASETEN_API_KEY or MODEL_API_KEY."
        for name, generate in _software_providers():
            try:
                patch = generate(diagnosis, feedback, contract=contract)
                state["model"] = name
                return patch
            except Exception as exc:
                last_error = str(exc) or type(exc).__name__
        raise RuntimeError(last_error)

    def escalate(diagnosis, feedback):
        state["model"] = f"meta:{ESCALATION_MODEL}"
        return meta_client.generate_patch(
            diagnosis, feedback, model=ESCALATION_MODEL, contract=contract
        )

    def verify(patch) -> VerificationResult:
        if harness:
            head = verify_patch(patch.patch_code, harness)
            if not head["passed"]:
                return VerificationResult(
                    passed=False,
                    feedback="Interface harness failed:\n" + head["feedback"],
                )
        if original_code:
            outcome = verify_fix(
                original_code, patch.patch_code, patch.test_code
            )
            state["checked_original"] = True
            if not outcome["feedback"].startswith(ORIGINAL_PASS_PREFIX):
                state["saw_failing_original"] = True
            return VerificationResult(**outcome)
        return VerificationResult(**verify_patch(patch.patch_code, patch.test_code))

    def act(patch, diagnosis, result, attempts: int) -> ExecutionResult:
        pr_url = None
        if open_pr is not None:
            pr_url = open_pr(
                diagnosis=diagnosis,
                patch=patch,
                verification_feedback=result.feedback,
                attempts=attempts,
                model_used=state["model"],
            )
        return ExecutionResult(
            status="PASS",
            stdout=result.feedback,
            stderr="",
            attempts=attempts,
            model_used=state["model"],
            pr_url=pr_url,
            run_id=run_id,
            patch_code=patch.patch_code,
        )

    outcome = run_loop(telemetry, diagnose, generate_fix, verify, act, escalate,
                       max_attempts, emit, early_stop)
    if isinstance(outcome, ExecutionResult):
        return outcome
    feedback = outcome.get("feedback") or ""
    if (
        original_code
        and state.get("checked_original")
        and not state.get("saw_failing_original")
    ):
        human = "Possibly intended behaviour, needs human."
        feedback = f"{human}\n{feedback}" if feedback else human
    return ExecutionResult(
        status="FAIL",
        stdout="",
        stderr=feedback,
        attempts=outcome["attempts"],
        model_used=state["model"],
        run_id=run_id,
    )


def run_appliance_loop(
    telemetry: ApplianceTelemetry,
    max_attempts: int = 3,
    on_event: Optional[EventCallback] = None,
    send_alert: Optional[Callable[..., Any]] = None,
    run_id: Optional[str] = None,
    reference: str = "",
    gate: Optional[dict] = None,
    profile: Any = None,
) -> ApplianceResult:
    """Appliance loop through the same shared core: diagnose → runbook → safety-check → alert.

    When `send_alert` is None the alert step is skipped (alert stays None).
    Production callers pass `core.actions.notify.send_alert`.

    P6: `reference` is profile reference data for the model, `gate` is the
    gate decision that started the run, and `profile` tightens runbook
    safety validation with the system's own limits.
    """
    run_id = run_id or uuid4().hex[:8]
    state = {"model": "none"}

    def emit(event: dict) -> None:
        _emit(on_event, {"model": state["model"], "domain": "appliance",
                         "run_id": run_id, **event})

    def diagnose(_telemetry) -> Any:
        state["model"] = f"meta:{DIAGNOSIS_MODEL}"
        if reference:
            return meta_client.diagnose(
                telemetry.model_dump_json(), reference=reference
            )
        return meta_client.diagnose(telemetry.model_dump_json())

    def early_stop(diagnosis: Any) -> Optional[ApplianceResult]:
        if not getattr(diagnosis, "is_expected", False):
            return None
        if gate_has_impact(gate):
            return None
        reason = (
            getattr(diagnosis, "expected_reason", "")
            or "No action: normal behaviour"
        )
        return ApplianceResult(
            status="NO_ACTION",
            feedback=reason,
            attempts=0,
            model_used=state["model"],
            run_id=run_id,
        )

    def generate_fix(diagnosis, feedback):
        last_error = "No runbook provider is configured; set BASETEN_API_KEY or MODEL_API_KEY."
        for name, generate in _runbook_providers():
            try:
                runbook = generate(diagnosis, feedback)
                state["model"] = name
                return runbook
            except Exception as exc:
                last_error = str(exc) or type(exc).__name__
        raise RuntimeError(last_error)

    def escalate(diagnosis, feedback):
        state["model"] = f"meta:{ESCALATION_MODEL}"
        return meta_client.generate_runbook(diagnosis, feedback, model=ESCALATION_MODEL)

    def verify(runbook) -> VerificationResult:
        violations = validate_runbook(
            runbook, telemetry.appliance_type, profile=profile
        )
        if violations:
            return VerificationResult(passed=False, feedback="\n".join(violations))
        return VerificationResult(
            passed=True, feedback="Runbook passed all safety checks (0 violations)."
        )

    def act(runbook, diagnosis, result, attempts: int) -> ApplianceResult:
        alert = None
        if send_alert is not None:
            alert = send_alert(
                diagnosis=diagnosis,
                runbook=runbook,
                attempts=attempts,
                model_used=state["model"],
            )
        return ApplianceResult(
            status="PASS",
            runbook=runbook,
            alert=alert,
            attempts=attempts,
            model_used=state["model"],
            run_id=run_id,
        )

    outcome = run_loop(telemetry, diagnose, generate_fix, verify, act, escalate,
                       max_attempts, emit, early_stop)
    if isinstance(outcome, ApplianceResult):
        return outcome
    return ApplianceResult(
        status="FAIL",
        feedback=outcome.get("feedback") or "",
        attempts=outcome["attempts"],
        model_used=state["model"],
        run_id=run_id,
    )


def run_diagnostic_loop(
    log_text: str,
    max_attempts: int = 3,
    on_event: Optional[EventCallback] = None,
    original_code: Optional[str] = None,
    open_pr: Optional[Callable[..., str]] = None,
    run_id: Optional[str] = None,
    contract: Optional[str] = None,
    harness: Optional[str] = None,
    reference: str = "",
    gate: Optional[dict] = None,
) -> ExecutionResult:
    telemetry = SoftwareTelemetry(source_id="api", raw_log=log_text)
    return run_software_loop(
        telemetry,
        max_attempts=max_attempts,
        on_event=on_event,
        original_code=original_code,
        open_pr=open_pr,
        run_id=run_id,
        contract=contract,
        harness=harness,
        reference=reference,
        gate=gate,
    )
