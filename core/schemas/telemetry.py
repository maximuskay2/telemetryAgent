from typing import List, Literal, Union

from pydantic import BaseModel, Field
from typing_extensions import Annotated


class SoftwareTelemetry(BaseModel):
    domain: Literal["software"] = "software"
    source_id: str
    raw_log: str = Field(min_length=1, max_length=20000)


class SensorReading(BaseModel):
    ts: float
    temperature_c: float
    current_a: float = Field(ge=0)
    vibration_g: float = Field(ge=0)
    door_open: bool = False


class ApplianceTelemetry(BaseModel):
    domain: Literal["appliance"] = "appliance"
    source_id: str
    appliance_type: Literal["fridge", "freezer"]
    readings: List[SensorReading] = Field(min_length=1)


Telemetry = Annotated[Union[SoftwareTelemetry, ApplianceTelemetry], Field(discriminator="domain")]
