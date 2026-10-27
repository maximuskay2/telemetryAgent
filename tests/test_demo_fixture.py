"""Pins the demo target-service fixture: the seeded bug must reproduce.

inventory.py is the buggy original for fail-to-pass verification and must stay
buggy. If this test goes red, the fixture was disturbed, not fixed.
"""

import importlib.util
import unittest
from pathlib import Path

DEMO_DIR = Path(__file__).resolve().parent.parent / "demo" / "target-service"


def _load_inventory():
    spec = importlib.util.spec_from_file_location("demo_inventory", DEMO_DIR / "inventory.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DemoFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inventory = _load_inventory()

    def test_seeded_bug_acquires_in_caller_order(self) -> None:
        held = self.inventory.acquire_all(["brake-pad", "axle"])
        try:
            self.assertEqual([name for name, _ in held], ["brake-pad", "axle"])
        finally:
            self.inventory.release_all(held)

    def test_canonical_order_contract_currently_violated(self) -> None:
        held = self.inventory.acquire_all(["brake-pad", "axle"])
        try:
            order = [name for name, _ in held]
        finally:
            self.inventory.release_all(held)
        self.assertNotEqual(order, sorted(order))


if __name__ == "__main__":
    unittest.main()
