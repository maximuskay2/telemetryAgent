"""VirtualFridge stream tests (Sim 4): faults move readings, repairs recover."""

import unittest

from core.simulate.appliance import BASE_CURRENT_A, BASE_TEMP_C
from core.simulate.fridge_stream import VirtualFridge


def run(fridge, n):
    readings = [fridge.tick() for _ in range(n)]
    return readings


class FridgeStreamTest(unittest.TestCase):
    def test_baseline_stays_near_base(self) -> None:
        fridge = VirtualFridge(seed=7)
        readings = run(fridge, 10)
        for reading in readings:
            self.assertAlmostEqual(reading.temperature_c, BASE_TEMP_C["fridge"], delta=1.0)
            self.assertAlmostEqual(reading.current_a, BASE_CURRENT_A["fridge"], delta=0.5)
            self.assertFalse(reading.door_open)

    def test_seed_makes_ticks_reproducible(self) -> None:
        first = [r.temperature_c for r in run(VirtualFridge(seed=3), 8)]
        second = [r.temperature_c for r in run(VirtualFridge(seed=3), 8)]
        self.assertEqual(first, second)

    def test_door_open_warms_fridge_into_warning_band(self) -> None:
        fridge = VirtualFridge(seed=11)
        fridge.apply_fault("door_open")
        readings = run(fridge, 20)
        self.assertTrue(all(r.door_open for r in readings))
        self.assertGreater(readings[-1].temperature_c, 5.0)

    def test_door_open_warms_freezer_into_warning_band(self) -> None:
        fridge = VirtualFridge(appliance_type="freezer", seed=11)
        fridge.apply_fault("door_open")
        readings = run(fridge, 30)
        self.assertGreater(readings[-1].temperature_c, -15.0)

    def test_condenser_fouling_raises_current(self) -> None:
        fridge = VirtualFridge(seed=5)
        fridge.apply_fault("condenser_fouling")
        readings = run(fridge, 20)
        tail = [r.current_a for r in readings[-5:]]
        self.assertGreater(sum(tail) / len(tail), 1.3 * BASE_CURRENT_A["fridge"])
        self.assertGreater(readings[-1].temperature_c, BASE_TEMP_C["fridge"])

    def test_power_surge_spikes_then_clears(self) -> None:
        fridge = VirtualFridge(seed=9)
        fridge.apply_fault("power_surge")
        self.assertTrue(fridge.snapshot()["surge_active"])
        spiked = run(fridge, 3)
        for reading in spiked:
            self.assertGreater(reading.current_a, 3.0 * BASE_CURRENT_A["fridge"])
        self.assertFalse(fridge.snapshot()["surge_active"])
        settled = run(fridge, 5)[-1]
        self.assertLess(settled.current_a, 2.0 * BASE_CURRENT_A["fridge"])

    def test_rapid_restart_spikes_every_fourth_tick(self) -> None:
        fridge = VirtualFridge(seed=2)
        fridge.apply_fault("rapid_restart")
        readings = run(fridge, 8)
        for index, reading in enumerate(readings, start=1):
            if index % 4 == 0:
                self.assertGreater(
                    reading.current_a, 3.0 * BASE_CURRENT_A["fridge"]
                )
            else:
                self.assertLess(reading.current_a, 2.0 * BASE_CURRENT_A["fridge"])

    def test_close_door_recovers(self) -> None:
        fridge = VirtualFridge(seed=11)
        fridge.apply_fault("door_open")
        run(fridge, 15)
        self.assertGreater(fridge.temp_c, 5.0)
        fridge.apply_action("close_door")
        run(fridge, 40)
        self.assertLess(fridge.temp_c, 5.0)

    def test_clean_condenser_recovers_current(self) -> None:
        fridge = VirtualFridge(seed=5)
        fridge.apply_fault("condenser_fouling")
        run(fridge, 20)
        fridge.apply_action("clean_condenser")
        settled = run(fridge, 15)[-1]
        self.assertLess(settled.current_a, 1.3 * BASE_CURRENT_A["fridge"])

    def test_reset_clears_everything(self) -> None:
        fridge = VirtualFridge(seed=4)
        fridge.apply_fault("door_open")
        fridge.apply_fault("condenser_fouling")
        fridge.apply_fault("rapid_restart")
        run(fridge, 10)
        fridge.apply_action("reset")
        snap = fridge.snapshot()
        self.assertFalse(snap["door_open"])
        self.assertFalse(snap["condenser_dirty"])
        self.assertFalse(snap["surge_active"])
        self.assertFalse(snap["short_cycling"])
        self.assertEqual(snap["temp_c"], BASE_TEMP_C["fridge"])

    def test_unknown_fault_and_action_rejected(self) -> None:
        fridge = VirtualFridge()
        with self.assertRaises(ValueError):
            fridge.apply_fault("meteor_strike")
        with self.assertRaises(ValueError):
            fridge.apply_action("kick_it")

    def test_window_carries_no_fault_label(self) -> None:
        fridge = VirtualFridge(seed=6)
        fridge.apply_fault("door_open")
        readings = run(fridge, 5)
        telemetry = fridge.window(readings)
        self.assertEqual(len(telemetry.readings), 5)
        # No field names the injected fault; door_open is a genuine sensor bit.
        self.assertNotIn("fault", telemetry.model_dump_json())
        self.assertTrue(all(r.door_open for r in telemetry.readings))


if __name__ == "__main__":
    unittest.main()
