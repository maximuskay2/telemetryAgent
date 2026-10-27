from typing import Literal, Optional

from pydantic import BaseModel, Field


class GeneratedPatch(BaseModel):
    patch_code: str = Field(min_length=1, description="Python module implementing the fix")
    test_code: str = Field(min_length=1, description="Pytest suite asserting the fix")


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


class ExecutionResult(BaseModel):
    status: str = Field(pattern="^(PASS|FAIL)$")
    stdout: str
    stderr: str
    attempts: int
    model_used: str
    pr_url: Optional[str] = Field(
        default=None, description="GitHub PR URL when a fix PR was opened"
    )
    run_id: str = Field(default="", description="Incident run identifier")


class ApplianceAlert(BaseModel):
    alert_id: str
    channel: str = Field(description="Delivery channel; sms-stub until a provider lands")
    message: str
    work_order_id: str
    work_order: str


class ApplianceResult(BaseModel):
    status: str = Field(pattern="^(PASS|FAIL)$")
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


RunSource = Literal["manual", "upload", "watcher", "webhook"]


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
