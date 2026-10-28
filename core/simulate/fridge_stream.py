"""Virtual fridge stream (Sim 4): a live world, not a physics simulator.

`VirtualFridge` steps every tick (1 s real = 1 simulated minute), reusing the
baselines and fault names from `core.simulate.appliance` so the streamed
readings stay consistent with the generated windows the agent trains on.
Faults mutate state; repairs clear it; readings follow. Stdlib only.
"""

from __future__ import annotations

import random
import time

from core.schemas.telemetry import ApplianceTelemetry, SensorReading
from core.simulate.appliance import (
    BASE_CURRENT_A,
    BASE_TEMP_C,
    BASE_VIBRATION_G,
    ApplianceType,
)

SIM_STEP_S = 60.0  # one tick simulates one minute

# Warm-air ingress per tick while the door stands open, tuned so a stuck door
# settles inside the sensor watcher's warning band for both unit types.
DOOR_INGRESS_C = {"fridge": 0.35, "freezer": 0.8}
DRIFT = 0.15  # pull toward baseline per tick when the loop is healthy
COMPRESSOR_BAND_C = 0.5  # hysteresis around baseline

FAULTS = (
    "door_open",
    "condenser_fouling",
    "power_surge",
    "rapid_restart",
    "defrost_stuck",
)
ACTIONS = ("close_door", "clean_condenser", "reset", "end_defrost")
SURGE_TICKS = 3

# Normal-but-scary behaviours (P3): defrost every 6 sim-hours, 20 sim-minutes
# each (at 1 tick/s real time the demo cycle is ~20 s).
DEFROST_PERIOD_TICKS = 360
DEFROST_DURATION_TICKS = 20
DEFROST_TARGET_C = 7.0
IN_RUSH_TICKS = 3
IN_RUSH_RATIO = 3.5  # total current multiple; trips the raw 3.0 watcher ratio
AMBIENT_HOT_RATIO = 1.15  # class-T steady load uplift on hot afternoons


