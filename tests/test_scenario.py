"""Scenario player tests (Sim 6): timeline parsing + scheduled play."""

import asyncio
import tempfile
import unittest
from pathlib import Path

from core.simulate.scenario import load_timeline, play_timeline


class FakeClock:
    def __init__(self) -> None:
        self.t = 100.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.t

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += seconds


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class LoadTimelineTest(unittest.TestCase):
    def test_repo_timeline_parses_and_sorts(self) -> None:
        steps = load_timeline()
        self.assertGreaterEqual(len(steps), 2)
        self.assertEqual([s["at"] for s in steps], sorted(s["at"] for s in steps))
        kinds = {s["action"] for s in steps}
        self.assertIn("shop_load", kinds)
        self.assertIn("fridge_fault", kinds)

    def _write(self, text):
        tmp = tempfile.NamedTemporaryFile(
            "w", suffix=".yaml", delete=False, encoding="utf-8"
        )
        tmp.write(text)
        tmp.close()
        self.addCleanup(Path(tmp.name).unlink)
        return Path(tmp.name)

    def test_rejects_unknown_action(self) -> None:
        path = self._write("- at: 1\n  action: explode\n")
        with self.assertRaises(ValueError):
            load_timeline(path)

    def test_rejects_negative_at(self) -> None:
        path = self._write("- at: -1\n  action: fridge_action\n  name: reset\n")
        with self.assertRaises(ValueError):
            load_timeline(path)

    def test_rejects_empty_timeline(self) -> None:
        path = self._write("[]\n")
        with self.assertRaises(ValueError):
            load_timeline(path)

    def test_rejects_shop_load_missing_params(self) -> None:
        path = self._write("- at: 1\n  action: shop_load\n  shoppers: 2\n")
        with self.assertRaises(ValueError):
            load_timeline(path)

    def test_rejects_unknown_fault_name(self) -> None:
        path = self._write("- at: 1\n  action: fridge_fault\n  fault: aliens\n")
        with self.assertRaises(ValueError):
            load_timeline(path)


class PlayTimelineTest(unittest.TestCase):
    def test_steps_run_in_order_on_schedule(self) -> None:
        clock = FakeClock()
        calls: list = []
        progress: list = []

        async def on_step(done, total, step):
            progress.append((done, total, step["action"]))

        steps = [
            {"at": 0, "action": "fridge_fault", "fault": "door_open"},
            {"at": 5, "action": "shop_load", "shoppers": 2, "rate": 5,
             "duration": 10},
            {"at": 5, "action": "fridge_action", "name": "reset"},
        ]
        run(play_timeline(
            steps,
            spawn_load=lambda **kw: calls.append(("load", kw)),
            apply_fault=lambda name: calls.append(("fault", name)),
            apply_action=lambda name: calls.append(("action", name)),
            on_step=on_step,
            sleep=clock.sleep,
            clock=clock,
        ))
        self.assertEqual(
            [c[0] for c in calls], ["fault", "load", "action"]
        )
        self.assertEqual(calls[1][1]["shoppers"], 2)
        self.assertEqual(clock.sleeps, [5.0])
        self.assertEqual(
            progress,
            [(1, 3, "fridge_fault"), (2, 3, "shop_load"), (3, 3, "fridge_action")],
        )


if __name__ == "__main__":
    unittest.main()
