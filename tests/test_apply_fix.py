"""Proof-it's-fixed tests (Sim 5): shop hot-swap + runbook apply."""

import hashlib
import importlib.util
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from apps.api.main import appliance_runs, app, shop_runtime_path, software_runs
from core.agent.loop import run_software_loop
from core.schemas.diagnosis import Diagnosis
from core.schemas.remediation import (
    ApplianceResult,
    ExecutionResult,
    GeneratedPatch,
    Runbook,
)
from core.schemas.telemetry import SoftwareTelemetry
from core.simulate.fridge_stream import map_step_to_action
from tests.test_shop import FIXED_MODULE

REPO = Path(__file__).resolve().parent.parent
BUGGY = REPO / "demo" / "target-service" / "inventory.py"
SHOP_APP = REPO / "demo" / "shop" / "app.py"

DIAGNOSIS = Diagnosis(
    summary="Deadlock on inventory_items",
    likely_cause="Lock ordering inversion",
    suggested_actions=["Sort lock acquisition"],
    confidence=0.9,
)
PATCH = GeneratedPatch(
    patch_code=FIXED_MODULE, test_code="def test_x(): assert True\n"
)
TELEMETRY = SoftwareTelemetry(source_id="test", raw_log="deadlock log")


def _load_shop_app():
    spec = importlib.util.spec_from_file_location("demo_shop_app_sim5", SHOP_APP)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _silent_env(**overrides):
    base = {"BASETEN_API_KEY": "", "FIREWORKS_API_KEY": "", "MODEL_API_KEY": "",
            "META_MODEL_API_KEY": "", "FIREWORKS_PATCH_MODEL": ""}
    base.update(overrides)
    return patch.dict(os.environ, base, clear=False)


def _ok_reload(url, json=None, timeout=None):
    response = httpx.Response(200, json={"inventory": json["inventory_path"]})
    return response


class LoopPatchCodeTest(unittest.TestCase):
    def test_pass_result_carries_patch_code(self) -> None:
        with _silent_env(BASETEN_API_KEY="x"), \
                patch("core.agent.loop.meta_client.diagnose",
                      return_value=DIAGNOSIS), \
                patch("core.infer.baseten_client.generate_patch",
                      return_value=PATCH), \
                patch("core.agent.loop.verify_patch",
                      return_value={"passed": True, "feedback": "1 passed"}):
            result = run_software_loop(TELEMETRY)
        self.assertEqual(result.status, "PASS")
        self.assertEqual(result.patch_code, FIXED_MODULE)

    def test_fail_result_has_no_patch(self) -> None:
        with _silent_env(BASETEN_API_KEY="x"), \
                patch("core.agent.loop.meta_client.diagnose",
                      return_value=DIAGNOSIS), \
                patch("core.infer.baseten_client.generate_patch",
                      return_value=PATCH), \
                patch("core.agent.loop.verify_patch",
                      return_value={"passed": False, "feedback": "nope"}), \
                patch("core.agent.loop.meta_client.generate_patch",
                      return_value=PATCH):
            result = run_software_loop(TELEMETRY, max_attempts=1)
        self.assertEqual(result.status, "FAIL")
        self.assertIsNone(result.patch_code)


class ApplyFixApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.buggy_hash = hashlib.sha256(BUGGY.read_bytes()).hexdigest()

    def tearDown(self) -> None:
        for key in ("run-pass", "run-fail", "run-nopatch", "run-other"):
            software_runs.pop(key, None)
        runtime = shop_runtime_path()
        if runtime.exists():
            runtime.unlink()
        try:
            runtime.parent.rmdir()
        except OSError:
            pass
        self.assertEqual(hashlib.sha256(BUGGY.read_bytes()).hexdigest(),
                         self.buggy_hash)

    def _inject(self, run_id, status, target, patch_code=None):
        software_runs[run_id] = {
            "target": target,
            "result": ExecutionResult(
                status=status, stdout="", stderr="", attempts=1,
                model_used="test", run_id=run_id, patch_code=patch_code,
            ),
        }

    def test_deploy_writes_runtime_and_reloads(self) -> None:
        self._inject("run-pass", "PASS", "inventory", FIXED_MODULE)
        with TestClient(app) as client:
            with client.websocket_connect("/api/ws") as websocket:
                with patch("httpx.post", side_effect=_ok_reload):
                    response = client.post(
                        "/api/sim/shop/apply-fix", json={"run_id": "run-pass"}
                    )
                self.assertEqual(response.status_code, 200)
                event = websocket.receive_json()
        body = response.json()
        self.assertTrue(body["inventory"].endswith("inventory_active.py"))
        self.assertEqual(shop_runtime_path().read_text(), FIXED_MODULE)
        self.assertEqual(event["kind"], "fix_applied")
        self.assertEqual(event["payload"]["domain"], "software")

    def test_unknown_run_rejected(self) -> None:
        with TestClient(app) as client:
            response = client.post(
                "/api/sim/shop/apply-fix", json={"run_id": "nope"}
            )
        self.assertEqual(response.status_code, 404)

    def test_fail_run_rejected(self) -> None:
        self._inject("run-fail", "FAIL", "inventory", FIXED_MODULE)
        with TestClient(app) as client:
            response = client.post(
                "/api/sim/shop/apply-fix", json={"run_id": "run-fail"}
            )
        self.assertEqual(response.status_code, 409)
        self.assertFalse(shop_runtime_path().exists())

    def test_pass_without_patch_rejected(self) -> None:
        self._inject("run-nopatch", "PASS", "inventory", None)
        with TestClient(app) as client:
            response = client.post(
                "/api/sim/shop/apply-fix", json={"run_id": "run-nopatch"}
            )
        self.assertEqual(response.status_code, 409)

    def test_non_inventory_run_rejected(self) -> None:
        self._inject("run-other", "PASS", None, FIXED_MODULE)
        with TestClient(app) as client:
            response = client.post(
                "/api/sim/shop/apply-fix", json={"run_id": "run-other"}
            )
        self.assertEqual(response.status_code, 409)

    def test_shop_unreachable_is_502(self) -> None:
        self._inject("run-pass", "PASS", "inventory", FIXED_MODULE)
        with TestClient(app) as client:
            with patch("httpx.post", side_effect=httpx.ConnectError("down")):
                response = client.post(
                    "/api/sim/shop/apply-fix", json={"run_id": "run-pass"}
                )
        self.assertEqual(response.status_code, 502)

    def test_nonconforming_patch_rejected_before_write(self) -> None:
        """A PASS patch without the inventory API must not deploy (e2e)."""
        self._inject(
            "run-pass", "PASS", "inventory",
            "def with_retry(fn):\n    return fn()\n",
        )
        with TestClient(app) as client:
            with patch("httpx.post", side_effect=_ok_reload) as posted:
                response = client.post(
                    "/api/sim/shop/apply-fix", json={"run_id": "run-pass"}
                )
        self.assertEqual(response.status_code, 409)
        self.assertIn("contract", response.json()["detail"])
        self.assertFalse(shop_runtime_path().exists())
        posted.assert_not_called()


class ShopReloadTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.shop_app = _load_shop_app()
        cls.shop_app.shop.log.close()

    def test_reload_uses_patched_module(self) -> None:
        runtime = shop_runtime_path()
        runtime.parent.mkdir(parents=True, exist_ok=True)
        runtime.write_text(FIXED_MODULE, encoding="utf-8")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                shop = self.shop_app.Shop(
                    inventory_path=str(BUGGY),
                    log_path=os.path.join(tmp, "shop.log"),
                    api_base="http://127.0.0.1:9",
                )
                resolved = shop.reload_inventory(str(runtime))
                self.assertEqual(resolved, os.path.realpath(runtime))
                errors: list = []

                def order():
                    try:
                        for _ in range(5):
                            result = shop.place_order(["axle", "gasket"])
                            if result["status"] != "ok":
                                errors.append(result)
                    except Exception as exc:  # noqa: BLE001
                        errors.append(exc)

                threads = [threading.Thread(target=order) for _ in range(8)]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join()
                self.assertEqual(errors, [])
        finally:
            if runtime.exists():
                runtime.unlink()
            try:
                runtime.parent.rmdir()
            except OSError:
                pass

    def test_reload_rejects_paths_outside_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            shop = self.shop_app.Shop(
                inventory_path=str(BUGGY),
                log_path=os.path.join(tmp, "shop.log"),
                api_base="http://127.0.0.1:9",
            )
            with self.assertRaises(ValueError):
                shop.reload_inventory("/etc/passwd")
            self.assertEqual(
                os.path.realpath(shop.inventory_path),
                os.path.realpath(str(BUGGY)),
            )

    def test_reload_endpoint_validates_path(self) -> None:
        module = _load_shop_app()
        module.shop.log.close()
        with TestClient(module.app) as client:
            denied = client.post(
                "/reload", json={"inventory_path": "/etc/passwd"}
            )
            self.assertEqual(denied.status_code, 400)

    def test_deploy_endpoint_starts_window(self) -> None:
        module = _load_shop_app()
        module.shop.log.close()
        with tempfile.TemporaryDirectory() as tmp:
            module.shop.log = module.ShopLogger(
                os.path.join(tmp, "shop.log")
            )
            try:
                with TestClient(module.app) as client:
                    response = client.post(
                        "/deploy", json={"duration_s": 5}
                    )
            finally:
                module.shop.log.close()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["deploying"])
        self.assertTrue(module.shop.deploying)

    def test_reload_rejects_nonconforming_module(self) -> None:
        """A runtime file without the lock API must not swap in (e2e)."""
        runtime = shop_runtime_path()
        runtime.parent.mkdir(parents=True, exist_ok=True)
        runtime.write_text(
            "def with_retry(fn):\n    return fn()\n", encoding="utf-8"
        )
        try:
            with tempfile.TemporaryDirectory() as tmp:
                shop = self.shop_app.Shop(
                    inventory_path=str(BUGGY),
                    log_path=os.path.join(tmp, "shop.log"),
                    api_base="http://127.0.0.1:9",
                )
                with self.assertRaisesRegex(ValueError, "rejected"):
                    shop.reload_inventory(str(runtime))
                self.assertEqual(
                    os.path.realpath(shop.inventory_path),
                    os.path.realpath(str(BUGGY)),
                )
        finally:
            if runtime.exists():
                runtime.unlink()
            try:
                runtime.parent.rmdir()
            except OSError:
                pass

    def test_reload_rejects_unimportable_file(self) -> None:
        runtime = shop_runtime_path()
        runtime.parent.mkdir(parents=True, exist_ok=True)
        runtime.write_text("def broken(:\n", encoding="utf-8")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                shop = self.shop_app.Shop(
                    inventory_path=str(BUGGY),
                    log_path=os.path.join(tmp, "shop.log"),
                    api_base="http://127.0.0.1:9",
                )
                with self.assertRaisesRegex(ValueError, "does not import"):
                    shop.reload_inventory(str(runtime))
        finally:
            if runtime.exists():
                runtime.unlink()
            try:
                runtime.parent.rmdir()
            except OSError:
                pass


