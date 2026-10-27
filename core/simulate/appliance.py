"""Synthetic fridge/freezer telemetry with injectable faults (Day 6).

No hardware and no physics simulator: deterministic random-walk readings with
per-fault signatures the agent must classify. `seed` makes windows
reproducible for tests and the demo.
"""

from __future__ import annotations

import random
import time
from typing import Literal

from core.schemas.telemetry import ApplianceTelemetry, SensorReading

ApplianceType = Literal["fridge", "freezer"]

BASE_TEMP_C = {"fridge": 3.5, "freezer": -19.0}
BASE_CURRENT_A = {"fridge": 1.1, "freezer": 1.6}
BASE_VIBRATION_G = 0.02
STEP_S = 60.0


def generate_window(
    appliance_type: ApplianceType = "fridge",
    fault: str = "door_open",
    n_readings: int = 30,
    source_id: str = "sim-fridge-01",
    seed: int | None = None,
    start_ts: float | None = None,
) -> ApplianceTelemetry:
    """Build a sensor window; `fault` selects the injected abnormal behavior."""
    if n_readings < 1:
        raise ValueError("n_readings must be at least 1")
    rng = random.Random(seed)
    base = start_ts if start_ts is not None else time.time() - n_readings * STEP_S
    temp = BASE_TEMP_C[appliance_type]
    readings: list[SensorReading] = []
    for i in range(n_readings):
        temp += rng.uniform(-0.15, 0.15)
        current = BASE_CURRENT_A[appliance_type] + rng.uniform(-0.08, 0.08)
        vibration = max(0.0, BASE_VIBRATION_G + rng.uniform(-0.008, 0.008))
        door_open = False
        progress = i / max(1, n_readings - 1)

        if fault == "door_open" and i >= n_readings // 3:
            door_open = rng.random() < 0.8
            temp += 0.25  # warm air ingress while the door stands open
        elif fault == "condenser_fouling":
            current += 0.9 * progress  # longer runs, higher current
            temp += 0.06
        elif fault == "power_surge" and n_readings // 2 - 1 <= i <= n_readings // 2 + 1:
            current += 4.5
            vibration += 0.15
        elif fault == "rapid_restart" and i % 4 == 0 and i > 0:
            current += 3.0  # compressor short-cycling
            vibration += 0.08

        readings.append(
            SensorReading(
                ts=base + i * STEP_S,
                temperature_c=round(temp, 2),
                current_a=round(max(0.0, current), 3),
                vibration_g=round(vibration, 4),
                door_open=door_open,
            )
        )
    return ApplianceTelemetry(
        source_id=source_id,
        appliance_type=appliance_type,
        readings=readings,
    )
