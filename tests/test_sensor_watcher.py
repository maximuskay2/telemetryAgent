"""Sensor watcher tests (Sim 4): thresholds, debounce, labelless payload."""

import unittest

from core.simulate.appliance import BASE_CURRENT_A
from core.simulate.fridge_stream import VirtualFridge
from core.watch.sensor_watcher import SensorWatcher


def reading(temp_c, current_a, ts=1.0):
    return {
        "ts": ts,
        "temperature_c": temp_c,
        "current_a": current_a,
        "vibration_g": 0.02,
    }


class SensorWatcherTest(unittest.TestCase):
    def test_healthy_readings_never_fire(self) -> None:
        watcher = SensorWatcher()
        for i in range(10):
            hit = watcher.observe(reading(3.5, BASE_CURRENT_A["fridge"], ts=i))
            self.assertIsNone(hit)

    def test_temp_warning_needs_three_hot_readings(self) -> None:
        watcher = SensorWatcher()
        self.assertIsNone(watcher.observe(reading(5.5, 1.1, ts=1)))
        self.assertIsNone(watcher.observe(reading(5.6, 1.1, ts=2)))
        hit = watcher.observe(reading(5.7, 1.1, ts=3))
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit.rule, "temp-warning")
        self.assertEqual(hit.level, "warning")

    def test_freezer_uses_freezer_thresholds(self) -> None:
        watcher = SensorWatcher(appliance_type="freezer")
        self.assertIsNone(watcher.observe(reading(-14.0, 1.6, ts=1)))
        self.assertIsNone(watcher.observe(reading(-14.0, 1.6, ts=2)))
        hit = watcher.observe(reading(-14.0, 1.6, ts=3))
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit.rule, "temp-warning")

    def test_temp_critical_fires_immediately(self) -> None:
        watcher = SensorWatcher()
        hit = watcher.observe(reading(8.5, 1.1))
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual((hit.rule, hit.level), ("temp-critical", "error"))

    def test_current_warning_and_spike(self) -> None:
        base = BASE_CURRENT_A["fridge"]
        watcher = SensorWatcher()
        hit = watcher.observe(reading(3.5, 1.5 * base))
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit.rule, "current-warning")
        spike = SensorWatcher()
        hit = spike.observe(reading(3.5, 3.5 * base))
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual((hit.rule, hit.level), ("current-spike", "error"))

    def test_fires_once_per_fault(self) -> None:
        watcher = SensorWatcher()
        hits = [
            watcher.observe(reading(6.0, 1.1, ts=i)) for i in range(6)
        ]
        self.assertEqual(sum(1 for h in hits if h is not None), 1)

    def test_distinct_rules_fire_distinct_hits(self) -> None:
        base = BASE_CURRENT_A["fridge"]
        watcher = SensorWatcher()
        watcher.observe(reading(6.0, 1.1, ts=1))
        watcher.observe(reading(6.0, 1.1, ts=2))
        first = watcher.observe(reading(6.0, 1.1, ts=3))
        second = watcher.observe(reading(6.0, 3.5 * base, ts=4))
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        assert first is not None and second is not None
        self.assertNotEqual(first.rule, second.rule)

    def test_reset_allows_refire(self) -> None:
        watcher = SensorWatcher()
        for i in range(3):
            watcher.observe(reading(6.0, 1.1, ts=i))
        watcher.reset()
        self.assertEqual(watcher.buffered, 0)
        self.assertIsNone(watcher.observe(reading(6.0, 1.1, ts=10)))
        self.assertIsNone(watcher.observe(reading(6.0, 1.1, ts=11)))
        self.assertIsNotNone(watcher.observe(reading(6.0, 1.1, ts=12)))

    def test_telemetry_window_has_no_fault_label(self) -> None:
        watcher = SensorWatcher()
        for i in range(35):
            watcher.observe(reading(6.0, 1.1, ts=i))
        telemetry = watcher.telemetry()
        self.assertEqual(len(telemetry.readings), 30)
        self.assertEqual(telemetry.source_id, "sim-fridge-01")
        self.assertNotIn("fault", telemetry.model_dump_json())

    def test_telemetry_empty_raises(self) -> None:
        with self.assertRaises(ValueError):
            SensorWatcher().telemetry()

    def test_door_fault_triggers_watcher_end_to_end(self) -> None:
        for appliance_type in ("fridge", "freezer"):
            fridge = VirtualFridge(appliance_type=appliance_type, seed=11)
            watcher = SensorWatcher(appliance_type=appliance_type)
            fridge.apply_fault("door_open")
            hits = [watcher.observe(fridge.tick()) for _ in range(30)]
            fired = [h for h in hits if h is not None]
            self.assertGreaterEqual(len(fired), 1, appliance_type)
            # Each rule fires once; the first hit is the temperature warning.
            self.assertEqual(fired[0].rule, "temp-warning", appliance_type)
            self.assertEqual(fired[0].level, "warning", appliance_type)
            self.assertEqual(len({h.rule for h in fired}), len(fired))

    def test_surge_triggers_error_end_to_end(self) -> None:
        fridge = VirtualFridge(seed=9)
        watcher = SensorWatcher()
        for _ in range(5):
            watcher.observe(fridge.tick())
        fridge.apply_fault("power_surge")
        hit = watcher.observe(fridge.tick())
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit.level, "error")


if __name__ == "__main__":
    unittest.main()
