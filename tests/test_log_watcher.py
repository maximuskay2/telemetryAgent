"""Shop watcher pins shared rules, grab flow, and trigger events (Sim 2)."""

import os
import tempfile
import unittest
from unittest.mock import patch

import httpx

from core.watch.log_watcher import classify_forward, run
from core.watch.rules import (
    RetryClusterTracker,
    extract_resource,
    fingerprint_for,
    match_error,
)
from core.watch.watcher import (
    LogForwarder,
    LogTail,
    build_window,
    post_candidate,
    post_log,
    publish_sim_event,
    send_run,
    should_send,
)


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

    def test_post_candidate_shape(self) -> None:
        with patch("httpx.post") as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = {"decision": {}}
            post_candidate(
                "http://api:8001/", system_id="shop", rule="deadlock",
                fingerprint="fp1", signature="Deadlock!",
                window="ctx\nDeadlock!",
            )
        _, kwargs = post.call_args
        self.assertEqual(
            post.call_args.args[0],
            "http://api:8001/api/incidents/candidate",
        )
        body = kwargs["json"]
        self.assertEqual(
            (body["system_id"], body["rule"], body["fingerprint"],
             body["signature"], body["source"]),
            ("shop", "deadlock", "fp1", "Deadlock!", "log"),
        )
        self.assertIn("Deadlock!", body["window"])

    def test_post_candidate_failure_raises(self) -> None:
        with patch("httpx.post", side_effect=httpx.ConnectError("down")):
            with self.assertRaises(RuntimeError):
                post_candidate("http://api:8001", "shop", "deadlock")


class GrabFlowTests(unittest.TestCase):
    def test_deadlock_line_posts_candidate_and_trigger(self) -> None:
        handle, path = tempfile.mkstemp(prefix="logwatch")
        with os.fdopen(handle, "w") as f:
            f.write("INFO starting\nDeadlock detected on inventory_items\n")
        self.addCleanup(os.unlink, path)
        with patch("core.watch.log_watcher.post_candidate") as post, patch(
            "core.watch.log_watcher.publish_sim_event"
        ) as publish:
            run(path, "http://api:8001", from_start=True, max_runs=1,
                poll_s=0.01, after_timeout_s=0.0, forward=False)
        _, kwargs = post.call_args
        self.assertEqual(post.call_args.args[0], "http://api:8001")
        self.assertEqual(kwargs["system_id"], "shop")
        self.assertEqual(kwargs["rule"], "deadlock")
        self.assertTrue(kwargs["fingerprint"])
        self.assertIn("Deadlock detected", kwargs["signature"])
        self.assertIn("Deadlock detected", kwargs["window"])
        trigger_args = publish.call_args.args
        self.assertEqual(trigger_args[1], "watcher_trigger")
        payload = trigger_args[2]
        self.assertEqual(payload["rule"], "deadlock")
        self.assertEqual(len(payload["matched_lines"]), 1)
        self.assertIn("resource", payload)

    def test_quiet_period_suppresses_backlog_runs(self) -> None:
        handle, path = tempfile.mkstemp(prefix="logwatch")
        with os.fdopen(handle, "w") as f:
            f.write(
                "ERROR order=a1 service=shop items=axle,chain\n"
                "ERROR order=b2 service=shop items=piston,muffler\n"
            )
        self.addCleanup(os.unlink, path)

        class Stop(Exception):
            pass

        with patch("core.watch.log_watcher.post_candidate") as post, patch(
            "core.watch.log_watcher.publish_sim_event"
        ), patch("core.watch.log_watcher.time.sleep", side_effect=Stop):
            with self.assertRaises(Stop):
                run(path, "http://api:8001", from_start=True, poll_s=0.01,
                    after=0, after_timeout_s=0.0, forward=False, quiet_s=60.0)
        self.assertEqual(post.call_count, 1)

    def test_suppressed_candidate_sets_no_quiet(self) -> None:
        handle, path = tempfile.mkstemp(prefix="logwatch")
        with os.fdopen(handle, "w") as f:
            f.write(
                "ERROR order=a1 service=shop items=axle,chain\n"
                "ERROR order=b2 service=shop items=piston,muffler\n"
                "ERROR order=c3 service=shop items=axle,shock\n"
            )
        self.addCleanup(os.unlink, path)

        class Stop(Exception):
            pass

        suppress = {"decision": {"decision": "suppress"}, "run_id": None}
        act = {"decision": {"decision": "act"}, "run_id": "abc123"}
        with patch(
            "core.watch.log_watcher.post_candidate",
            side_effect=[suppress, act, act],
        ) as post, patch(
            "core.watch.log_watcher.publish_sim_event"
        ), patch("core.watch.log_watcher.time.sleep", side_effect=Stop):
            with self.assertRaises(Stop):
                run(path, "http://api:8001", from_start=True, poll_s=0.01,
                    after=0, after_timeout_s=0.0, forward=False, quiet_s=60.0)
        # First suppresses (no quiet), second acts (quiet), third is quiet.
        self.assertEqual(post.call_count, 2)

    def test_failed_post_sets_quiet(self) -> None:
        handle, path = tempfile.mkstemp(prefix="logwatch")
        with os.fdopen(handle, "w") as f:
            f.write(
                "ERROR order=a1 service=shop items=axle,chain\n"
                "ERROR order=b2 service=shop items=piston,muffler\n"
            )
        self.addCleanup(os.unlink, path)

        class Stop(Exception):
            pass

        with patch(
            "core.watch.log_watcher.post_candidate",
            side_effect=RuntimeError("timed out, run may be going"),
        ) as post, patch(
            "core.watch.log_watcher.publish_sim_event"
        ), patch("core.watch.log_watcher.time.sleep", side_effect=Stop):
            with self.assertRaises(Stop):
                run(path, "http://api:8001", from_start=True, poll_s=0.01,
                    after=0, after_timeout_s=0.0, forward=False, quiet_s=60.0)
        # Unknown outcome: assume a run started, don't pile up.
        self.assertEqual(post.call_count, 1)


