"""Sensor watcher: propose candidates from raw readings (P5).

`SignalWatch` is the sensor-side mirror of the log watcher's classify()
window code: it tracks per-metric breach windows (first-breach time plus
the latest value of every metric seen) and proposes a `Candidate` while a
reading sits outside its band. The gate — not this module — decides
whether the breach is real. Durations accumulate only while breached and
reset the moment the signal returns to band, so short pulses (a 12 s
door-open) arrive at the gate with small durations and observe out.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from core.setup.gate import Candidate

DEFAULT_FRIDGE_BANDS = {
    "temp_c": (1.0, 6.0),
    "current_a": (0.0, 8.0),
    "vibration_g": (0.0, 0.5),
}


@dataclass
class BreachWindow:
    metric: str
    direction: str  # "high" | "low"
    first_breach: float
    count: int = 0


@dataclass
class SignalWatch:
    system_id: str
    bands: dict[str, tuple[float, float]] = field(default_factory=dict)
    windows: dict[str, BreachWindow] = field(default_factory=dict)
    latest: dict[str, float] = field(default_factory=dict)
    door_since: Optional[float] = None

    def __post_init__(self) -> None:
        if not self.bands:
            self.bands = dict(DEFAULT_FRIDGE_BANDS)

    def feed(
        self, metric: str, value: float, now: float
    ) -> Optional[Candidate]:
        """Record a reading; return a candidate while it breaches."""
        self.latest[metric] = value
        band = self.bands.get(metric)
        if band is None:
            return None
        low, high = band
        if low <= value <= high:
            self.windows.pop(metric, None)
            return None
        direction = "high" if value > high else "low"
        window = self.windows.get(metric)
        if window is None or window.direction != direction:
            window = BreachWindow(
                metric=metric, direction=direction, first_breach=now
            )
            self.windows[metric] = window
        window.count += 1
        durations = {
            name: max(0.0, now - item.first_breach)
            for name, item in self.windows.items()
        }
        return Candidate(
            system_id=self.system_id,
            source="sensor",
            rule=f"{metric}_{direction}",
            fingerprint=f"{self.system_id}:{metric}:{direction}",
            signature=f"{metric} {value:g} outside {low:g}..{high:g}",
            metrics=dict(self.latest),
            durations=durations,
        )

    def feed_door(self, is_open: bool, now: float) -> float:
        """Track a door-open stretch; return its length in seconds."""
        if not is_open:
            self.door_since = None
            return 0.0
        if self.door_since is None:
            self.door_since = now
            return 0.0
        return max(0.0, now - self.door_since)

    def reset(self, metric: Optional[str] = None) -> None:
        if metric is None:
            self.windows.clear()
            self.door_since = None
        else:
            self.windows.pop(metric, None)
