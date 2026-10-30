"""Phase 3 pre-tag: costs, events, allowance, alerts. No network, no DB."""

import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from core.usage.allowance import (
    AllowanceLimits,
    allowance,
    check_fix_run_rate,
    check_ingest_rate,
    load_limits,
    month_end,
    month_start,
)
from core.usage.alerts import credit_alerts, provider_spend
from core.usage.costs import cost_of_sandbox, cost_of_tokens, rate_for
from core.usage.events import (
    JsonlUsageStore,
    Kind,
    MemoryUsageStore,
    UsageEvent,
    record_fix_run,
    record_ingest,
    record_mitigation,
    record_model_call,
    record_pr,
    record_sandbox_time,
    record_snapshot,
)


def _ts(y=2026, mo=10, d=15, h=12):
    return datetime(y, mo, d, h, tzinfo=timezone.utc).timestamp()


class CostsTest(unittest.TestCase):
    def test_baseten_known_rate_math(self):
        # 1000 in @ .60/1M + 500 out @ 1.80/1M
        self.assertAlmostEqual(
            cost_of_tokens("baseten", "meta-models/muse-spark-open-1026",
                           1000, 500),
            0.0006 + 0.0009)

    def test_unknown_model_falls_back_to_provider_default(self):
        rate = rate_for("baseten", "nope/not-a-model")
        self.assertEqual(rate.model, "default")
        self.assertGreater(cost_of_tokens("baseten", "nope/x", 10**6, 0), 0)

    def test_unknown_provider_falls_back_to_generic_estimate(self):
        rate = rate_for("mystery", "mystery/model")
        self.assertEqual(rate.provider, "unknown")
        self.assertGreater(cost_of_tokens("mystery", "m", 10**6, 10**6), 0)

    def test_never_raises_on_bad_token_input(self):
        self.assertEqual(cost_of_tokens("baseten", "m", None, None), 0.0)
        self.assertEqual(cost_of_tokens("baseten", "m", "x", -5), 0.0)

    def test_env_override_replaces_provider_numbers(self):
        with patch.dict(os.environ, {"TA_COST_BASETEN_IN": "1.0",
                                     "TA_COST_BASETEN_OUT": "2.0"}):
            self.assertAlmostEqual(
                cost_of_tokens("baseten", "anything", 10**6, 10**6), 3.0)
            self.assertIn("env override",
                          rate_for("baseten", "anything").source)

    def test_bad_env_override_ignored(self):
        with patch.dict(os.environ, {"TA_COST_BASETEN_IN": "junk"}):
            rate = rate_for("baseten", "meta-models/muse-spark-open-1026")
            self.assertAlmostEqual(rate.input_usd_per_1m, 0.60)

    def test_modal_sandbox_math(self):
        # 3600 s @ $0.000046/s
        self.assertAlmostEqual(cost_of_sandbox("modal", 3600), 0.1656)

    def test_docker_and_unknown_backend_cost_zero(self):
        self.assertEqual(cost_of_sandbox("docker", 3600), 0.0)
        self.assertEqual(cost_of_sandbox("quantum", 3600), 0.0)

    def test_sandbox_env_override(self):
        with patch.dict(os.environ, {"TA_COST_MODAL_SANDBOX_S": "0.001"}):
            self.assertAlmostEqual(cost_of_sandbox("modal", 10), 0.01)

    def test_sandbox_never_raises(self):
        self.assertEqual(cost_of_sandbox("modal", None), 0.0)
        self.assertEqual(cost_of_sandbox("modal", "junk"), 0.0)
        self.assertEqual(cost_of_sandbox("modal", -3), 0.0)

    def test_rate_provenance_present(self):
        rate = rate_for("fireworks", "any-model")
        self.assertTrue(rate.source)
        self.assertTrue(rate.verified)
        est = rate_for("meta", "muse-spark-1.3")
        self.assertFalse(est.verified)


