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

    def test_defrost_climbs_then_recovers(self) -> None:
        fridge = VirtualFridge(seed=21)
        fridge.defrost_schedule = False
        fridge.start_defrost(duration_ticks=20)
        first_half = run(fridge, 10)
        self.assertTrue(fridge.snapshot()["defrost_active"])
        second_half = run(fridge, 10)
        peak = max(
            [r.temperature_c for r in first_half + second_half]
        )
        self.assertGreater(peak, 5.5)
        self.assertLess(peak, 7.5)
        self.assertFalse(fridge.snapshot()["defrost_active"])
        recovered = run(fridge, 30)[-1].temperature_c
        self.assertAlmostEqual(
            recovered, BASE_TEMP_C["fridge"], delta=1.0
        )

    def test_defrost_runs_on_schedule(self) -> None:
        fridge = VirtualFridge(seed=22)
        run(fridge, 359)
        self.assertFalse(fridge.snapshot()["defrost_active"])
        fridge.tick()
        self.assertTrue(fridge.snapshot()["defrost_active"])

    def test_defrost_stuck_blows_past_limit(self) -> None:
        fridge = VirtualFridge(seed=23)
        fridge.apply_fault("defrost_stuck")
        temps = [r.temperature_c for r in run(fridge, 40)]
        self.assertGreater(temps[-1], 8.0)
        self.assertTrue(fridge.snapshot()["defrost_stuck"])
        fridge.apply_action("end_defrost")
        self.assertFalse(fridge.snapshot()["defrost_active"])

    def test_restart_draws_inrush(self) -> None:
        fridge = VirtualFridge(seed=24)
        base = BASE_CURRENT_A["fridge"]
        fridge.restart()
        spike = [r.current_a for r in run(fridge, 3)]
        self.assertTrue(all(a > 3.0 * base for a in spike))
        settled = run(fridge, 3)[-1].current_a
        self.assertLess(settled, 2.0 * base)

    def test_restock_closes_itself(self) -> None:
        fridge = VirtualFridge(seed=25)
        fridge.open_door(ticks=2)
        first = fridge.tick()
        second = fridge.tick()
        third = fridge.tick()
        self.assertTrue(first.door_open)
        self.assertFalse(second.door_open)
        self.assertFalse(third.door_open)

    def test_ambient_hot_raises_steady_current(self) -> None:
        cool = VirtualFridge(seed=26)
        hot = VirtualFridge(seed=26)
        hot.set_ambient_hot(True)
        cool_avg = sum(r.current_a for r in run(cool, 10)) / 10
        hot_avg = sum(r.current_a for r in run(hot, 10)) / 10
        self.assertAlmostEqual(hot_avg / cool_avg, 1.15, delta=0.05)

    def test_reset_triggers_inrush(self) -> None:
        fridge = VirtualFridge(seed=27)
        fridge.apply_action("reset")
        self.assertTrue(fridge.snapshot()["inrush_active"])

    def test_reading_carries_defrost_mode(self) -> None:
        fridge = VirtualFridge(seed=28)
        fridge.defrost_schedule = False
        self.assertEqual(fridge.tick().mode, "")
        fridge.start_defrost(duration_ticks=5)
        self.assertEqual(fridge.tick().mode, "defrost")

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
