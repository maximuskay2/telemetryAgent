"""N-R1: device command queue lifecycle (enqueue → ack / expire)."""

import unittest

from core.devices import queue


class DeviceQueueTests(unittest.TestCase):
    def setUp(self) -> None:
        queue.reset()

    def test_enqueue_and_pending_projection(self) -> None:
        entry = queue.enqueue(
            "dev-1", "run-1", "opt_defrost", "defrost", {}, now=1000.0
        )
        self.assertEqual(entry["status"], "sent")
        self.assertEqual(entry["expires_at"], 1000.0 + queue.COMMAND_TTL_S)
        pending = queue.pending_for("dev-1", now=1001.0)
        self.assertEqual(len(pending), 1)
        self.assertEqual(
            sorted(pending[0].keys()),
            ["action", "expires_at", "id", "params"],
        )
        self.assertEqual(pending[0]["action"], "defrost")
        self.assertEqual(queue.pending_for("dev-2", now=1001.0), [])

    def test_ack_ok_marks_done(self) -> None:
        entry = queue.enqueue(
            "dev-1", "run-1", "opt_defrost", "defrost", {}, now=1000.0
        )
        done = queue.ack(entry["id"], True, "relay on", now=1010.0)
        assert done is not None
        self.assertEqual(done["status"], "done")
        self.assertEqual(done["detail"], "relay on")
        self.assertEqual(queue.pending_for("dev-1", now=1011.0), [])
        statuses = queue.option_statuses("run-1")
        self.assertEqual(statuses["opt_defrost"]["status"], "done")

    def test_ack_fail_marks_failed(self) -> None:
        entry = queue.enqueue(
            "dev-1", "run-1", "opt_power_cycle", "power_cycle",
            {"min_off_s": 180}, now=1000.0,
        )
        failed = queue.ack(entry["id"], False, "compressor ran 3s ago",
                            now=1010.0)
        assert failed is not None
        self.assertEqual(failed["status"], "failed")
        self.assertIn("compressor", failed["detail"])

    def test_unacked_command_expires(self) -> None:
        entry = queue.enqueue(
            "dev-1", "run-1", "opt_defrost", "defrost", {}, now=1000.0
        )
        self.assertEqual(
            queue.pending_for("dev-1", now=1000.0 + queue.COMMAND_TTL_S + 1),
            [],
        )
        stored = queue.get(entry["id"])
        assert stored is not None
        self.assertEqual(stored["status"], "expired")
        self.assertIn("offline", stored["detail"])
        statuses = queue.option_statuses("run-1")
        self.assertEqual(statuses["opt_defrost"]["status"], "expired")

    def test_ack_after_expiry_stays_expired(self) -> None:
        entry = queue.enqueue(
            "dev-1", "run-1", "opt_defrost", "defrost", {}, now=1000.0
        )
        late = queue.ack(
            entry["id"], True, "finally", now=1000.0 + queue.COMMAND_TTL_S + 1
        )
        assert late is not None
        self.assertEqual(late["status"], "expired")

    def test_unknown_ack_returns_none(self) -> None:
        self.assertIsNone(queue.ack("cmd_nope", True, now=1000.0))

    def test_terminal_ack_is_idempotent(self) -> None:
        entry = queue.enqueue(
            "dev-1", "run-1", "opt_defrost", "defrost", {}, now=1000.0
        )
        queue.ack(entry["id"], True, "relay on", now=1010.0)
        again = queue.ack(entry["id"], False, "oops", now=1011.0)
        assert again is not None
        self.assertEqual(again["status"], "done")
        self.assertEqual(again["detail"], "relay on")

    def test_option_status_for_manual_execute(self) -> None:
        queue.set_option_status("run-1", "opt_manual_1", "done", now=1000.0)
        statuses = queue.option_statuses("run-1")
        self.assertEqual(statuses["opt_manual_1"]["status"], "done")
        self.assertEqual(queue.option_statuses("run-2"), {})


if __name__ == "__main__":
    unittest.main()
