from pydantic import BaseModel, Field


class Diagnosis(BaseModel):
    summary: str = Field(min_length=1)
    likely_cause: str = Field(min_length=1)
    suggested_actions: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    is_expected: bool = Field(
        default=False,
        description="Model verdict: this telemetry is normal behaviour",
    )
    expected_reason: str = Field(
        default="",
        description="Why it is normal, citing the reference data",
    )


class DiagnosisRequest(BaseModel):
    log_text: str = Field(min_length=1, max_length=20000)
