"""P0: SystemProfile schema, provenance rules, and versioned storage."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from core.schemas.profile import (
    HardLimit,
    NormalRange,
    Provenance,
    SystemProfile,
)
from core.setup import store

REPO = Path(__file__).resolve().parent.parent


def _prov(**overrides):
    base = {
        "source_doc": "spec.pdf",
        "page_or_region": "p.1",
        "quote": "range 2-5 C",
        "confidence": 0.9,
    }
    base.update(overrides)
    return Provenance(**base)


def _profile(**overrides):
    base = {
        "system_id": "shop-1",
        "name": "Shop",
        "kind": "software",
        "hard_limits": [
            HardLimit(
                metric="error_rate",
                op=">",
                threshold=0.5,
                provenance=_prov(source_doc="manual", quote=""),
            )
        ],
    }
    base.update(overrides)
    return SystemProfile(**base)


class SchemaTests(unittest.TestCase):
    def test_minimal_draft_validates(self) -> None:
        profile = SystemProfile(system_id="x-1", name="X", kind="software")
        self.assertEqual(profile.status, "draft")
        self.assertEqual(profile.version, 1)

    def test_confirmed_needs_hard_limits(self) -> None:
        with self.assertRaises(ValidationError):
            SystemProfile(
                system_id="x-1", name="X", kind="software",
                status="confirmed",
            )

    def test_armed_needs_hard_limits(self) -> None:
        with self.assertRaises(ValidationError):
            SystemProfile(
                system_id="x-1", name="X", kind="software", status="armed"
            )

    def test_appliance_type_rules(self) -> None:
        with self.assertRaises(ValidationError):
            SystemProfile(system_id="x-1", name="X", kind="appliance")
        with self.assertRaises(ValidationError):
            SystemProfile(
                system_id="x-1", name="X", kind="software",
                appliance_type="fridge",
            )
        ok = SystemProfile(
            system_id="x-1", name="X", kind="appliance",
            appliance_type="fridge",
        )
        self.assertEqual(ok.appliance_type, "fridge")

    def test_system_id_pattern(self) -> None:
        with self.assertRaises(ValidationError):
            SystemProfile(system_id="Bad ID!", name="X", kind="software")

    def test_numeric_field_needs_provenance(self) -> None:
        with self.assertRaises(ValidationError):
            NormalRange(metric="temp_c", min=2, max=5)

    def test_doc_value_needs_quote(self) -> None:
        with self.assertRaises(ValidationError):
            _prov(source_doc="spec.pdf", quote="  ")

    def test_manual_value_needs_no_quote(self) -> None:
        prov = _prov(source_doc="manual", quote="")
        self.assertEqual(prov.source_doc, "manual")

    def test_confidence_bounds(self) -> None:
        with self.assertRaises(ValidationError):
            _prov(confidence=1.5)


class SampleProfileTests(unittest.TestCase):
    def test_shop_sample_validates(self) -> None:
        path = REPO / "demo" / "setup" / "profiles" / "shop.json"
        profile = SystemProfile.model_validate_json(path.read_text())
        self.assertEqual(profile.status, "confirmed")
        self.assertTrue(profile.hard_limits)
        self.assertTrue(profile.normal_ranges)

    def test_coldchain_sample_validates(self) -> None:
        path = REPO / "demo" / "setup" / "profiles" / "coldchain.json"
        profile = SystemProfile.model_validate_json(path.read_text())
        self.assertEqual(profile.kind, "appliance")
        self.assertEqual(profile.appliance_type, "fridge")
        self.assertTrue(profile.hard_limits)


class StoreTests(unittest.TestCase):
    def test_round_trip_and_versions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"TA_DATA_DIR": tmp}):
                self.assertIsNone(store.get_profile("shop-1"))
                first = store.save_profile(_profile())
                self.assertEqual(first.version, 1)
                second = store.save_profile(
                    first.model_copy(update={"status": "confirmed"})
                )
                self.assertEqual(second.version, 2)
                loaded = store.get_profile("shop-1")
                assert loaded is not None
                self.assertEqual(loaded.version, 2)
                self.assertEqual(loaded.status, "confirmed")
                old = store.get_version("shop-1", 1)
                assert old is not None
                self.assertEqual(old.version, 1)
                self.assertEqual(old.status, "draft")
                self.assertIsNone(store.get_version("shop-1", 9))
                listed = store.list_profiles()
                self.assertEqual([p.system_id for p in listed], ["shop-1"])
                uploads = store.uploads_dir("shop-1")
                self.assertTrue(str(uploads).endswith("uploads/shop-1"))

    def test_list_skips_bad_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"TA_DATA_DIR": tmp}):
                store.save_profile(_profile())
                (Path(tmp) / "profiles" / "junk.json").write_text(
                    "{nope", encoding="utf-8"
                )
                self.assertEqual(len(store.list_profiles()), 1)


if __name__ == "__main__":
    unittest.main()