class EventsTest(unittest.TestCase):
    def setUp(self):
        self.store = MemoryUsageStore()

    def test_model_call_emits_two_events_and_returns_cost(self):
        cost = record_model_call(
            self.store, org_id="o1", system_id="s1", run_id="r1",
            language="rust", provider="baseten",
            model="meta-models/muse-spark-open-1026",
            input_tokens=1000, output_tokens=500, at=_ts())
        rows = self.store.query(org_id="o1")
        self.assertEqual(len(rows), 2)
        by_unit = {r.unit: r for r in rows}
        self.assertAlmostEqual(by_unit["tokens_in"].quantity, 1000)
        self.assertAlmostEqual(by_unit["tokens_out"].quantity, 500)
        self.assertTrue(all(r.kind == Kind.MODEL_CALL for r in rows))
        self.assertTrue(all(r.provider == "baseten" for r in rows))
        self.assertTrue(all(r.run_id == "r1" and r.language == "rust"
                            for r in rows))
        self.assertAlmostEqual(
            cost, by_unit["tokens_in"].cost_estimate_usd
            + by_unit["tokens_out"].cost_estimate_usd)
        self.assertAlmostEqual(cost, 0.0015)

    def test_sandbox_time_event(self):
        cost = record_sandbox_time(
            self.store, org_id="o1", run_id="r1", language="php",
            backend="modal", seconds=100.0, at=_ts())
        (row,) = self.store.query(org_id="o1")
        self.assertEqual(row.kind, Kind.SANDBOX_TIME)
        self.assertEqual(row.unit, "seconds")
        self.assertEqual(row.provider, "modal")
        self.assertAlmostEqual(row.quantity, 100.0)
        self.assertAlmostEqual(cost, 100 * 0.000046)
        self.assertAlmostEqual(row.cost_estimate_usd, cost)

    def test_fix_run_outcome_units(self):
        for outcome, unit in [("started", "run_started"),
                              ("pass", "run_pass"),
                              ("PASS", "run_pass"),
                              ("draft", "run_draft"),
                              ("failed", "run_failed"),
                              ("weird", "run_started")]:
            with self.subTest(outcome=outcome):
                store = MemoryUsageStore()
                record_fix_run(store, org_id="o", run_id="r",
                               language="go", outcome=outcome, at=_ts())
                (row,) = store.query()
                self.assertEqual(row.kind, Kind.FIX_RUN)
                self.assertEqual(row.unit, unit)
                self.assertEqual(row.cost_estimate_usd, 0.0)
                self.assertEqual(row.quantity, 1.0)

    def test_pr_mitigation_ingest_snapshot_shapes(self):
        record_pr(self.store, org_id="o", run_id="r", language="java",
                  action="opened", at=_ts())
        record_pr(self.store, org_id="o", run_id="r", language="java",
                  action="comment", at=_ts())
        record_pr(self.store, org_id="o", run_id="r", language="java",
                  action="bogus", at=_ts())
        record_mitigation(self.store, org_id="o", system_id="s",
                          action="rollback", at=_ts())
        record_ingest(self.store, org_id="o", system_id="s", lines=42,
                      at=_ts())
        record_snapshot(self.store, org_id="o", kind="systems", count=2,
                        at=_ts())
        record_snapshot(self.store, org_id="o", kind="devices", count=4,
                        at=_ts())
        record_snapshot(self.store, org_id="o", kind="bogus", count=9,
                        at=_ts())
        units = sorted(r.unit for r in self.store.query())
        self.assertEqual(units, ["action:rollback", "count", "count", "count",
                                 "lines", "pr_comment", "pr_comment",
                                 "pr_opened"])
        ingest = [r for r in self.store.query()
                  if r.kind == Kind.INGEST][0]
        self.assertEqual(ingest.quantity, 42)

    def test_query_filters(self):
        record_model_call(self.store, org_id="o1", provider="baseten",
                          model="m", language="rust",
                          input_tokens=1, output_tokens=0, at=_ts(d=10))
        record_model_call(self.store, org_id="o2", provider="meta",
                          model="m", language="php",
                          input_tokens=1, output_tokens=0, at=_ts(d=20))
        self.assertEqual(len(self.store.query(org_id="o1")), 2)
        self.assertEqual(len(self.store.query(provider="meta")), 2)
        self.assertEqual(len(self.store.query(language="php")), 2)
        self.assertEqual(len(self.store.query(since=_ts(d=15))), 2)
        self.assertEqual(len(self.store.query(until=_ts(d=15))), 2)
        self.assertEqual(len(self.store.query(
            kinds=[Kind.MODEL_CALL], org_id="o1", provider="baseten",
            language="rust", since=_ts(d=1), until=_ts(d=11))), 2)
        self.assertEqual(self.store.query(org_id="nobody"), [])

    def test_event_round_trip_dict(self):
        record_ingest(self.store, org_id="o", system_id="s", lines=3,
                      at=_ts())
        (row,) = self.store.query()
        back = UsageEvent.from_dict(row.to_dict())
        self.assertEqual(back, row)

    def test_from_dict_defaults(self):
        row = UsageEvent.from_dict({})
        self.assertEqual(row.org_id, "")
        self.assertEqual(row.quantity, 0.0)
        self.assertEqual(row.at, 0.0)


