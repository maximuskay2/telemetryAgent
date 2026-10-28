"""Interface-contract tests: a patch that ignores the shop's module API must
fail the shape check, the sandbox harness, the deploy gate, and reload."""

import unittest

from core.verify.contracts import (
    HARNESS_PYTEST,
    check_inventory_source,
    contract_for_target,
    inventory_contract,
    load_module_from_source,
    run_inventory_harness,
)
from tests.test_shop import BUGGY, FIXED_MODULE

#: The e2e failure shape (Oct 28): a plausible-looking helper module with no
#: acquire_all/release_all at all.
SQL_HELPER = '''"""Retry helper with no inventory API."""
import time

class DeadlockError(Exception):
    pass

def with_retry(fn, tries=3):
    for _ in range(tries):
        try:
            return fn()
        except DeadlockError:
            time.sleep(0.01)
    raise DeadlockError("still failing")
'''

MISSING_RELEASE = '''""" acquire_all only; release_all forgotten. """
import threading
_locks = {}

def acquire_all(items):
    return [(i, threading.Lock()) for i in sorted(items)]
'''


class CheckSourceTests(unittest.TestCase):
    def test_fixed_module_passes(self) -> None:
        self.assertIsNone(check_inventory_source(FIXED_MODULE))

    def test_buggy_original_passes_shape(self) -> None:
        # The buggy file has the right shape (wrong order); shape is not
        # correctness — the harness covers order.
        self.assertIsNone(check_inventory_source(BUGGY.read_text()))

    def test_sql_helper_rejected(self) -> None:
        reason = check_inventory_source(SQL_HELPER)
        self.assertIn("acquire_all", reason or "")

    def test_missing_release_rejected(self) -> None:
        reason = check_inventory_source(MISSING_RELEASE)
        self.assertIn("release_all", reason or "")

    def test_syntax_error_reported(self) -> None:
        reason = check_inventory_source("def broken(:\n")
        self.assertIn("does not import", reason or "")

    def test_smoke_failure_reported(self) -> None:
        reason = check_inventory_source(
            "def acquire_all(items):\n"
            "    raise RuntimeError('db down')\n"
            "def release_all(held):\n"
            "    pass\n"
        )
        self.assertIn("smoke call failed", reason or "")


class HarnessTests(unittest.TestCase):
    def test_fixed_module_clean(self) -> None:
        module = load_module_from_source(FIXED_MODULE)
        self.assertEqual(run_inventory_harness(module), [])

    def test_buggy_original_fails_order(self) -> None:
        module = load_module_from_source(BUGGY.read_text())
        violations = run_inventory_harness(module)
        self.assertTrue(
            any("canonical" in v for v in violations), violations
        )

    def test_sql_helper_fails_interface(self) -> None:
        module = load_module_from_source(SQL_HELPER)
        violations = run_inventory_harness(module)
        self.assertTrue(
            any("acquire_all" in v for v in violations), violations
        )

    def test_pytest_file_is_self_contained(self) -> None:
        self.assertIn("import solution", HARNESS_PYTEST)
        self.assertIn("def run_inventory_harness", HARNESS_PYTEST)
        self.assertIn("def test_inventory_contract", HARNESS_PYTEST)
        # No repo imports: the sandbox has no repo to import from.
        self.assertNotIn("import core", HARNESS_PYTEST)
        self.assertNotIn("from core", HARNESS_PYTEST)
        compile(HARNESS_PYTEST, "<harness>", "exec")

    def _run_artifact(self, solution_source: str) -> None:
        """Execute the exact pytest file with an injected solution module."""
        import sys

        sys.modules["solution"] = load_module_from_source(
            solution_source, name="solution"
        )
        try:
            namespace: dict = {}
            exec(HARNESS_PYTEST, namespace)
            namespace["test_inventory_contract"]()
        finally:
            del sys.modules["solution"]

    def test_pytest_artifact_passes_fixed(self) -> None:
        self._run_artifact(FIXED_MODULE)

    def test_pytest_artifact_fails_buggy(self) -> None:
        with self.assertRaisesRegex(AssertionError, "canonical"):
            self._run_artifact(BUGGY.read_text())


class ContractTextTests(unittest.TestCase):
    def test_inventory_contract_pins_api(self) -> None:
        text = inventory_contract("ORIGINAL")
        self.assertIn("acquire_all", text)
        self.assertIn("release_all", text)
        self.assertIn("ORIGINAL", text)

    def test_resolver(self) -> None:
        contract, harness = contract_for_target("inventory", "ORIGINAL")
        self.assertIn("acquire_all", contract or "")
        self.assertIn("test_inventory_contract", harness or "")
        self.assertEqual(contract_for_target("other", "x"), (None, None))
        self.assertEqual(contract_for_target("inventory", None), (None, None))


if __name__ == "__main__":
    unittest.main()
