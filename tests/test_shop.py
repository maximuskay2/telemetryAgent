"""Shop pins ordering, wedging logs, metrics math, and endpoints (Sim 1)."""

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SHOP_APP = Path(__file__).resolve().parent.parent / "demo" / "shop" / "app.py"
BUGGY = (
    Path(__file__).resolve().parent.parent / "demo" / "target-service" / "inventory.py"
)
FIXED_MODULE = '''"""Fixed copy: canonical lock order, no deadlock."""
import threading
_locks = {}
_guard = threading.Lock()

def _lock_for(item):
    with _guard:
        return _locks.setdefault(item, threading.Lock())

def acquire_all(items):
    acquired = []
    for item in sorted(items):
        lock = _lock_for(item)
        lock.acquire()
        acquired.append((item, lock))
    return acquired

def release_all(acquired):
    for _, lock in reversed(acquired):
        lock.release()
'''


def _load_app():
    spec = importlib.util.spec_from_file_location("demo_shop_app", SHOP_APP)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ShopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _load_app()
        # Importing the app opens the real shop log; tests use their own Shop.
        cls.app.shop.log.close()

    def _shop(self, tmp, inventory_path=None):
        return self.app.Shop(
            inventory_path=inventory_path or str(BUGGY),
            log_path=os.path.join(tmp, "shop.log"),
            api_base="http://127.0.0.1:9",  # unroutable: publish must not block
        )

    def test_loader_exposes_lock_api(self) -> None:
        module = self.app.load_inventory(str(BUGGY))
        self.assertTrue(callable(module.acquire_all))
        self.assertTrue(callable(module.release_all))

    def test_successful_order_moves_stock(self) -> None:
        with tempfile.TemporaryDirectory(prefix="shop") as tmp:
            shop = self._shop(tmp)
            try:
                result = shop.place_order(["axle", "brake-pad"])
            finally:
                shop.log.close()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(shop.stock["axle"], 101)
        self.assertEqual(shop.stock["brake-pad"], 99)

    def test_unknown_skus_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="shop") as tmp:
            shop = self._shop(tmp)
            try:
                result = shop.place_order(["axle", "nope"])
            finally:
                shop.log.close()
        self.assertEqual(result["status"], "failed")

    def test_wedged_order_logs_retries_then_deadlock(self) -> None:
        with tempfile.TemporaryDirectory(prefix="shop") as tmp:
            shop = self._shop(tmp)
            try:
                with patch.object(
                    shop, "acquire_timed", return_value=(None, True)
                ), patch("time.sleep", return_value=None):
                    result = shop.place_order(["axle", "brake-pad"])
            finally:
                shop.log.close()
            with open(os.path.join(tmp, "shop.log"), encoding="utf-8") as f:
                text = f.read()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["reason"], "deadlock")
        self.assertIn("WARNING retry=1", text)
        self.assertIn("WARNING retry=3", text)
        self.assertIn("Deadlock detected", text)

    def test_fixed_module_orders_cleanly(self) -> None:
        with tempfile.TemporaryDirectory(prefix="shop") as tmp:
            fixed = os.path.join(tmp, "fixed_inventory.py")
            with open(fixed, "w", encoding="utf-8") as f:
                f.write(FIXED_MODULE)
            shop = self._shop(tmp, inventory_path=fixed)
            try:
                result = shop.place_order(["brake-pad", "axle"])
            finally:
                shop.log.close()
        self.assertEqual(result["status"], "ok")

    def test_metrics_math(self) -> None:
        metrics = self.app.Metrics()
        for _ in range(9):
            metrics.record(True, 10.0)
        metrics.record(False, 500.0)
        snapshot = metrics.snapshot(window_s=3600)
        self.assertGreater(snapshot["orders_per_min"], 0)
        self.assertAlmostEqual(snapshot["error_rate"], 0.1)
        self.assertEqual(snapshot["p95_ms"], 500.0)

    def test_products_endpoint(self) -> None:
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory(prefix="shop") as tmp:
            shop = self._shop(tmp)
            try:
                with patch.object(self.app, "shop", shop):
                    with TestClient(self.app.app) as client:
                        response = client.get("/products")
            finally:
                shop.log.close()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["products"]), 12)

    def test_order_endpoint_success_and_validation(self) -> None:
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory(prefix="shop") as tmp:
            shop = self._shop(tmp)
            try:
                with patch.object(self.app, "shop", shop):
                    with TestClient(self.app.app) as client:
                        ok_response = client.post(
                            "/orders", json={"items": ["axle", "chain"]}
                        )
                        bad_response = client.post(
                            "/orders", json={"items": ["axle"]}
                        )
            finally:
                shop.log.close()
        self.assertEqual(ok_response.status_code, 200)
        self.assertEqual(ok_response.json()["status"], "ok")
        self.assertEqual(bad_response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