class VirtualFridge:
    """Stateful fridge/freezer whose sensor readings follow faults + repairs."""

    def __init__(
        self,
        appliance_type: ApplianceType = "fridge",
        source_id: str = "sim-fridge-01",
        seed: int | None = None,
    ) -> None:
        if appliance_type not in BASE_TEMP_C:
            raise ValueError(f"unknown appliance_type: {appliance_type}")
        self.appliance_type = appliance_type
        self.source_id = source_id
        self.rng = random.Random(seed)
        self.sim_ts = time.time()
        self.tick_count = 0
        self.temp_c = BASE_TEMP_C[appliance_type]
        self.compressor_on = True
        self.door_open = False
        self.condenser_dirty = False
        self.condenser_heat = 0.0  # 0 clean .. 1 fully fouled
        self.surge_ticks = 0
        self.short_cycling = False
        # P3 normal-but-scary state.
        self.defrost_ticks_left = 0
        self.defrost_stuck = False
        self.last_defrost_tick = 0
        self.defrost_schedule = True
        self.door_ticks_left: int | None = None  # None = held open
        self.ambient_hot = False
        self.inrush_ticks = 0

    # -- controls ---------------------------------------------------------
    def apply_fault(self, fault: str) -> None:
        """Mutate state; unknown names raise ValueError (422 at the API)."""
        if fault == "door_open":
            self.open_door(None)
        elif fault == "condenser_fouling":
            self.condenser_dirty = True
        elif fault == "power_surge":
            self.surge_ticks = SURGE_TICKS
        elif fault == "rapid_restart":
            self.short_cycling = True
        elif fault == "defrost_stuck":
            self.defrost_stuck = True
            self.defrost_ticks_left = DEFROST_DURATION_TICKS
        else:
            raise ValueError(f"unknown fault: {fault}")

    def start_defrost(self, duration_ticks: int = DEFROST_DURATION_TICKS) -> None:
        """Begin a defrost cycle (schedule, button, or API)."""
        if duration_ticks < 1:
            raise ValueError("duration_ticks must be >= 1")
        self.defrost_ticks_left = duration_ticks

    def open_door(self, ticks: int | None) -> None:
        """Open the door; `ticks` auto-closes (restock), None holds it open."""
        if ticks is not None and ticks < 1:
            raise ValueError("ticks must be >= 1")
        self.door_open = True
        self.door_ticks_left = ticks

    def set_ambient_hot(self, hot: bool) -> None:
        """Lagos afternoon: class-T steady load runs ~15% higher."""
        self.ambient_hot = hot

    def restart(self) -> None:
        """Compressor restart: 2-3 ticks of ~3.5x inrush current."""
        self.inrush_ticks = IN_RUSH_TICKS
        self.compressor_on = True

    def apply_action(self, action: str) -> None:
        """Repairs clear state; unknown names raise ValueError (422 at the API)."""
        if action == "close_door":
            self.door_open = False
            self.door_ticks_left = None
        elif action == "clean_condenser":
            self.condenser_dirty = False
        elif action == "end_defrost":
            self.defrost_ticks_left = 0
            self.defrost_stuck = False
            self.last_defrost_tick = self.tick_count
        elif action == "reset":
            self.door_open = False
            self.condenser_dirty = False
            self.condenser_heat = 0.0
            self.surge_ticks = 0
            self.short_cycling = False
            self.defrost_ticks_left = 0
            self.defrost_stuck = False
            self.door_ticks_left = None
            self.temp_c = BASE_TEMP_C[self.appliance_type]
            self.compressor_on = True
            self.restart()  # any restart draws inrush
        else:
            raise ValueError(f"unknown action: {action}")

    # -- simulation -------------------------------------------------------
    def tick(self) -> SensorReading:
        """Advance one simulated minute; return the new sensor reading."""
        base_t = BASE_TEMP_C[self.appliance_type]
        base_a = BASE_CURRENT_A[self.appliance_type]
        self.tick_count += 1
        self.sim_ts += SIM_STEP_S

        current = base_a + self.rng.uniform(-0.08, 0.08)
        vibration = max(0.0, BASE_VIBRATION_G + self.rng.uniform(-0.008, 0.008))

        if self.ambient_hot:
            current *= AMBIENT_HOT_RATIO
            self.temp_c += 0.02
        if self.inrush_ticks > 0:
            current += base_a * (IN_RUSH_RATIO - 1.0)
            vibration += 0.05
            self.inrush_ticks -= 1
        if (
            self.defrost_schedule
            and self.defrost_ticks_left <= 0
            and not self.defrost_stuck
            and self.tick_count - self.last_defrost_tick >= DEFROST_PERIOD_TICKS
        ):
            self.start_defrost()
        defrosting = self.defrost_ticks_left > 0 or self.defrost_stuck
        if self.door_ticks_left is not None:
            self.door_ticks_left -= 1
            if self.door_ticks_left <= 0:
                self.door_open = False  # restock closes itself
                self.door_ticks_left = None

        if defrosting:
            self.compressor_on = False  # heater on, cooling off
            if self.defrost_stuck:
                self.temp_c += 0.15  # heater never stops: blows past 7 °C
            else:
                self.temp_c += (DEFROST_TARGET_C - self.temp_c) * 0.12
                self.defrost_ticks_left -= 1
                if self.defrost_ticks_left <= 0:
                    self.last_defrost_tick = self.tick_count
        else:
            if self.temp_c > base_t + COMPRESSOR_BAND_C:
                self.compressor_on = True
            elif self.temp_c < base_t - COMPRESSOR_BAND_C:
                self.compressor_on = False
            self.temp_c += (base_t - self.temp_c) * DRIFT
        self.temp_c += self.rng.uniform(-0.1, 0.1)

        if self.door_open:
            self.temp_c += DOOR_INGRESS_C[self.appliance_type]
            current += 0.15  # compressor fights the warm air (below warn band)
            self.compressor_on = True
        if self.condenser_dirty:
            self.condenser_heat = min(1.0, self.condenser_heat + 0.05)
            current += 0.9 * self.condenser_heat  # longer runs, higher current
            self.temp_c += 0.06
        else:
            self.condenser_heat = max(0.0, self.condenser_heat - 0.1)
        if self.surge_ticks > 0:
            current += 4.5
            vibration += 0.15
            self.surge_ticks -= 1
        if self.short_cycling and self.tick_count % 4 == 0:
            current += 3.0  # compressor short-cycling
            vibration += 0.08
        if self.compressor_on:
            vibration += 0.01

        defrosting = self.defrost_ticks_left > 0 or self.defrost_stuck
        return SensorReading(
            ts=self.sim_ts,
            temperature_c=round(self.temp_c, 2),
            current_a=round(max(0.0, current), 3),
            vibration_g=round(vibration, 4),
            door_open=self.door_open,
            mode="defrost" if defrosting else "",
        )

    # -- views ------------------------------------------------------------
    def snapshot(self) -> dict:
        """World state for the dashboard (display only, never model input)."""
        return {
            "appliance_type": self.appliance_type,
            "source_id": self.source_id,
            "tick": self.tick_count,
            "temp_c": round(self.temp_c, 2),
            "door_open": self.door_open,
            "compressor_on": self.compressor_on,
            "condenser_dirty": self.condenser_dirty,
            "surge_active": self.surge_ticks > 0,
            "short_cycling": self.short_cycling,
            "defrost_active": self.defrost_ticks_left > 0 or self.defrost_stuck,
            "defrost_stuck": self.defrost_stuck,
            "ambient_hot": self.ambient_hot,
            "inrush_active": self.inrush_ticks > 0,
        }

    def window(self, readings: list[SensorReading]) -> ApplianceTelemetry:
        """Wrap readings as model input; carries no fault label by construction."""
        return ApplianceTelemetry(
            source_id=self.source_id,
            appliance_type=self.appliance_type,
            readings=list(readings),
        )


def map_step_to_action(step: str) -> str | None:
    """Map a runbook step to a fridge action; None when not safely mappable.

    Only steps that name a known repair map; anything else is skipped by the
    caller, never force-executed.
    """
    text = step.lower()
    if "defrost" in text and any(
        word in text for word in ("end", "stop", "off", "finish", "cancel")
    ):
        return "end_defrost"
    if "door" in text and any(word in text for word in ("close", "shut", "seal")):
        return "close_door"
    if "condens" in text and any(
        word in text for word in ("clean", "wipe", "clear", "dust", "wash", "brush")
    ):
        return "clean_condenser"
    if any(
        word in text for word in ("power cycle", "power-cycle", "reboot", "reset")
    ) and any(
        word in text
        for word in ("unit", "fridge", "freezer", "system", "controller")
    ):
        return "reset"
    return None
