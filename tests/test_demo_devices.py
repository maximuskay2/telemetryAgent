"""Demo device sessions: register, watch, resolve (file backend + routes)."""

import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from apps.api.main import app


def _tmp_data() -> str:
    return tempfile.mkdtemp(prefix="ta-demo-dev-")


class DemoDeviceStoreTests(unittest.TestCase):
    def test_register_watch_list_file_backend(self) -> None:
        from core.commerce import repo as repo_module

        tmp = _tmp_data()
        with patch.dict(os.environ, {"TA_DATA_DIR": tmp}):
            os.environ.pop("DATABASE_URL", None)
            store = repo_module.get_store()
            row, token = store.create_demo_device("Kayode's Pixel")
            self.assertTrue(token.startswith("ta_demo_"))
            self.assertEqual(row["label"], "Kayode's Pixel")
            self.assertEqual(row["watching"], [])
            self.assertNotIn("token_hash", row)

            from core.connections import store as connection_store

            found = store.get_demo_device_by_hash(
                connection_store.hash_key(token)
            )
            self.assertIsNotNone(found)
            assert found is not None
            self.assertEqual(found["id"], row["id"])

            updated = store.set_demo_device_watch(
                row["id"], ["autoparts-shop", "coldchain-1"]
            )
            self.assertIsNotNone(updated)
            assert updated is not None
            self.assertEqual(
                updated["watching"], ["autoparts-shop", "coldchain-1"]
            )
            self.assertIsNotNone(updated["last_seen_at"])

            listed = store.list_demo_devices()
            self.assertEqual(len(listed), 1)
            self.assertNotIn("token_hash", listed[0])

    def test_unknown_token_and_device(self) -> None:
        from core.commerce import repo as repo_module

        tmp = _tmp_data()
        with patch.dict(os.environ, {"TA_DATA_DIR": tmp}):
            os.environ.pop("DATABASE_URL", None)
            store = repo_module.get_store()
            self.assertIsNone(store.get_demo_device_by_hash("nope"))
            self.assertIsNone(store.get_demo_device("demo_nope"))
            self.assertIsNone(
                store.set_demo_device_watch("demo_nope", ["x"])
            )


class DemoDeviceRouteTests(unittest.TestCase):
    def _env(self, tmp: str):
        return patch.dict(os.environ, {"TA_DATA_DIR": tmp})

    def test_register_watch_list_routes(self) -> None:
        tmp = _tmp_data()
        with self._env(tmp):
            os.environ.pop("DATABASE_URL", None)
            with TestClient(app) as client:
                created = client.post(
                    "/api/demo/devices", json={"label": "Kayode's Pixel"}
                )
                self.assertEqual(created.status_code, 200, created.text)
                body = created.json()
                self.assertTrue(
                    body["device_token"].startswith("ta_demo_")
                )
                headers = {
                    "Authorization": f"Bearer {body['device_token']}"
                }
                watch = client.put(
                    "/api/demo/devices/watch",
                    json={"systems": ["autoparts-shop"]},
                    headers=headers,
                )
                self.assertEqual(watch.status_code, 200, watch.text)
                self.assertEqual(
                    watch.json()["watching"], ["autoparts-shop"]
                )
                listed = client.get("/api/demo/devices")
                self.assertEqual(listed.status_code, 200, listed.text)
                devices = listed.json()["devices"]
                self.assertEqual(len(devices), 1)
                self.assertEqual(devices[0]["label"], "Kayode's Pixel")
                self.assertNotIn("token_hash", devices[0])
                self.assertNotIn("device_token", devices[0])

    def test_watch_needs_demo_token(self) -> None:
        tmp = _tmp_data()
        with self._env(tmp):
            os.environ.pop("DATABASE_URL", None)
            with TestClient(app) as client:
                denied = client.put(
                    "/api/demo/devices/watch",
                    json={"systems": ["autoparts-shop"]},
                )
                self.assertEqual(denied.status_code, 401)
                bad = client.put(
                    "/api/demo/devices/watch",
                    json={"systems": []},
                    headers={"Authorization": "Bearer ta_demo_nope"},
                )
                self.assertEqual(bad.status_code, 401)

    def test_register_validates_label(self) -> None:
        tmp = _tmp_data()
        with self._env(tmp):
            os.environ.pop("DATABASE_URL", None)
            with TestClient(app) as client:
                blank = client.post("/api/demo/devices", json={"label": " "})
                self.assertIn(blank.status_code, (400, 422))


if __name__ == "__main__":
    unittest.main()
