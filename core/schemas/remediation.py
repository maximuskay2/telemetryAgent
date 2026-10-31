from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from core.schemas.production import MitigationSummary, SuiteSummary


def normalize_code(code: str) -> str:
    """Undo one layer of escape doubling in model-generated Python.

    Providers return JSON, so one `json.loads` decodes the model's `\\n`
    escapes. Some models double-escape, leaving literal backslash-n text
    that fails collection with `SyntaxError: unexpected character after
    line continuation character`. Only rewrite when the blob does not
    compile as-is and the decoded form does; valid code (including
    intentional `"a\\n"` string escapes) passes through untouched.
    """
    if not isinstance(code, str) or "\\n" not in code:
        return code
    try:
        compile(code, "<generated>", "exec")
    except (SyntaxError, ValueError):
        pass
    else:
        return code
    try:
        decoded = code.encode("ascii").decode("unicode_escape")
    except (UnicodeEncodeError, UnicodeDecodeError, ValueError):
        return code
    try:
        compile(decoded, "<generated>", "exec")
    except (SyntaxError, ValueError):
        return code
    return decoded


class GeneratedPatch(BaseModel):
    patch_code: str = Field(min_length=1, description="Python module implementing the fix")
    test_code: str = Field(min_length=1, description="Pytest suite asserting the fix")

    @field_validator("patch_code", "test_code", mode="before")
    @classmethod
    def _unescape_doubled_code(cls, value: object) -> object:
        if isinstance(value, str):
            return normalize_code(value)
        return value


class Runbook(BaseModel):
    steps: list[str] = Field(default_factory=list, description="Ordered technician/owner actions")
    target_temperature_c: float = Field(description="Required holding temperature in Celsius")
    restart_delay_s: int = Field(ge=0, description="Compressor restart delay in seconds")
    power_off_minutes: float = Field(ge=0, description="Planned power-off window in minutes")
    disables_protection: bool = Field(
        default=False, description="True if any step disables protection"
    )


class VerificationResult(BaseModel):
    passed: bool
    feedback: str = ""


class VerifyAttempt(BaseModel):
    """One side of fail-to-pass: did the test pass, and what did it print."""

    passed: bool = False
    output: str = ""


class RunVerification(BaseModel):
    """Fail-on-original → pass-on-patch evidence for the run drawer (S1).

    Optional everywhere: older runs and runs without an original simply
    leave it unset, and readers must tolerate missing pieces.
    """

    target: str = Field(default="", description="Verified target, e.g. inventory")
    original_code: Optional[str] = Field(
        default=None, description="Buggy original the test had to fail on"
    )
    test_code: Optional[str] = Field(
        default=None, description="Final regression test from the passing attempt"
    )
    original: Optional[VerifyAttempt] = Field(
        default=None, description="Test run against the original (should fail)"
    )
    patched: Optional[VerifyAttempt] = Field(
        default=None, description="Test run against the patch (should pass)"
    )
    runner: Optional[str] = Field(
        default=None, description="Sandbox backend that ran pytest: modal|local"
    )


class ExecutionResult(BaseModel):
    status: str = Field(pattern="^(PASS|FAIL|NO_ACTION)$")
    stdout: str
    stderr: str
    attempts: int
    model_used: str
    pr_url: Optional[str] = Field(
        default=None, description="GitHub PR URL when a fix PR was opened"
    )
    run_id: str = Field(default="", description="Incident run identifier")
    patch_code: Optional[str] = Field(
        default=None, description="Verified fix module on PASS (Sim 5 deploy)"
    )
    verification: Optional[RunVerification] = Field(
        default=None, description="Fail-to-pass evidence for the drawer (S1)"
    )
    # Production repo runs (roadmap §3.4; James fills, John reads).
    repo: str = Field(default="", description="owner/name the fix PR targets")
    suite: Optional[SuiteSummary] = Field(
        default=None, description="Prove step: passed/failed/new_failures"
    )
    mitigation: Optional[MitigationSummary] = Field(
        default=None, description="J-R4 fills this on mitigation runs"
    )


class ApplianceAlert(BaseModel):
    alert_id: str
    channel: str = Field(description="Delivery channel; sms-stub until a provider lands")
    message: str
    work_order_id: str
    work_order: str


class ApplianceResult(BaseModel):
    status: str = Field(pattern="^(PASS|FAIL|NO_ACTION)$")
    runbook: Optional[Runbook] = Field(
        default=None, description="Validated runbook on PASS"
    )
    alert: Optional[ApplianceAlert] = Field(
        default=None, description="Owner alert + work order on PASS"
    )
    feedback: str = Field(default="", description="Safety violations on FAIL")
    attempts: int
    model_used: str
    run_id: str = Field(default="", description="Incident run identifier")


RunSource = Literal["manual", "upload", "watcher", "webhook", "gate"]


class RunRequest(BaseModel):
    log_text: str = Field(min_length=1, max_length=20000)
    original_code: Optional[str] = Field(
        default=None, description="Buggy original; enables fail-to-pass verification"
    )
    source: RunSource = Field(
        default="manual", description="How the incident reached the agent"
    )
    target: Optional[Literal["inventory"]] = Field(
        default=None,
        description="Known demo target; verifies against inventory.py (constant, not a path)",
    )
    target_path: Optional[str] = Field(
        default=None,
        max_length=200,
        description="Allowlisted demo-target file used as original_code",
    )
    reference: str = Field(
        default="",
        description="Profile reference data for the diagnosing model (P6)",
    )
    gate: Optional[dict] = Field(
        default=None,
        description="Gate decision payload that started the run (P6)",
    )


ApplianceFault = Literal[
    "none", "door_open", "condenser_fouling", "power_surge", "rapid_restart"
]


class ApplianceRunRequest(BaseModel):
    appliance_type: Literal["fridge", "freezer"] = "fridge"
    fault: ApplianceFault = "door_open"
    n_readings: int = Field(default=30, ge=5, le=120)
    source_id: str = Field(default="dashboard", min_length=1, max_length=100)
    source: RunSource = Field(
        default="manual", description="How the incident reached the agent"
    )