class JsonlStoreTest(unittest.TestCase):
    def test_round_trip_and_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sub" / "usage.jsonl"
            store = JsonlUsageStore(path)
            self.assertEqual(store.query(), [])  # missing file -> []
            record_model_call(store, org_id="o", provider="meta",
                              model="m", language="python",
                              input_tokens=10, output_tokens=5, at=_ts())
            record_ingest(store, org_id="o", system_id="s", lines=7,
                          at=_ts())
            reopened = JsonlUsageStore(path)
            rows = reopened.query(org_id="o")
            self.assertEqual(len(rows), 3)
            self.assertEqual(len(path.read_text().strip().split("\n")), 3)

    def test_corrupt_lines_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "usage.jsonl"
            path.write_text('{"org_id": "o", "kind": "ingest", "quantity": 1,'
                            ' "unit": "lines"}\nNOT JSON\n[1,2\n')
            rows = JsonlUsageStore(path).query()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].org_id, "o")

    def test_query_filters_apply(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "usage.jsonl"
            store = JsonlUsageStore(path)
            record_snapshot(store, org_id="a", kind="systems", count=1,
                            at=_ts(d=5))
            record_snapshot(store, org_id="b", kind="systems", count=2,
                            at=_ts(d=25))
            self.assertEqual(len(store.query(org_id="b")), 1)
            self.assertEqual(len(store.query(since=_ts(d=10))), 1)


class AllowanceTest(unittest.TestCase):
    def setUp(self):
        self.store = MemoryUsageStore()
        self.limits = AllowanceLimits()

    def test_fresh_org_allowed_with_full_remaining(self):
        d = allowance("o", self.store, now=_ts(), limits=self.limits)
        self.assertTrue(d.allowed)
        self.assertEqual(d.reason, "")
        self.assertEqual(d.remaining["fix_runs"], 30)
        self.assertEqual(d.remaining["cost_usd"], 25.0)
        self.assertNotIn("systems", d.used)  # no data -> check skipped

    def test_fix_run_limit_boundary(self):
        for i in range(29):
            record_fix_run(self.store, org_id="o", run_id=f"r{i}",
                           outcome="pass", at=_ts())
        d = allowance("o", self.store, now=_ts(), limits=self.limits)
        self.assertTrue(d.allowed)
        self.assertEqual(d.remaining["fix_runs"], 1)
        record_fix_run(self.store, org_id="o", run_id="r29",
                       outcome="draft", at=_ts())
        d = allowance("o", self.store, now=_ts(), limits=self.limits)
        self.assertFalse(d.allowed)
        self.assertIn("free allowance reached", d.reason)
        self.assertIn("30/30 fix runs", d.reason)

    def test_started_runs_do_not_consume_allowance(self):
        for i in range(50):
            record_fix_run(self.store, org_id="o", run_id=f"r{i}",
                           outcome="started", at=_ts())
        d = allowance("o", self.store, now=_ts(), limits=self.limits)
        self.assertTrue(d.allowed)
        self.assertEqual(d.used["fix_runs"], 0)

    def test_cost_limit_blocks(self):
        # $0.60 + 13.5M out @ $1.80/1M = $24.90: just under the $25 cap
        record_model_call(self.store, org_id="o", provider="baseten",
                          model="meta-models/muse-spark-open-1026",
                          input_tokens=10**6, output_tokens=13_500_000,
                          at=_ts())
        d = allowance("o", self.store, now=_ts(), limits=self.limits)
        self.assertTrue(d.allowed)
        record_sandbox_time(self.store, org_id="o", backend="modal",
                            seconds=3600, at=_ts())  # +$0.1656 -> over
        d = allowance("o", self.store, now=_ts(), limits=self.limits)
        self.assertFalse(d.allowed)
        self.assertIn("free allowance reached", d.reason)
        self.assertIn("estimated provider cost", d.reason)

    def test_last_month_usage_does_not_count(self):
        for i in range(40):
            record_fix_run(self.store, org_id="o", run_id=f"r{i}",
                           outcome="pass", at=_ts(mo=9, d=30))
        record_model_call(self.store, org_id="o", provider="baseten",
                          model="m", input_tokens=10**9, output_tokens=0,
                          at=_ts(mo=9, d=30))
        d = allowance("o", self.store, now=_ts(), limits=self.limits)
        self.assertTrue(d.allowed)
        self.assertEqual(d.used["fix_runs"], 0)
        self.assertEqual(d.used["cost_usd"], 0.0)

    def test_systems_devices_from_snapshots(self):
        record_snapshot(self.store, org_id="o", kind="systems", count=3,
                        at=_ts())
        d = allowance("o", self.store, now=_ts(), limits=self.limits)
        self.assertFalse(d.allowed)
        self.assertIn("3/3 systems", d.reason)
        # newer snapshot wins
        record_snapshot(self.store, org_id="o", kind="systems", count=1,
                        at=_ts(h=13))
        record_snapshot(self.store, org_id="o", kind="devices", count=5,
                        at=_ts())
        d = allowance("o", self.store, now=_ts(), limits=self.limits)
        self.assertFalse(d.allowed)
        self.assertIn("5/5 devices", d.reason)

    def test_explicit_counts_override_snapshots(self):
        record_snapshot(self.store, org_id="o", kind="systems", count=3,
                        at=_ts())
        d = allowance("o", self.store, now=_ts(), systems=1,
                      limits=self.limits)
        self.assertTrue(d.allowed)
        self.assertEqual(d.used["systems"], 1)

    def test_env_limits_apply(self):
        with patch.dict(os.environ, {"TA_FREE_FIX_RUNS_PER_MONTH": "1",
                                     "TA_FREE_MONTHLY_COST_USD": "0.5"}):
            lim = load_limits()
            self.assertEqual(lim.fix_runs_per_month, 1)
            self.assertEqual(lim.monthly_cost_usd, 0.5)
            record_fix_run(self.store, org_id="o", run_id="r",
                           outcome="pass", at=_ts())
            d = allowance("o", self.store, now=_ts())
            self.assertFalse(d.allowed)

    def test_month_bounds_and_december_rollover(self):
        start = month_start(_ts(mo=10, d=15))
        end = month_end(_ts(mo=10, d=15))
        self.assertEqual(start, _ts(mo=10, d=1, h=0))
        self.assertEqual(end, _ts(mo=11, d=1, h=0))
        self.assertEqual(month_end(_ts(mo=12, d=10)),
                         datetime(2027, 1, 1, tzinfo=timezone.utc).timestamp())


class AbuseGuardTest(unittest.TestCase):
    def setUp(self):
        self.store = MemoryUsageStore()
        self.limits = AllowanceLimits()

    def test_ingest_under_and_over(self):
        ok, _ = check_ingest_rate("o", self.store, lines=9999, now=_ts(),
                                  limits=self.limits)
        self.assertTrue(ok)
        record_ingest(self.store, org_id="o", system_id="s", lines=9999,
                      at=_ts())
        ok, reason = check_ingest_rate("o", self.store, lines=2, now=_ts(),
                                       limits=self.limits)
        self.assertFalse(ok)
        self.assertIn("ingest burst guard", reason)

    def test_ingest_window_expires(self):
        record_ingest(self.store, org_id="o", system_id="s", lines=50_000,
                      at=_ts(h=11))  # an hour ago
        ok, _ = check_ingest_rate("o", self.store, lines=1, now=_ts(),
                                  limits=self.limits)
        self.assertTrue(ok)

    def test_fix_run_burst_guard(self):
        for i in range(10):
            record_fix_run(self.store, org_id="o", run_id=f"r{i}",
                           outcome="started", at=_ts())
        ok, reason = check_fix_run_rate("o", self.store, now=_ts(),
                                        limits=self.limits)
        self.assertFalse(ok)
        self.assertIn("fix-run burst guard", reason)
        # completions don't count as starts; old starts expire
        old = MemoryUsageStore()
        record_fix_run(old, org_id="o", run_id="x", outcome="pass",
                       at=_ts())
        record_fix_run(old, org_id="o", run_id="y", outcome="started",
                       at=_ts(h=10))
        ok, _ = check_fix_run_rate("o", old, now=_ts(),
                                   limits=self.limits)
        self.assertTrue(ok)


class AlertsTest(unittest.TestCase):
    def setUp(self):
        self.store = MemoryUsageStore()

    def test_no_spend_no_alerts(self):
        self.assertEqual(credit_alerts(self.store), [])

    def test_levels_at_boundaries(self):
        with patch.dict(os.environ, {"TA_CREDIT_BASETEN_USD": "100"}):
            # baseten default rate: $0.60/1M in. $49.99 -> no alert.
            record_model_call(self.store, org_id="o", provider="baseten",
                              model="m", input_tokens=83_316_666,
                              output_tokens=0, at=_ts())
            self.assertEqual(provider_spend(self.store, "baseten"), 49.99)
            self.assertEqual(credit_alerts(self.store), [])
            record_model_call(self.store, org_id="o", provider="baseten",
                              model="m", input_tokens=16_667,
                              output_tokens=0, at=_ts())
            (a,) = credit_alerts(self.store)
            self.assertEqual((a.provider, a.level), ("baseten", 50.0))

    def test_80_and_95_levels(self):
        with patch.dict(os.environ, {"TA_CREDIT_BASETEN_USD": "10"}):
            record_model_call(self.store, org_id="o", provider="baseten",
                              model="m", input_tokens=10**8,
                              output_tokens=0, at=_ts())  # $60
            (a,) = credit_alerts(self.store)
            self.assertEqual(a.level, 95.0)
            self.assertEqual(a.spent_usd, 60.0)
            self.assertEqual(a.pct, 600.0)

    def test_modal_sandbox_spend_counts_for_modal(self):
        record_sandbox_time(self.store, org_id="o", backend="modal",
                            seconds=1_086_957, at=_ts())  # ~$50.00
        (a,) = [x for x in credit_alerts(self.store)
                if x.provider == "modal"]
        self.assertEqual(a.level, 50.0)

    def test_non_cost_kinds_add_no_spend(self):
        record_fix_run(self.store, org_id="o", run_id="r", outcome="pass",
                       at=_ts())
        record_pr(self.store, org_id="o", action="opened", at=_ts())
        record_mitigation(self.store, org_id="o", action="rollback",
                          at=_ts())
        record_ingest(self.store, org_id="o", system_id="s", lines=10**6,
                      at=_ts())
        self.assertEqual(provider_spend(self.store, "baseten"), 0.0)
        self.assertEqual(provider_spend(self.store, "modal"), 0.0)
        self.assertEqual(credit_alerts(self.store), [])

    def test_meta_spend_tracked_but_unalerted(self):
        record_model_call(self.store, org_id="o", provider="meta",
                          model="muse-spark-1.3",
                          input_tokens=10**9, output_tokens=0, at=_ts())
        self.assertGreater(provider_spend(self.store, "meta"), 0)
        self.assertEqual(
            [a for a in credit_alerts(self.store) if a.provider == "meta"],
            [])

    def test_zero_credit_skipped(self):
        with patch.dict(os.environ, {"TA_CREDIT_MODAL_USD": "0"}):
            record_sandbox_time(self.store, org_id="o", backend="modal",
                                seconds=10**9, at=_ts())
            self.assertEqual(
                [a for a in credit_alerts(self.store)
                 if a.provider == "modal"], [])

    def test_spend_sums_across_orgs(self):
        record_model_call(self.store, org_id="o1", provider="baseten",
                          model="m", input_tokens=50_000_000,
                          output_tokens=0, at=_ts())  # $30
        record_model_call(self.store, org_id="o2", provider="baseten",
                          model="m", input_tokens=50_000_000,
                          output_tokens=0, at=_ts())  # $30
        self.assertEqual(provider_spend(self.store, "baseten"), 60.0)
        (a,) = credit_alerts(self.store)
        self.assertEqual((a.provider, a.level), ("baseten", 50.0))


if __name__ == "__main__":
    unittest.main()
