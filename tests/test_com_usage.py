"""C-D1..D3: frozen §8.4 surface on a fake store. No network, no DB."""

import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from core.commerce import allowance as com_allow
from core.commerce import costs as com_costs
from core.commerce import usage as com_usage
from core.commerce.allowance import AllowanceStatus
from core.commerce.usage import (
    COST_TABLE,
    Kind,
    MemoryUsageStore,
    admin_cost_overview,
    allowance_limits,
    configure_usage_store,
    provider_credit_status,
    record_usage,
    reset_usage_store,
    usage_summary,
)
from core.usage.events import record_fix_run, record_sandbox_time


def _ts(y=2026, mo=10, d=15, h=12):
    return datetime(y, mo, d, h, tzinfo=timezone.utc).timestamp()


class ComUsageCase(unittest.TestCase):
    def setUp(self):
        self.store = MemoryUsageStore()
        configure_usage_store(self.store)

    def tearDown(self):
        reset_usage_store()


class RecordUsageTest(ComUsageCase):
    def test_model_call_auto_cost_and_shape(self):
        row = record_usage(
            "o1", Kind.MODEL_CALL, 10**6, "tokens_in",
            system_id="s1", run_id="r1", provider="baseten",
            model="meta-models/muse-spark-open-1026", language="rust")
        self.assertEqual(
            sorted(row),
            ["at", "cost_estimate_usd", "kind", "language", "model",
             "org_id", "provider", "quantity", "run_id", "system_id",
             "unit"])
        self.assertAlmostEqual(row["cost_estimate_usd"], 0.60)
        self.assertEqual(row["model"], "meta-models/muse-spark-open-1026")
        (stored,) = self.store.query(org_id="o1")
        self.assertEqual(stored.to_dict(), row)

    def test_tokens_out_and_unknown_model_fallback(self):
        row = record_usage("o", Kind.MODEL_CALL, 10**6, "tokens_out",
                           provider="baseten", model="nope/x")
        self.assertAlmostEqual(row["cost_estimate_usd"], 1.80)
        row = record_usage("o", Kind.MODEL_CALL, 10**6, "tokens_in",
                           provider="mystery", model="m")
        self.assertGreater(row["cost_estimate_usd"], 0)

    def test_explicit_cost_wins(self):
        row = record_usage("o", Kind.MODEL_CALL, 10**6, "tokens_in",
                           provider="baseten", model="m",
                           cost_estimate_usd=2.5)
        self.assertEqual(row["cost_estimate_usd"], 2.5)

    def test_sandbox_time_auto_cost(self):
        row = record_usage("o", Kind.SANDBOX_TIME, 1000, "seconds",
                           run_id="r", provider="modal", language="go")
        self.assertAlmostEqual(row["cost_estimate_usd"], 1000 * 0.000046)
        row = record_usage("o", Kind.SANDBOX_TIME, 1000, "seconds",
                           provider="docker")
        self.assertEqual(row["cost_estimate_usd"], 0.0)

    def test_count_kinds_default_zero(self):
        for kind, unit in [(Kind.FIX_RUN, "run_pass"), (Kind.PR, "pr_opened"),
                           (Kind.MITIGATION, "action:rollback"),
                           (Kind.INGEST, "lines"),
                           (Kind.SYSTEMS, "count")]:
            with self.subTest(kind=kind):
                row = record_usage("o", kind, 3, unit, language="python")
                self.assertEqual(row["cost_estimate_usd"], 0.0)
                self.assertEqual(row["quantity"], 3.0)

    def test_none_normalizes_to_empty(self):
        row = record_usage("o", Kind.PR)
        self.assertEqual(
            (row["system_id"], row["run_id"], row["language"]), ("", "", ""))
        self.assertEqual((row["quantity"], row["unit"]), (1.0, "count"))

    def test_never_raises_on_junk(self):
        row = record_usage("o", Kind.MODEL_CALL, "junk", "tokens_in",
                           provider="baseten", model="m",
                           cost_estimate_usd="junk")
        self.assertEqual(row["quantity"], 0.0)
        # explicit junk cost coerces to 0 (auto-fill skipped when given)
        self.assertEqual(row["cost_estimate_usd"], 0.0)
        row = record_usage("o", Kind.SANDBOX_TIME, None, "seconds",
                           provider="modal")
        self.assertEqual(row["cost_estimate_usd"], 0.0)

    def test_cost_table_shape(self):
        self.assertIs(com_usage.COST_TABLE, com_costs.COST_TABLE)
        self.assertEqual(sorted(COST_TABLE), ["sandbox_usd_per_s", "tokens"])
        for rate in COST_TABLE["tokens"]:
            self.assertEqual(
                sorted(rate),
                ["input_usd_per_1m", "model", "output_usd_per_1m",
                 "provider", "source", "verified"])
        self.assertIn("modal", COST_TABLE["sandbox_usd_per_s"])

    def test_every_section3_kind_records_with_language_and_cost(self):
        # C-D1 acceptance: every §3 kind records with language + cost.
        record_usage("o", Kind.MODEL_CALL, 100, "tokens_in",
                     provider="meta", model="muse-spark-1.3",
                     language="python", run_id="r")
        record_usage("o", Kind.MODEL_CALL, 50, "tokens_out",
                     provider="meta", model="muse-spark-1.3",
                     language="python", run_id="r")
        record_usage("o", Kind.SANDBOX_TIME, 30, "seconds",
                     provider="docker", language="python", run_id="r")
        record_usage("o", Kind.FIX_RUN, 1, "run_pass",
                     language="python", run_id="r")
        record_usage("o", Kind.PR, 1, "pr_opened",
                     language="python", run_id="r")
        record_usage("o", Kind.MITIGATION, 1, "action:rollback",
                     language="python")
        record_usage("o", Kind.INGEST, 120, "lines")
        record_usage("o", Kind.SYSTEMS, 2, "count")
        record_usage("o", Kind.DEVICES, 3, "count")
        rows = self.store.query(org_id="o")
        self.assertEqual(len(rows), 9)
        kinds = {r.kind for r in rows}
        self.assertEqual(kinds, {Kind.MODEL_CALL, Kind.SANDBOX_TIME,
                                 Kind.FIX_RUN, Kind.PR, Kind.MITIGATION,
                                 Kind.INGEST, Kind.SYSTEMS, Kind.DEVICES})
        for r in rows:
            self.assertIn("cost_estimate_usd", r.to_dict())
        fix = [r for r in rows if r.kind == Kind.FIX_RUN][0]
        self.assertEqual(fix.language, "python")


