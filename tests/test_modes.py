"""P4: mode set/get, manual-beats-device, expiry, overrun."""

import tempfile
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from apps.api.main import app
from core.setup import modes


def _profile_with_modes():
    from core.schemas.profile import ModeRelaxation, Provenance, SystemProfile

    prov = Provenance(source_doc="manual")
    return SystemProfile(
        system_id="s-1",
        name="S",
        kind="software",
        modes=[
            ModeRelaxation(
                mode="deploying", relaxes=["retry=1"],
                max_duration_s=60, provenance=prov,
            )
        ],
    )


class ModesUnitTests(unittest.TestCase):
    def setUp(self) -> None:
        modes.clear_all()

    def test_manual_beats_device(self) -> None:
        modes.set_mode("s-1", "deploying", duration_s=60)
        state = modes.current_mode("s-1", _profile_with_modes(), "defrost")
        self.assertEqual((state.mode, state.source), ("deploying", "manual"))

    def test_expiry_clears_back_to_device(self) -> None:
        modes.set_mode("s-1", "deploying", duration_s=60, now=1000.0)
        state = modes.current_mode(
            "s-1", _profile_with_modes(), "defrost", now=2000.0
        )
        self.assertEqual((state.mode, state.source), ("defrost", "device"))

    def test_empty_clears(self) -> None:
        modes.set_mode("s-1", "deploying")
        modes.set_mode("s-1", "")
        state = modes.current_mode("s-1", _profile_with_modes(), "")
        self.assertEqual(state.mode, "")

    def test_overrun_flags(self) -> None:
        modes.set_mode("s-1", "deploying", now=1000.0)
        fresh = modes.current_mode("s-1", _profile_with_modes(), now=1030.0)
        self.assertFalse(fresh.overrun)
        stale = modes.current_mode("s-1", _profile_with_modes(), now=2000.0)
        self.assertTrue(stale.overrun)
        self.assertEqual(stale.max_duration_s, 60)

    def test_unknown_mode_has_no_max(self) -> None:
        modes.set_mode("s-1", "weird", now=1000.0)
        state = modes.current_mode("s-1", _profile_with_modes(), now=9999.0)
        self.assertFalse(state.overrun)


class ModesApiTests(unittest.TestCase):
    def setUp(self) -> None:
        modes.clear_all()

    def _create(self, client, kind="software"):
        body = {"name": "S", "kind": kind}
        if kind == "appliance":
            body["appliance_type"] = "fridge"
        created = client.post("/api/systems", json=body)
        self.assertEqual(created.status_code, 200)
        return created.json()["system_id"]

    def test_set_get_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"TA_DATA_DIR": tmp}):
                with TestClient(app) as client:
                    system_id = self._create(client)
                    profile = client.get(
                        f"/api/systems/{system_id}/profile"
                    ).json()["profile"]
                    profile["modes"] = [{
                        "mode": "deploying", "relaxes": ["retry=1"],
                        "max_duration_s": 60,
                        "provenance": {"source_doc": "manual"},
                    }]
                    put = client.put(
                        f"/api/systems/{system_id}/profile", json=profile
                    )
                    self.assertEqual(put.status_code, 200)
                    set_mode = client.post(
                        f"/api/systems/{system_id}/mode",
                        json={"mode": "deploying", "duration_s": 60},
                    )
                    self.assertEqual(set_mode.status_code, 200)
                    got = client.get(f"/api/systems/{system_id}/mode")
                    self.assertEqual(got.json()["mode"], "deploying")
                    self.assertEqual(got.json()["source"], "manual")
                    self.assertFalse(got.json()["overrun"])
                    bad = client.post(
                        f"/api/systems/{system_id}/mode",
                        json={"mode": "nope"},
                    )
                    self.assertEqual(bad.status_code, 400)

    def test_device_defrost_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"TA_DATA_DIR": tmp}):
                with TestClient(app) as client:
                    system_id = self._create(client, kind="appliance")
                    client.post(
                        "/api/sim/fridge/defrost", json={"duration_ticks": 50}
                    )
                    try:
                        got = client.get(f"/api/systems/{system_id}/mode")
                    finally:
                        client.post(
                            "/api/sim/fridge/action",
                            json={"action": "end_defrost"},
                        )
                    self.assertEqual(got.json()["mode"], "defrost")
                    self.assertEqual(got.json()["source"], "device")

    def test_deploy_sets_pipeline_mode(self) -> None:
        from apps.api import main as api_main

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"TA_DATA_DIR": tmp}):
                with TestClient(app) as client:
                    system_id = self._create(client)
                    profile = client.get(
                        f"/api/systems/{system_id}/profile"
                    ).json()["profile"]
                    profile["modes"] = [{
                        "mode": "deploying", "relaxes": ["retry=1"],
                        "max_duration_s": 60,
                        "provenance": {"source_doc": "manual"},
                    }]
                    client.put(
                        f"/api/systems/{system_id}/profile", json=profile
                    )
                    with patch.object(
                        api_main, "shop_base_url",
                        return_value="http://shop:1",
                    ), patch("httpx.post") as posted:
                        posted.return_value.status_code = 200
                        posted.return_value.json.return_value = {
                            "deploying": True
                        }
                        deploy = client.post(
                            "/api/sim/shop/deploy",
                            json={"duration_s": 20},
                        )
                    self.assertEqual(deploy.status_code, 200)
                    got = client.get(f"/api/systems/{system_id}/mode")
                    self.assertEqual(got.json()["mode"], "deploying")


if __name__ == "__main__":
    unittest.main()
