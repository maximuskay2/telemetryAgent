"""target_path resolves only inside demo/target-service/ (I2)."""

import os
import unittest

from core.verify.targets import TARGET_DIR, read_target_file, resolve_target_path


class TargetsTests(unittest.TestCase):
    def test_resolves_demo_file(self) -> None:
        path = resolve_target_path("inventory.py")
        self.assertEqual(path.parent, TARGET_DIR.resolve())
        self.assertIn("acquire_all", read_target_file("inventory.py"))

    def test_parent_escape_rejected(self) -> None:
        for bad in ("../about.md", "../../README.md", "..", "/etc/passwd",
                    "subdir/../../about.md"):
            with self.assertRaises(ValueError, msg=bad):
                resolve_target_path(bad)

    def test_missing_file_rejected(self) -> None:
        with self.assertRaises(ValueError):
            resolve_target_path("nope.py")

    def test_empty_rejected(self) -> None:
        with self.assertRaises(ValueError):
            resolve_target_path("  ")

    def test_oversize_rejected(self) -> None:
        from core.verify import targets

        big = TARGET_DIR / "_big_fixture_tmp.py"
        big.write_text("x = 1\n" * 20000, encoding="utf-8")
        self.addCleanup(lambda: os.path.exists(big) and os.unlink(big))
        original = targets.MAX_TARGET_BYTES
        targets.MAX_TARGET_BYTES = 100
        self.addCleanup(setattr, targets, "MAX_TARGET_BYTES", original)
        with self.assertRaises(ValueError):
            resolve_target_path("_big_fixture_tmp.py")


if __name__ == "__main__":
    unittest.main()