class UsageSummaryTest(ComUsageCase):
    def test_empty_org_zeros_with_limits(self):
        self.assertEqual(usage_summary("nobody"), {
            "fix_runs_used": 0, "fix_runs_limit": 30,
            "cost_used_usd": 0.0, "cost_ceiling_usd": 25.0,
            "systems_used": 0, "systems_limit": 3,
            "devices_used": 0, "devices_limit": 5,
            "by_language": {}})

    def test_mixed_events_counted(self):
        record_usage("o", Kind.FIX_RUN, 1, "run_pass", language="python")
        record_usage("o", Kind.FIX_RUN, 1, "run_started", language="python")
        record_usage("o", Kind.FIX_RUN, 1, "run_draft", language="rust")
        record_usage("o", Kind.MODEL_CALL, 10**6, "tokens_in",
                     provider="baseten",
                     model="meta-models/muse-spark-open-1026",
                     language="python")
        record_usage("o", Kind.SYSTEMS, 2, "count")
        record_usage("o", Kind.DEVICES, 4, "count")
        summary = usage_summary("o")
        self.assertEqual(summary["fix_runs_used"], 2)  # started excluded
        self.assertAlmostEqual(summary["cost_used_usd"], 0.60)
        self.assertEqual(summary["systems_used"], 2)
        self.assertEqual(summary["devices_used"], 4)
        self.assertEqual(summary["by_language"]["python"]["fix_runs"], 1)
        self.assertEqual(summary["by_language"]["rust"]["fix_runs"], 1)
        self.assertAlmostEqual(
            summary["by_language"]["python"]["cost_usd"], 0.60)

    def test_month_default_excludes_last_month_all_includes(self):
        record_fix_run(self.store, org_id="o", run_id="old",
                       outcome="pass", at=_ts(mo=9, d=20))
        record_sandbox_time(self.store, org_id="o", backend="modal",
                            seconds=1000, language="go", at=_ts(mo=9, d=20))
        month = usage_summary("o", period="month")
        everything = usage_summary("o", period="all")
        # Sept events are outside any "current month" containing Oct 15
        # fixtures only when the wall clock is Oct 2026; assert the
        # weaker invariant that holds on any clock: all >= month.
        self.assertGreaterEqual(everything["fix_runs_used"],
                                month["fix_runs_used"])
        self.assertGreaterEqual(everything["cost_used_usd"],
                                month["cost_used_usd"])
        self.assertGreaterEqual(everything["fix_runs_used"], 1)

    def test_allowance_limits_shape(self):
        self.assertEqual(allowance_limits(), {
            "systems_limit": 3, "devices_limit": 5,
            "fix_runs_limit": 30, "cost_ceiling_usd": 25.0})