class ClassifyForwardTests(unittest.TestCase):
    def test_levels(self) -> None:
        self.assertEqual(
            classify_forward("2026-10-27T12:00:00Z Deadlock detected on t"), "ERROR"
        )
        self.assertEqual(
            classify_forward("ERROR order=abc service=shop"), "ERROR"
        )
        self.assertEqual(
            classify_forward("WARNING retry=1 order=abc items=axle"), "WARNING"
        )
        self.assertEqual(classify_forward("retry=2 items=axle"), "WARNING")
        self.assertEqual(
            classify_forward("Traceback (most recent call last)"), "ERROR"
        )
        self.assertEqual(
            classify_forward("FATAL process died"), "CRITICAL"
        )

    def test_clean_lines_stay_out(self) -> None:
        self.assertIsNone(classify_forward("INFO starting"))
        self.assertIsNone(classify_forward("order ok in 3ms"))
        self.assertIsNone(classify_forward(""))


class FakeClock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


class ForwarderTests(unittest.TestCase):
    def _forwarder(self, clock, sent, **kwargs):
        kwargs.setdefault("rate_per_s", 5.0)
        return LogForwarder(
            "http://api:8001", clock=clock,
            sender=lambda message, level: sent.append((level, message)),
            **kwargs,
        )

    def test_under_rate_sends_all(self) -> None:
        clock, sent = FakeClock(), []
        forward = self._forwarder(clock, sent)
        forward.push("w1", "WARNING")
        forward.push("e1", "ERROR")
        self.assertEqual(forward.flush(), 2)
        self.assertEqual(sent, [("ERROR", "e1"), ("WARNING", "w1")])

    def test_caps_at_five_per_second_then_refills(self) -> None:
        clock, sent = FakeClock(), []
        forward = self._forwarder(clock, sent)
        for i in range(8):
            forward.push(f"w{i}", "WARNING")
        self.assertEqual(forward.flush(), 5)
        self.assertEqual(forward.flush(), 0)
        clock.advance(1.0)
        self.assertEqual(forward.flush(), 3)
        self.assertEqual(len(sent), 8)

    def test_errors_jump_the_queue(self) -> None:
        clock, sent = FakeClock(), []
        forward = self._forwarder(clock, sent, rate_per_s=2.0)
        forward.push("w1", "WARNING")
        forward.push("w2", "WARNING")
        forward.push("e1", "ERROR")
        forward.flush()
        self.assertEqual([line for _, line in sent], ["e1", "w1"])

    def test_full_buffer_evicts_oldest_warnings_first(self) -> None:
        clock, sent = FakeClock(), []
        forward = self._forwarder(clock, sent, rate_per_s=100.0, max_buffer=3)
        forward.push("w1", "WARNING")
        forward.push("e1", "ERROR")
        forward.push("w2", "WARNING")
        forward.push("w3", "WARNING")
        self.assertEqual(forward.dropped, 1)
        forward.flush()
        self.assertEqual(
            [line for _, line in sent], ["e1", "w2", "w3"]
        )

    def test_sender_failure_drops_without_raising(self) -> None:
        clock = FakeClock()

        def boom(message, level):
            raise RuntimeError("down")

        forward = LogForwarder(
            "http://api:8001", clock=clock, sender=boom
        )
        forward.push("e1", "ERROR")
        self.assertEqual(forward.flush(), 0)
        self.assertEqual(forward.dropped, 1)

    def test_post_log_body(self) -> None:
        seen = {}

        def fake_post(url, json=None, timeout=None):
            seen["url"] = url
            seen["body"] = json
            return httpx.Response(200, json={"id": "1"})

        with patch("httpx.post", side_effect=fake_post):
            post_log("http://api:8001", "boom", source="shop", level="ERROR")
        self.assertEqual(seen["url"], "http://api:8001/api/logs")
        self.assertEqual(
            seen["body"],
            {"message": "boom", "source": "shop", "level": "ERROR"},
        )


