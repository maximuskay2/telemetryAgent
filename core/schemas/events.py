from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class LogInput(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    source: str = Field(default="unknown", min_length=1, max_length=100)
    level: Optional[LogLevel] = None


class LogEvent(BaseModel):
    id: str
    timestamp: datetime
    source: str
    message: str
    level: LogLevel


class AgentStep(BaseModel):
    step: str = Field(description="diagnose, generate, verify, or done")
    attempt: int = 0
    model: str = ""
    status: str = ""
    message: str = ""
    duration_ms: float = Field(default=0.0, description="Stage wall time in ms")
    run_id: str = Field(default="", description="Incident run this step belongs to")
    domain: str = Field(default="", description="Telemetry domain: software or appliance")
    detail: str = Field(default="", description="Truncated stage payload summary")
    source: str = Field(default="", description="How the incident arrived: upload, watcher, webhook")
    suggestions: list[str] = Field(default_factory=list, description="Suggested next actions from diagnosis")
