"""Shop watcher pins shared rules, grab flow, and trigger events (Sim 2)."""

import os
import tempfile
import unittest
from unittest.mock import patch

import httpx

from core.watch.log_watcher import run
from core.watch.rules import (
    RetryClusterTracker,
    extract_resource,
    fingerprint_for,
    match_error,
)
from core.watch.watcher import LogTail, build_window, publish_sim_event, send_run, should_send


class ErrorRuleTests(unittest.TestCase):
    def test_deadlock_error_traceback_fire(self) -> None:
        hit = match_error("Deadlock detected while acquiring lock on inventory_items")
        self.assertEqual((hit.rule, hit.level), ("deadlock", "error"))
        hit = match_error("2026-10-27 ERROR order=abc123 service=shop")
        self.assertEqual((hit.rule, hit.level), ("error", "error"))
        self.assertEqual(hit.resource, "abc123")
        hit = match_error("Traceback (most recent call last):")
        self.assertEqual((hit.rule, hit.level), ("traceback", "error"))

    def test_clean_lines_fire_nothing(self) -> None:
        self.assertIsNone(match_error("request completed in 12ms"))
        self.assertIsNone(match_error("INFO service=shop starting"))

    def test_resource_prefers_items(self) -> None:
        self.assertEqual(
            extract_resource("WARNING retry=1 items=brake-pad,axle"), "brake-pad,axle"
        )
        self.assertEqual(extract_resource("nothing here"), "")


class RetryClusterTests(unittest.TestCase):
    def test_two_same_item_retries_fire_once(self) -> None:
        tracker = RetryClusterTracker()
        line = "WARNING retry=1 items=brake-pad,axle"
        self.assertIsNone(tracker.observe(line, 100.0))
        hit = tracker.observe(line, 110.0)
        self.assertIsNotNone(hit)
        self.assertEqual((hit.rule, hit.level), ("retry-cluster", "warning"))
        self.assertEqual(hit.resource, "brake-pad,axle")
        self.assertIsNone(tracker.observe(line, 115.0))  # fires once per cluster

    def test_different_items_stay_quiet(self) -> None:
        tracker = RetryClusterTracker()
        self.assertIsNone(
            tracker.observe("WARNING retry=1 items=axle,chain", 100.0)
        )
        self.assertIsNone(
            tracker.observe("WARNING retry=2 items=brake-pad,gasket", 110.0)
        )

    def test_expired_retries_stay_quiet(self) -> None:
        tracker = RetryClusterTracker()
        line = "WARNING retry=1 items=axle"
        self.assertIsNone(tracker.observe(line, 100.0))
        self.assertIsNone(tracker.observe(line, 200.0))

    def test_non_retry_lines_ignored(self) -> None:
        tracker = RetryClusterTracker()
        self.assertIsNone(tracker.observe("all quiet", 100.0))


class FingerprintTests(unittest.TestCase):
    def test_stable_across_numbers(self) -> None:
        first = fingerprint_for("error", "", "ERROR order=abc tx-11 12ms")
        second = fingerprint_for("error", "", "ERROR order=abc tx-99 99ms")
        self.assertEqual(first, second)

    def test_differs_by_rule_and_resource(self) -> None:
        base = fingerprint_for("deadlock", "axle", "x")
        self.assertNotEqual(base, fingerprint_for("error", "axle", "x"))
        self.assertNotEqual(base, fingerprint_for("deadlock", "chain", "x"))


class WindowDebounceTests(unittest.TestCase):
    def test_window_order(self) -> None:
        self.assertEqual(build_window(["b"], "T", ["a"]), "b\nT\na")

    def test_debounce_suppresses_repeat(self) -> None:
        last_sent = {}
        self.assertTrue(should_send("fp", 0.0, last_sent, 600.0))
        self.assertFalse(should_send("fp", 60.0, last_sent, 600.0))


class RotationTests(unittest.TestCase):
    def test_follows_rotated_file(self) -> None:
        handle, path = tempfile.mkstemp(prefix="logwatch")
        self.addCleanup(os.unlink, path)
        rotated = path + ".1"
        self.addCleanup(lambda: os.path.exists(rotated) and os.unlink(rotated))
        with os.fdopen(handle, "w") as f:
            f.write("one\n")
        tail = LogTail(path, from_start=True)
        try:
            self.assertEqual(tail.read_new(), ["one"])
            os.rename(path, rotated)
            with open(path, "w") as f:
                f.write("two\n")
            self.assertEqual(tail.read_new(), ["two"])
        finally:
            tail.close()


class SendTests(unittest.TestCase):
    def test_send_run_includes_target(self) -> None:
        seen = {}

        def fake_post(url, json=None, timeout=None):
            seen["url"] = url
            seen["body"] = json
            return httpx.Response(200, json={"status": "PASS"})

        with patch("httpx.post", side_effect=fake_post):
            send_run("http://api:8001", "boom", target="inventory")
        self.assertEqual(seen["url"], "http://api:8001/api/run")
        self.assertEqual(
            seen["body"],
            {"log_text": "boom", "source": "watcher", "target": "inventory"},
        )

    def test_publish_sim_event(self) -> None:
        seen = {}

        def fake_post(url, json=None, timeout=None):
            seen["url"] = url
            seen["body"] = json
            return httpx.Response(200, json=json)

        with patch("httpx.post", side_effect=fake_post):
            publish_sim_event("http://api:8001", "watcher_trigger", {"rule": "deadlock"})
        self.assertEqual(seen["url"], "http://api:8001/api/sim/events")
        self.assertEqual(seen["body"]["kind"], "watcher_trigger")

    def test_publish_failure_raises(self) -> None:
        with patch("httpx.post", side_effect=httpx.ConnectError("down")):
            with self.assertRaises(RuntimeError):
                publish_sim_event("http://api:8001", "watcher_trigger", {})


class GrabFlowTests(unittest.TestCase):
    def test_deadlock_line_sends_run_and_trigger(self) -> None:
        handle, path = tempfile.mkstemp(prefix="logwatch")
        with os.fdopen(handle, "w") as f:
            f.write("INFO starting\nDeadlock detected on inventory_items\n")
        self.addCleanup(os.unlink, path)
        with patch("core.watch.log_watcher.send_run") as send, patch(
            "core.watch.log_watcher.publish_sim_event"
        ) as publish:
            run(path, "http://api:8001", from_start=True, max_runs=1,
                poll_s=0.01, after_timeout_s=0.0)
        _, kwargs = send.call_args
        self.assertEqual(kwargs["source"], "watcher")
        self.assertEqual(kwargs["target"], "inventory")
        self.assertIn("Deadlock detected", send.call_args.args[1])
        trigger_args = publish.call_args.args
        self.assertEqual(trigger_args[1], "watcher_trigger")
        payload = trigger_args[2]
        self.assertEqual(payload["rule"], "deadlock")
        self.assertEqual(len(payload["matched_lines"]), 1)


if __name__ == "__main__":
    unittest.main()
