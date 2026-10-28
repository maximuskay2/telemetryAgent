"""System Profile schema: what "normal" looks like, with provenance.

Before TelemetryAgent watches a system, the owner teaches it normal: docs go
in, a profile comes out, a human confirms it, and only then does the system
arm. Every value carries where it came from so the UI can cite it and the
gate can explain itself ("Expected: defrost (spec sheet p.2)").

Policy and hard limits are human-only: extraction (P1) never writes them.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

#: Provenance sources that need no document quote (human-typed or learned).
QUOTELESS_SOURCES = ("manual", "learned", "feedback")


class Provenance(BaseModel):
    """Where one value came from. Doc-sourced values must quote exactly."""

    source_doc: str = Field(min_length=1, description="Filename or 'manual'")
    page_or_region: str = Field(
        default="", description="'p.2' or 'rating plate, lower right'"
    )
    quote: str = Field(default="", description="Exact source text")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    confirmed_by: str = Field(default="", description="Human confirmer")
    confirmed_at: str = Field(default="", description="ISO timestamp")

    @model_validator(mode="after")
    def _quote_required_for_docs(self) -> "Provenance":
        if (
            self.source_doc not in QUOTELESS_SOURCES
            and not self.quote.strip()
        ):
            raise ValueError(
                f"value from '{self.source_doc}' needs an exact source quote"
            )
        return self


class NormalRange(BaseModel):
    metric: str = Field(min_length=1)
    min: float
    max: float
    unit: str = ""
    provenance: Provenance


class ExpectedBehaviour(BaseModel):
    name: str = Field(min_length=1)
    signature: str = Field(
        default="", description="Log template or signal pattern"
    )
    schedule: str = Field(default="", description="'every 6h', 'at startup'")
    max_duration_s: float = Field(default=0, ge=0)
    allowed_effect: str = Field(
        default="", description="'temp may rise to ≤ 7 °C'"
    )
    provenance: Provenance


class ModeRelaxation(BaseModel):
    mode: str = Field(min_length=1)
    relaxes: list[str] = Field(
        default_factory=list, description="Signals excused in this mode"
    )
    max_duration_s: float = Field(default=0, ge=0)
    provenance: Provenance


class FailureDefinition(BaseModel):
    """What really counts as broken (the gate checks these for impact)."""

    name: str = Field(min_length=1)
    metric: str = Field(min_length=1)
    op: Literal[">", "<"] = ">"
    threshold: float
    duration_s: float = Field(default=0, ge=0)
    except_modes: list[str] = Field(default_factory=list)
    provenance: Provenance


class HardLimit(BaseModel):
    """Safety floor: the gate can never call these normal."""

    metric: str = Field(min_length=1)
    op: Literal[">", "<"] = ">"
    threshold: float
    provenance: Provenance


class Policy(BaseModel):
    allowed_actions: list[str] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(default_factory=list)
    auto_fix_allowed: bool = False
    countdown_s: int = Field(default=20, ge=5, le=300)
    alert_contacts: list[str] = Field(default_factory=list)


class Baseline(BaseModel):
    """Filled by P7 learning; loose shapes until then."""

    status: Literal["none", "learning", "ready"] = "none"
    duration_s: float = 0
    learned_at: str = ""
    log_templates: list[dict] = Field(default_factory=list)
    sensor_bands: dict = Field(default_factory=dict)
    metric_bands: dict = Field(default_factory=dict)


class SystemProfile(BaseModel):
    system_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str = Field(min_length=1)
    kind: Literal["software", "appliance"]
    appliance_type: Optional[Literal["fridge", "freezer"]] = None
    owner_contact: str = ""
    environment: dict[str, str] = Field(default_factory=dict)
    normal_ranges: list[NormalRange] = Field(default_factory=list)
    expected_behaviours: list[ExpectedBehaviour] = Field(default_factory=list)
    modes: list[ModeRelaxation] = Field(default_factory=list)
    failure_definitions: list[FailureDefinition] = Field(default_factory=list)
    hard_limits: list[HardLimit] = Field(default_factory=list)
    policy: Policy = Field(default_factory=Policy)
    baseline: Baseline = Field(default_factory=Baseline)
    status: Literal["draft", "confirmed", "learning", "armed"] = "draft"
    version: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def _cross_field_rules(self) -> "SystemProfile":
        # Hard limits are optional (but recommended as the safety floor):
        # any status validates with or without them.
        if self.kind == "appliance" and self.appliance_type is None:
            raise ValueError("appliance systems need an appliance_type")
        if self.kind == "software" and self.appliance_type is not None:
            raise ValueError("software systems must not set appliance_type")
        return self