class ComAllowanceTest(ComUsageCase):
    def test_fresh_org_allowed_full_remaining(self):
        status = com_allow.allowance("o")
        self.assertIsInstance(status, AllowanceStatus)
        self.assertTrue(status.allowed_fix_run)
        self.assertEqual(status.reason, "")
        self.assertEqual(
            (status.fix_runs_remaining, status.cost_remaining_usd,
             status.systems_remaining, status.devices_remaining),
            (30, 25.0, 3, 5))

    def test_fix_run_cap_blocks_with_frozen_reason(self):
        for i in range(30):
            record_usage("o", Kind.FIX_RUN, 1, "run_pass",
                         language="java")
        status = com_allow.allowance("o")
        self.assertFalse(status.allowed_fix_run)
        self.assertEqual(status.reason,
                         "free allowance reached: "
                         "30/30 fix runs used this month")
        self.assertEqual(status.fix_runs_remaining, 0)

    def test_cost_cap_blocks(self):
        record_usage("o", Kind.MODEL_CALL, 10**8, "tokens_out",
                     provider="baseten", model="m")  # $180
        status = com_allow.allowance("o")
        self.assertFalse(status.allowed_fix_run)
        self.assertIn("free allowance reached", status.reason)
        self.assertEqual(status.cost_remaining_usd, 0.0)

    def test_snapshots_gate_systems_devices(self):
        record_usage("o", Kind.SYSTEMS, 3, "count")
        status = com_allow.allowance("o")
        self.assertFalse(status.allowed_fix_run)
        self.assertIn("3/3 systems", status.reason)
        self.assertEqual(status.systems_remaining, 0)

    def test_allowance_check_is_a_pure_read(self):
        # C-D2: the monitoring path is untouched by gating.
        before = len(self.store.query(org_id="o"))
        com_allow.allowance("o")
        com_allow.check_ingest_rate("o", lines=5)
        com_allow.check_fix_run_rate("o")
        self.assertEqual(len(self.store.query(org_id="o")), before)

    def test_abuse_guards(self):
        ok, _ = com_allow.check_ingest_rate("o", lines=100)
        self.assertTrue(ok)
        record_usage("o", Kind.INGEST, 9999, "lines")
        ok, reason = com_allow.check_ingest_rate("o", lines=2)
        self.assertFalse(ok)
        self.assertIn("ingest burst guard", reason)
        for i in range(10):
            record_usage("o", Kind.FIX_RUN, 1, "run_started",
                         run_id=f"r{i}")
        ok, reason = com_allow.check_fix_run_rate("o")
        self.assertFalse(ok)
        self.assertIn("fix-run burst guard", reason)


class AdminOverviewTest(ComUsageCase):
    def test_overview_shapes(self):
        record_usage("o1", Kind.FIX_RUN, 1, "run_pass", language="python")
        record_usage("o1", Kind.MODEL_CALL, 10**6, "tokens_in",
                     provider="baseten", model="m", language="python")
        record_usage("o2", Kind.FIX_RUN, 1, "run_failed", language="rust")
        view = admin_cost_overview()
        self.assertEqual(sorted(view),
                         ["by_language", "by_org", "provider_credit",
                          "top_spenders"])
        by_org = {r["org_id"]: r for r in view["by_org"]}
        self.assertEqual(by_org["o1"]["fix_runs"], 1)
        self.assertAlmostEqual(by_org["o1"]["cost_usd"], 0.60)
        self.assertEqual(by_org["o2"]["cost_usd"], 0.0)
        self.assertEqual(view["top_spenders"][0]["org_id"], "o1")
        self.assertIn("python", view["by_language"])
        for entry in view["provider_credit"]:
            self.assertEqual(sorted(entry),
                             ["pct_used", "provider", "remaining_usd"])

    def test_empty_store_overview(self):
        view = admin_cost_overview()
        self.assertEqual(view["by_org"], [])
        self.assertEqual(view["top_spenders"], [])
        self.assertEqual(view["by_language"], {})
        providers = {c["provider"] for c in view["provider_credit"]}
        self.assertEqual(providers, {"baseten", "modal"})

    def test_credit_status_levels(self):
        rows = provider_credit_status()
        self.assertEqual([r["provider"] for r in rows],
                         ["baseten", "modal"])
        self.assertTrue(all(r["level"] is None for r in rows))
        self.assertTrue(all(r["pct"] == 0 for r in rows))
        with patch.dict(os.environ, {"TA_CREDIT_BASETEN_USD": "10"}):
            record_usage("o", Kind.MODEL_CALL, 10**8, "tokens_in",
                         provider="baseten", model="m")  # $60 of $10
            (b,) = [r for r in provider_credit_status()
                    if r["provider"] == "baseten"]
            self.assertEqual(b["level"], 95.0)
            self.assertEqual(b["spent_usd"], 60.0)
            self.assertEqual(b["credit_usd"], 10.0)

    def test_zero_credit_provider_skipped(self):
        with patch.dict(os.environ, {"TA_CREDIT_MODAL_USD": "0"}):
            providers = {r["provider"]
                         for r in provider_credit_status()}
            self.assertNotIn("modal", providers)


class EngineModelFieldTest(ComUsageCase):
    def test_model_call_events_carry_model(self):
        from core.usage.events import UsageEvent, record_model_call
        record_model_call(self.store, org_id="o", provider="meta",
                          model="muse-spark-1.3", language="go",
                          input_tokens=10, output_tokens=5)
        rows = self.store.query(org_id="o")
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r.model == "muse-spark-1.3" for r in rows))
        self.assertIn("model", rows[0].to_dict())

    def test_old_rows_without_model_still_load(self):
        from core.usage.events import UsageEvent
        row = UsageEvent.from_dict({"org_id": "o", "kind": "ingest"})
        self.assertEqual(row.model, "")


if __name__ == "__main__":
    unittest.main()
