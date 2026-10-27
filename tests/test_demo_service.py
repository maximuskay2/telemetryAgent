"""Demo service pins CLI behavior and log format (signal volume is probe-verified)."""

import importlib.util
import os
import random
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SERVICE = Path(__file__).resolve().parent.parent / "demo" / "target-service" / "run_service.py"
STAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z ")


def _load_service():
    spec = importlib.util.spec_from_file_location("demo_run_service", SERVICE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DemoServiceTests(unittest.TestCase):
    def test_run_completes_with_stamped_lines(self) -> None:
        run_service = _load_service()
        with tempfile.TemporaryDirectory(prefix="svc-log") as tmp:
            log_path = os.path.join(tmp, "service.log")
            exit_code = run_service.main(
                ["--workers", "2", "--ops", "10", "--seed", "7",
                 "--log", log_path, "--quiet"]
            )
            self.assertEqual(exit_code, 0)
            with open(log_path, encoding="utf-8") as f:
                lines = [line.rstrip("\n") for line in f]
        self.assertGreaterEqual(len(lines), 2)
        for line in lines:
            self.assertRegex(line, STAMP)
        text = "\n".join(lines)
        self.assertIn("starting", text)
        self.assertIn("done transactions=20", text)

    def test_wedged_transfer_logs_retries_then_deadlock(self) -> None:
        run_service = _load_service()
        with tempfile.TemporaryDirectory(prefix="svc-log") as tmp:
            log_path = os.path.join(tmp, "service.log")
            log = run_service.Logger(log_path, echo=False)
            try:
                with patch.object(
                    run_service, "_acquire_timed", return_value=(None, True)
                ), patch("time.sleep", return_value=None):
                    ok = run_service.transfer(
                        log, random.Random(1), 99, hold_ms=0.0
                    )
            finally:
                log.close()
            with open(log_path, encoding="utf-8") as f:
                text = f.read()
        self.assertFalse(ok)
        self.assertIn("WARNING retry=1", text)
        self.assertIn("WARNING retry=3", text)
        self.assertIn("Deadlock detected", text)


if __name__ == "__main__":
    unittest.main()
