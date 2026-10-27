"""Simulator pins each injectable fault's signature and reproducibility."""

import unittest

from core.simulate.appliance import generate_window


class SimulateTests(unittest.TestCase):
    def test_window_shape_and_types(self) -> None:
        window = generate_window("fridge", "none", n_readings=10, seed=7)
        self.assertEqual(window.domain, "appliance")
        self.assertEqual(window.appliance_type, "fridge")
        self.assertEqual(len(window.readings), 10)
        ts = [r.ts for r in window.readings]
        self.assertEqual(ts, sorted(ts))
        self.assertTrue(all(r.current_a >= 0 and r.vibration_g >= 0 for r in window.readings))

    def test_door_open_has_door_events_and_warming(self) -> None:
        window = generate_window("fridge", "door_open", n_readings=30, seed=3)
        doors = [r for r in window.readings if r.door_open]
        self.assertGreater(len(doors), 5)
        first_half = window.readings[:10]
        last_half = window.readings[-10:]
        avg = lambda rs: sum(r.temperature_c for r in rs) / len(rs)
        self.assertGreater(avg(last_half), avg(first_half))

    def test_condenser_fouling_raises_current_over_time(self) -> None:
        window = generate_window("fridge", "condenser_fouling", n_readings=30, seed=3)
        first = sum(r.current_a for r in window.readings[:10]) / 10
        last = sum(r.current_a for r in window.readings[-10:]) / 10
        self.assertGreater(last - first, 0.4)

    def test_power_surge_spikes_current_mid_window(self) -> None:
        window = generate_window("fridge", "power_surge", n_readings=30, seed=3)
        peak = max(r.current_a for r in window.readings)
        self.assertGreater(peak, 4.0)

    def test_rapid_restart_repeats_current_bursts(self) -> None:
        window = generate_window("fridge", "rapid_restart", n_readings=30, seed=3)
        bursts = [r for r in window.readings if r.current_a > 3.0]
        self.assertGreaterEqual(len(bursts), 5)

    def test_same_seed_reproduces_window(self) -> None:
        first = generate_window("freezer", "door_open", seed=11, start_ts=1000.0)
        second = generate_window("freezer", "door_open", seed=11, start_ts=1000.0)
        self.assertEqual(first, second)

    def test_empty_window_rejected(self) -> None:
        with self.assertRaises(ValueError):
            generate_window("fridge", "none", n_readings=0)


if __name__ == "__main__":
    unittest.main()
