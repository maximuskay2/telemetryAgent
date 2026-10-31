"""C-D4 wire-in proof (Jude): cost on a real fix run + blocked-with-reason.

E2E with mocked models/sandbox/GitHub (J-R3 fakes from
tests.test_prod_repofix). Hosted mode is faked with an unreachable
DATABASE_URL: PG calls fail safe into warnings, while the usage /
allowance loop under proof runs on the engine store (MemoryUsageStore).
No network, no Postgres, no live models.

The blocked test stubs only the PG profile/connection reads (James's
C-J3 territory, covered by his tests); the allowance gate, the
blocked-run record, and the usage events are all real.
"""

import asyncio
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

import apps.api.main as api_main
from core.commerce import allowance as allowance_module
from core.commerce.usage import (
    Kind,
    MemoryUsageStore,
    configure_usage_store,
    record_usage,
    reset_usage_store,
    usage_summary,
)
from core.repo_fix import generate as repo_generate
from core.repo_fix import run as repo_run
from core.schemas.profile import SystemProfile
from tests.test_prod_repofix import (
    BASE_TARBALL,
    DIAGNOSIS,
    TRACEBACK_TEXT,
    FakeGitHub,
    FakeSandbox,
    PASS_SCRIPT,
)

RUN_ID = "runwirein34"
ORG_COST = "org-wirein-cost"
ORG_BLOCKED = "org-wirein-blocked"
SYSTEM_ID = "acme-wirein"
FINGERPRINT = "fp9f2c4d8a1b3e"

# Unreachable: flips _hosted() on, PG connects fail fast (refused).
FAKE_DB_URL = "postgresql://localhost:1/wirein"


class WireinTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="ta-wirein-")
        self.store = MemoryUsageStore()
        configure_usage_store(self.store)
        self.addCleanup(reset_usage_store)
        repo_run.reset_run_state()
        api_main.software_runs.pop(RUN_ID, None)

    def test_real_fix_run_carries_cost(self) -> None:
        """PASS run records fix_run + pr + sandbox_time(cost) events."""
        box = FakeSandbox(list(PASS_SCRIPT))
        fake = FakeGitHub(BASE_TARBALL)
        with (
            patch.dict(os.environ, {
                "DATABASE_URL": FAKE_DB_URL,
                "TA_DATA_DIR": self.tmp,
                # Pinned rate for the fake backend so sandbox cost is
                # deterministically visible (wiring proof, not pricing).
                "TA_COST_FAKE_SANDBOX_S": "1000000",
            }),
            patch.object(
                repo_generate, "generate_repro_test",
                return_value=(
                    "def test_total(): assert False", "mock:model"
                ),
            ),
            patch.object(
                repo_generate, "generate_patch",
                return_value=(
                    [{"path": "app/cart.py", "content": "fixed"}],
                    "mock:model",
                    "",
                ),
            ),
            patch.object(api_main.hub, "broadcast", new=AsyncMock()),
        ):
            outcome = asyncio.run(
                repo_run.run_repo_fix(
                    run_id=RUN_ID,
                    system_id=SYSTEM_ID,
                    repo_info={
                        "repo": "acme/api", "base": "main", "token": "good",
                    },
                    fingerprint=FINGERPRINT,
                    traceback_text=TRACEBACK_TEXT,
                    commit="abc123",
                    gate={"decision": "observe"},
                    http_client=fake.client(),
                    sandbox_factory=lambda _tar: box,
                    diagnose_fn=lambda *args: DIAGNOSIS,
                    org_id=ORG_COST,
                    language="python",
                )
            )
            summary = usage_summary(ORG_COST)
        self.assertEqual(outcome["status"], "PASS")
        self.assertTrue(outcome.get("pr_url"))

        events = self.store.query(org_id=ORG_COST)
        kinds = {(e.kind, e.unit) for e in events}
        self.assertIn((Kind.FIX_RUN, "run_started"), kinds)
        self.assertIn((Kind.FIX_RUN, "run_pass"), kinds)
        self.assertIn((Kind.PR, "pr_opened"), kinds)
        sandbox = [
            e for e in events if e.kind == Kind.SANDBOX_TIME
        ]
        self.assertTrue(sandbox, "expected sandbox_time events")
        self.assertGreater(
            sum(e.cost_estimate_usd for e in sandbox), 0.0
        )
        self.assertEqual(summary["fix_runs_used"], 1)
        self.assertGreater(summary["cost_used_usd"], 0.0)
        self.assertEqual(
            summary["by_language"]["python"]["fix_runs"], 1
        )

    def test_over_allowance_gets_no_runs_and_sees_why(self) -> None:
        """Gate blocks the run; the frozen reason lands in gate_decisions."""
        with patch.dict(os.environ, {
            "DATABASE_URL": FAKE_DB_URL,
            "TA_DATA_DIR": self.tmp,
            "TA_FREE_FIX_RUNS_PER_MONTH": "1",
        }):
            record_usage(
                ORG_BLOCKED, Kind.FIX_RUN, unit="run_pass",
                language="python",
            )
            gate = allowance_module.allowance(ORG_BLOCKED)
            self.assertFalse(gate.allowed_fix_run)
            self.assertTrue(
                gate.reason.startswith("free allowance reached")
            )
            profile = SystemProfile(
                system_id=SYSTEM_ID,
                name="Acme",
                kind="software",
                environment={"mode": "production"},
                status="armed",
            )
            decision = {
                "decision": "observe",
                "rule": "traceback",
                "fingerprint": FINGERPRINT,
                "window": TRACEBACK_TEXT,
                "commit": "abc123",
            }
            before = len(api_main.gate_decisions)
            with (
                # PG reads only (James's C-J3 seam); the gate, the
                # blocked record, and usage stay real.
                patch.object(
                    repo_run, "_profile_for", return_value=profile
                ),
                patch.object(
                    repo_run.github_conn, "connection_repo",
                    return_value={
                        "repo": "acme/api", "base": "main",
                        "token": "good",
                    },
                ),
            ):
                begun = asyncio.run(
                    repo_run.maybe_trigger(
                        SYSTEM_ID, [decision], "abc123",
                        org_id=ORG_BLOCKED,
                    )
                )
        self.assertEqual(begun, [])
        started = [
            e
            for e in self.store.query(org_id=ORG_BLOCKED)
            if e.kind == Kind.FIX_RUN and e.unit == "run_started"
        ]
        self.assertEqual(started, [])
        fresh = [
            d
            for d in list(api_main.gate_decisions)[before:]
            if d.get("system_id") == SYSTEM_ID
        ]
        self.assertEqual(len(fresh), 1)
        self.assertEqual(fresh[0]["decision"], "suppress")
        self.assertEqual(fresh[0]["fingerprint"], FINGERPRINT)
        self.assertIn("free allowance reached", fresh[0]["reason"])


if __name__ == "__main__":
    unittest.main()
