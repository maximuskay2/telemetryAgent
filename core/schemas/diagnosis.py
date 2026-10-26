from pydantic import BaseModel, Field


class Diagnosis(BaseModel):
    summary: str = Field(min_length=1)
    likely_cause: str = Field(min_length=1)
    suggested_actions: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


class DiagnosisRequest(BaseModel):
    log_text: str = Field(min_length=1, max_length=20000)
