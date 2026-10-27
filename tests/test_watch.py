"""Watcher pins trigger levels, windows, debounce, tailing, and rotation."""

import os
import tempfile
import unittest
from unittest.mock import patch

import httpx

from core.watch.watcher import (
    LogTail,
    build_window,
    fingerprint,
    match_line,
    send_run,
    should_send,
)


class MatchTests(unittest.TestCase):
    def test_warning_signals(self) -> None:
        trigger = match_line("2026-10-26 WARNING retry=1 transaction=tx-1 backoff_ms=250")
        self.assertEqual((trigger.name, trigger.level), ("retry", "warning"))
        trigger = match_line("lock wait timeout exceeded; try restarting transaction")
        self.assertEqual((trigger.name, trigger.level), ("lock_timeout", "warning"))

    def test_error_signals(self) -> None:
        trigger = match_line("ERROR transaction=tx-8841 service=orders")
        self.assertEqual(trigger.level, "error")
        trigger = match_line("Deadlock detected while acquiring lock on inventory_items")
        self.assertEqual((trigger.name, trigger.level), ("deadlock", "error"))
        trigger = match_line("Traceback (most recent call last):")
        self.assertEqual((trigger.name, trigger.level), ("traceback", "error"))

    def test_crash_signals(self) -> None:
        trigger = match_line("process exited with code 137")
        self.assertEqual((trigger.name, trigger.level), ("crash", "crash"))
        trigger = match_line("health check down for service orders")
        self.assertEqual(trigger.level, "crash")

    def test_clean_lines_match_nothing(self) -> None:
        self.assertIsNone(match_line("request completed in 12ms"))
        self.assertIsNone(match_line("connected to inventory_items"))
        self.assertIsNone(match_line(""))


class FingerprintTests(unittest.TestCase):
    def test_numbers_normalized(self) -> None:
        first = fingerprint("retry", "WARNING retry=1 transaction=tx-8841")
        second = fingerprint("retry", "WARNING retry=7 transaction=tx-9902")
        self.assertEqual(first, second)

    def test_distinct_errors_differ(self) -> None:
        self.assertNotEqual(
            fingerprint("deadlock", "Deadlock on inventory_items"),
            fingerprint("deadlock", "Deadlock on payments_ledger"),
        )
        self.assertNotEqual(
            fingerprint("retry", "WARNING retry=1"),
            fingerprint("deadlock", "WARNING retry=1"),
        )


class DebounceTests(unittest.TestCase):
    def test_repeat_within_window_suppressed(self) -> None:
        last_sent = {}
        self.assertTrue(should_send("fp", 100.0, last_sent, 600.0))
        self.assertFalse(should_send("fp", 200.0, last_sent, 600.0))
        self.assertTrue(should_send("fp", 700.0, last_sent, 600.0))

    def test_fingerprints_independent(self) -> None:
        last_sent = {}
        self.assertTrue(should_send("a", 100.0, last_sent, 600.0))
        self.assertTrue(should_send("b", 100.0, last_sent, 600.0))


class WindowTests(unittest.TestCase):
    def test_window_order_and_cap(self) -> None:
        text = build_window(["b1", "b2"], "TRIGGER", ["a1"])
        self.assertEqual(text, "b1\nb2\nTRIGGER\na1")

    def test_oversized_window_truncated_to_limit(self) -> None:
        text = build_window(["x" * 19000], "TRIGGER", ["y" * 19000])
        self.assertLessEqual(len(text), 20000)
        self.assertTrue(text.endswith("y" * 19000))


class TailTests(unittest.TestCase):
    def _tempfile(self, content=""):
        handle, path = tempfile.mkstemp(prefix="watchtail")
        with os.fdopen(handle, "w") as f:
            f.write(content)
        self.addCleanup(os.unlink, path)
        return path

    def _append(self, path, content):
        with open(path, "a") as f:
            f.write(content)

    def test_reads_appends_only(self) -> None:
        path = self._tempfile("old\n")
        tail = LogTail(path)
        try:
            self.assertEqual(tail.read_new(), [])
            self._append(path, "one\ntwo\n")
            self.assertEqual(tail.read_new(), ["one", "two"])
            self.assertEqual(tail.read_new(), [])
        finally:
            tail.close()

    def test_from_start_reads_existing(self) -> None:
        path = self._tempfile("old\n")
        tail = LogTail(path, from_start=True)
        try:
            self.assertEqual(tail.read_new(), ["old"])
        finally:
            tail.close()

    def test_truncation_restarts(self) -> None:
        path = self._tempfile("one\ntwo\n")
        tail = LogTail(path, from_start=True)
        try:
            self.assertEqual(tail.read_new(), ["one", "two"])
            with open(path, "w") as f:
                f.write("fresh\n")
            self.assertEqual(tail.read_new(), ["fresh"])
        finally:
            tail.close()

    def test_rotation_follows_new_file(self) -> None:
        path = self._tempfile("one\n")
        rotated = path + ".1"
        self.addCleanup(lambda: os.path.exists(rotated) and os.unlink(rotated))
        tail = LogTail(path, from_start=True)
        try:
            self.assertEqual(tail.read_new(), ["one"])
            os.rename(path, rotated)
            with open(path, "w") as f:
                f.write("two\n")
            self.assertEqual(tail.read_new(), ["two"])
        finally:
            tail.close()


class SendRunTests(unittest.TestCase):
    def test_posts_window_with_source(self) -> None:
        seen = {}

        def fake_post(url, json=None, timeout=None):
            seen["url"] = url
            seen["body"] = json
            return httpx.Response(200, json={"status": "PASS"})

        with patch("httpx.post", side_effect=fake_post):
            result = send_run("http://api:8001", "boom", target_path="inventory.py")
        self.assertEqual(result, {"status": "PASS"})
        self.assertEqual(seen["url"], "http://api:8001/api/run")
        self.assertEqual(
            seen["body"],
            {"log_text": "boom", "source": "watcher", "target_path": "inventory.py"},
        )

    def test_rejection_raises_readable_error(self) -> None:
        def fake_post(url, json=None, timeout=None):
            return httpx.Response(503, json={"detail": "no keys"})

        with patch("httpx.post", side_effect=fake_post):
            with self.assertRaises(RuntimeError) as ctx:
                send_run("http://api:8001", "boom")
        self.assertIn("503", str(ctx.exception))
        self.assertIn("no keys", str(ctx.exception))

    def test_unreachable_api_raises_readable_error(self) -> None:
        with patch("httpx.post", side_effect=httpx.ConnectError("refused")):
            with self.assertRaises(RuntimeError) as ctx:
                send_run("http://api:8001", "boom")
        self.assertIn("could not reach", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