class ForwardFlowTests(unittest.TestCase):
    def test_run_forwards_warnings_and_errors_only(self) -> None:
        handle, path = tempfile.mkstemp(prefix="logwatch-fwd")
        with os.fdopen(handle, "w") as f:
            f.write(
                "WARNING retry=1 order=a1 items=axle (lock wait timeout)\n"
                "INFO shop open\n"
                "ERROR order=z9 service=shop\n"
                "Deadlock detected order=z8 while acquiring lock\n"
            )
        self.addCleanup(os.unlink, path)
        with patch("core.watch.log_watcher.post_candidate"), patch(
            "core.watch.log_watcher.publish_sim_event"
        ), patch("core.watch.log_watcher.post_log") as posted:
            run(path, "http://api:8001", from_start=True, max_runs=2,
                poll_s=0.01, after_timeout_s=0.0)
        messages = [call.args[1] for call in posted.call_args_list]
        self.assertEqual(len(messages), 3)
        self.assertTrue(any("retry=1" in m for m in messages))
        self.assertTrue(any("Deadlock detected" in m for m in messages))
        self.assertFalse(any("shop open" in m for m in messages))

    def test_no_forward_sends_nothing(self) -> None:
        handle, path = tempfile.mkstemp(prefix="logwatch-nofwd")
        with os.fdopen(handle, "w") as f:
            f.write(
                "WARNING retry=1 order=a1 items=axle\n"
                "Deadlock detected while acquiring lock\n"
            )
        self.addCleanup(os.unlink, path)
        with patch("core.watch.log_watcher.post_candidate"), patch(
            "core.watch.log_watcher.publish_sim_event"
        ), patch("core.watch.log_watcher.post_log") as posted:
            run(path, "http://api:8001", from_start=True, max_runs=1,
                poll_s=0.01, after_timeout_s=0.0, forward=False)
        self.assertEqual(posted.call_count, 0)


if __name__ == "__main__":
    unittest.main()