class RunbookMappingTest(unittest.TestCase):
    def test_door_condenser_reset_map(self) -> None:
        self.assertEqual(
            map_step_to_action("Close the fridge door fully and check the seal"),
            "close_door",
        )
        self.assertEqual(
            map_step_to_action("Clean the condenser coils with a brush"),
            "clean_condenser",
        )
        self.assertEqual(
            map_step_to_action("Power cycle the unit after 5 minutes"),
            "reset",
        )

    def test_unmappable_steps_return_none(self) -> None:
        self.assertIsNone(map_step_to_action("Replace the start relay"))
        self.assertIsNone(map_step_to_action("Wait 180s restart delay"))
        self.assertIsNone(map_step_to_action("Call the owner"))


class ApplyRunbookApiTest(unittest.TestCase):
    def tearDown(self) -> None:
        for key in ("app-pass", "app-fail", "app-unsafe"):
            appliance_runs.pop(key, None)
        from apps.api.main import fridge, sensor_watcher

        fridge.apply_action("reset")
        sensor_watcher.reset()

    def _inject(self, run_id, status, steps, target_c=3.5):
        appliance_runs[run_id] = {
            "appliance_type": "fridge",
            "result": ApplianceResult(
                status=status,
                runbook=Runbook(
                    steps=steps,
                    target_temperature_c=target_c,
                    restart_delay_s=180,
                    power_off_minutes=0,
                ),
                attempts=1,
                model_used="test",
                run_id=run_id,
            ),
        }

    def test_apply_maps_steps_and_skips_rest(self) -> None:
        from apps.api.main import fridge

        fridge.apply_fault("door_open")
        self.assertTrue(fridge.snapshot()["door_open"])
        self._inject("app-pass", "PASS", [
            "Close the fridge door fully",
            "Replace the start relay",
        ])
        with TestClient(app) as client:
            with client.websocket_connect("/api/ws") as websocket:
                response = client.post(
                    "/api/sim/fridge/apply-runbook", json={"run_id": "app-pass"}
                )
                self.assertEqual(response.status_code, 200)
                event = websocket.receive_json()
        body = response.json()
        self.assertEqual(
            body["applied"],
            [{"step": "Close the fridge door fully", "action": "close_door"}],
        )
        self.assertEqual(body["skipped"], ["Replace the start relay"])
        self.assertFalse(body["state"]["door_open"])
        self.assertEqual(event["kind"], "fix_applied")
        self.assertEqual(event["payload"]["domain"], "appliance")

    def test_fail_run_rejected(self) -> None:
        self._inject("app-fail", "FAIL", ["Close the fridge door"])
        with TestClient(app) as client:
            response = client.post(
                "/api/sim/fridge/apply-runbook", json={"run_id": "app-fail"}
            )
        self.assertEqual(response.status_code, 409)

    def test_unsafe_runbook_rejected_by_resafety_check(self) -> None:
        self._inject("app-unsafe", "PASS", ["Close the fridge door"],
                     target_c=30.0)
        with TestClient(app) as client:
            response = client.post(
                "/api/sim/fridge/apply-runbook", json={"run_id": "app-unsafe"}
            )
        self.assertEqual(response.status_code, 409)

    def test_unknown_run_rejected(self) -> None:
        with TestClient(app) as client:
            response = client.post(
                "/api/sim/fridge/apply-runbook", json={"run_id": "nope"}
            )
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
