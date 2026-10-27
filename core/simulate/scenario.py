"""Scripted demo timeline player (Sim 6).

`demo/timeline.yaml` lists steps as `{at, action, ...params}` with `at` in
seconds from Play. The player sleeps between steps and executes each through
callables, so tests drive it with fakes and the API wires the real world.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

import yaml

TIMELINE_PATH = (
    Path(__file__).resolve().parent.parent.parent / "demo" / "timeline.yaml"
)

STEP_ACTIONS = ("shop_load", "fridge_fault", "fridge_action")
FRIDGE_FAULTS = ("door_open", "condenser_fouling", "power_surge", "rapid_restart")
FRIDGE_ACTIONS = ("close_door", "clean_condenser", "reset")


def load_timeline(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Parse + validate the timeline; steps come back sorted by `at`."""
    raw = yaml.safe_load((path or TIMELINE_PATH).read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw:
        raise ValueError("timeline must be a non-empty list of steps")
    steps: List[Dict[str, Any]] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError(f"step {index} must be a mapping")
        at = entry.get("at")
        action = entry.get("action")
        if not isinstance(at, (int, float)) or at < 0:
            raise ValueError(f"step {index} needs `at` >= 0 seconds")
        if action not in STEP_ACTIONS:
            raise ValueError(f"step {index} has unknown action {action!r}")
        step = dict(entry)
        step["at"] = float(at)
        if action == "shop_load":
            for key in ("shoppers", "rate", "duration"):
                if key not in step:
                    raise ValueError(f"step {index} shop_load needs `{key}`")
        elif action == "fridge_fault":
            if step.get("fault") not in FRIDGE_FAULTS:
                raise ValueError(f"step {index} has unknown fault")
        elif action == "fridge_action":
            if step.get("name") not in FRIDGE_ACTIONS:
                raise ValueError(f"step {index} has unknown action name")
        steps.append(step)
    steps.sort(key=lambda s: s["at"])
    return steps


async def play_timeline(
    steps: List[Dict[str, Any]],
    spawn_load: Callable[..., None],
    apply_fault: Callable[[str], None],
    apply_action: Callable[[str], None],
    on_step: Optional[Callable[[int, int, Dict[str, Any]], Awaitable[None]]] = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    """Run steps on schedule; `sleep`/`clock` are injectable for tests."""
    started = clock()
    total = len(steps)
    for index, step in enumerate(steps):
        delay = step["at"] - (clock() - started)
        if delay > 0:
            await sleep(delay)
        action = step["action"]
        if action == "shop_load":
            spawn_load(
                shoppers=int(step["shoppers"]),
                rate=float(step["rate"]),
                duration=int(step["duration"]),
            )
        elif action == "fridge_fault":
            apply_fault(str(step["fault"]))
        elif action == "fridge_action":
            apply_action(str(step["name"]))
        if on_step is not None:
            await on_step(index + 1, total, step)
