"""Sensor watcher (Sim 4): evaluate every fridge reading, grab incidents.

Threshold rules on temperature/current, debounced by fingerprint so one fault
fires one run. The model payload is the raw reading window only: the fault
name is never sent. Stdlib only; the API wires triggers to the appliance loop.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, Mapping, Optional, Union

from core.schemas.telemetry import ApplianceTelemetry, SensorReading
from core.simulate.appliance import BASE_CURRENT_A
from core.watch.rules import fingerprint_for
from core.watch.watcher import should_send

WARN_TEMP_C = {"fridge": 5.0, "freezer": -15.0}
ERR_TEMP_C = {"fridge": 8.0, "freezer": -12.0}
WARN_CURRENT_RATIO = 1.3
ERR_CURRENT_RATIO = 3.0
WARN_STREAK = 3  # consecutive hot readings before a warning fires

ReadingLike = Union[SensorReading, Mapping[str, float]]


@dataclass
class SensorHit:
    rule: str
    level: str  # warning | error
    resource: str
    detail: str


class SensorWatcher:
    """Threshold + debounce evaluator over a live reading stream."""

    def __init__(
        self,
        appliance_type: str = "fridge",
        source_id: str = "sim-fridge-01",
        window: int = 30,
        debounce_s: float = 600.0,
    ) -> None:
        if appliance_type not in WARN_TEMP_C:
            raise ValueError(f"unknown appliance_type: {appliance_type}")
        self.appliance_type = appliance_type
        self.source_id = source_id
        self.window = max(1, window)
        self.debounce_s = debounce_s
        self._readings: Deque[SensorReading] = deque(maxlen=self.window)
        self._last_sent: Dict[str, float] = {}

    def reset(self) -> None:
        """Clear buffer + debounce so a new scenario can fire fresh."""
        self._readings.clear()
        self._last_sent.clear()

    @property
    def buffered(self) -> int:
        return len(self._readings)

    def observe(self, reading: ReadingLike) -> Optional[SensorHit]:
        """Evaluate one reading; return a hit when a rule fires (debounced)."""
        if isinstance(reading, Mapping):
            sensor = SensorReading(
                ts=float(reading.get("ts", time.time())),
                temperature_c=float(reading["temperature_c"]),
                current_a=float(reading["current_a"]),
                vibration_g=float(reading.get("vibration_g", 0.0)),
                door_open=bool(reading.get("door_open", False)),
            )
        else:
            sensor = reading
        self._readings.append(sensor)

        temp = sensor.temperature_c
        amps = sensor.current_a
        base_a = BASE_CURRENT_A[self.appliance_type]  # type: ignore[arg-type]

        rule: Optional[str] = None
        level = "warning"
        if temp > ERR_TEMP_C[self.appliance_type]:
            rule, level = "temp-critical", "error"
            detail = f"temp {temp:.1f}C above {ERR_TEMP_C[self.appliance_type]}C"
        elif amps > ERR_CURRENT_RATIO * base_a:
            rule, level = "current-spike", "error"
            detail = f"current {amps:.2f}A above {ERR_CURRENT_RATIO}x baseline"
        elif self._hot_streak():
            rule, level = "temp-warning", "warning"
            detail = f"temp above {WARN_TEMP_C[self.appliance_type]}C for {WARN_STREAK}"
        elif amps > WARN_CURRENT_RATIO * base_a:
            rule, level = "current-warning", "warning"
            detail = f"current {amps:.2f}A above {WARN_CURRENT_RATIO}x baseline"
        if rule is None:
            return None
        fp = fingerprint_for(rule, self.source_id, detail)
        if not should_send(fp, time.time(), self._last_sent, self.debounce_s):
            return None
        return SensorHit(rule=rule, level=level, resource=self.source_id, detail=detail)

    def telemetry(self) -> ApplianceTelemetry:
        """Last readings as model input; contains no fault label."""
        if not self._readings:
            raise ValueError("no readings buffered")
        return ApplianceTelemetry(
            source_id=self.source_id,
            appliance_type=self.appliance_type,  # type: ignore[arg-type]
            readings=list(self._readings),
        )

    def _hot_streak(self) -> bool:
        if len(self._readings) < WARN_STREAK:
            return False
        cutoff = WARN_TEMP_C[self.appliance_type]
        tail = list(self._readings)[-WARN_STREAK:]
        return all(r.temperature_c > cutoff for r in tail)
