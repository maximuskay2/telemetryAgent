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
