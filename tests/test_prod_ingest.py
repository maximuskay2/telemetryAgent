"""J-R1 acceptance: real error intake + forwarder (James)."""

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import apps.api.main as api_main
from apps.api.main import app
from core.connections import store as connection_store
from core.ingest import pipeline as ingest_pipeline
from core.ingest.traceback import (
    TracebackAssembler,
    parse_traceback,
)
from core.schemas.profile import SystemProfile
from core.setup import store as setup_store

SAMPLE_TRACEBACK = """Traceback (most recent call last):
  File "/srv/shop/views.py", line 42, in checkout
    total = cart.total()
  File "/srv/shop/cart.py", line 17, in total
    return sum(items) / len(items)
ZeroDivisionError: division by zero"""

CHAINED_TRACEBACK = """Traceback (most recent call last):
  File "/srv/shop/db.py", line 9, in save
    conn.commit()
TimeoutError: commit timed out
During handling of the above exception, another exception occurred:
Traceback (most recent call last):
  File "/srv/shop/views.py", line 50, in checkout
    save(order)
RuntimeError: order not saved"""

ROOT = Path(__file__).resolve().parent.parent


def _tmp_data() -> str:
    return tempfile.mkdtemp(prefix="ta-ingest-test-")


def _save_production_system(tmp: str, system_id: str) -> None:
    with patch.dict(os.environ, {"TA_DATA_DIR": tmp}):
        setup_store.save_profile(
            SystemProfile(
                system_id=system_id,
                name="Acme",
                kind="software",
                environment={"mode": "production"},
                status="armed",
            )
        )


def _make_key(tmp: str, system_id: str, kind: str) -> str:
    with patch.dict(os.environ, {"TA_DATA_DIR": tmp}):
        _, key = connection_store.create_connection(
            system_id, kind, {}, None
        )
    assert key is not None
    return key


def _decisions_for(system_id: str, rule: str) -> list:
    return [
        item
        for item in api_main.gate_decisions
        if item.get("system_id") == system_id and item.get("rule") == rule
    ]


def _lines(messages: list) -> list:
    return [
        {"ts": 1700000000.0 + index, "level": "ERROR", "message": text}
        for index, text in enumerate(messages)
    ]


class TracebackParserTests(unittest.TestCase):
    def test_parses_frames_and_exception(self) -> None:
        parsed = parse_traceback(SAMPLE_TRACEBACK)
        assert parsed is not None
        self.assertEqual(parsed.exc_type, "ZeroDivisionError")
        self.assertEqual(parsed.exc_value, "division by zero")
        self.assertEqual(len(parsed.frames), 2)
        self.assertEqual(parsed.frames[1].file, "/srv/shop/cart.py")
        self.assertEqual(parsed.frames[1].line, 17)
        self.assertEqual(parsed.frames[1].func, "total")
        self.assertEqual(
            parsed.signature, "ZeroDivisionError: division by zero"
        )

    def test_chained_keeps_last_exception(self) -> None:
        parsed = parse_traceback(CHAINED_TRACEBACK)
        assert parsed is not None
        self.assertEqual(parsed.exc_type, "RuntimeError")
        self.assertEqual(len(parsed.frames), 2)

    def test_garbage_returns_none(self) -> None:
        self.assertIsNone(parse_traceback("just a log line\nanother one"))


class AssemblerTests(unittest.TestCase):
    def test_split_feed_completes_once(self) -> None:
        assembler = TracebackAssembler()
        lines = SAMPLE_TRACEBACK.splitlines()
        results = [assembler.feed(line, 100.0) for line in lines]
        completed = [text for text in results if text is not None]
        self.assertEqual(len(completed), 1)
        self.assertIn("ZeroDivisionError", completed[0])

    def test_stale_flush_returns_plain_lines(self) -> None:
        assembler = TracebackAssembler()
        assembler.feed("Traceback (most recent call last):", 100.0)
        assembler.feed('  File "x.py", line 1, in f', 100.0)
        self.assertEqual(assembler.flush_stale(101.0), [])
        stale = assembler.flush_stale(200.0)
        self.assertEqual(len(stale), 2)
        self.assertFalse(assembler.collecting)


class IngestApiTests(unittest.TestCase):
    def setUp(self) -> None:
        ingest_pipeline.reset_assemblers()

    def test_traceback_is_one_candidate_with_frames(self) -> None:
        tmp = _tmp_data()
        system_id = "acme-tb"
        _save_production_system(tmp, system_id)
        key = _make_key(tmp, system_id, "logs")
        messages = SAMPLE_TRACEBACK.splitlines()
        with patch.dict(os.environ, {"TA_DATA_DIR": tmp}):
            with TestClient(app) as client:
                response = client.post(
                    "/api/ingest/logs",
                    json={"service": "api", "lines": _lines(messages)},
                    headers={"Authorization": f"Bearer {key}"},
                )
        self.assertEqual(
            response.json(),
            {"accepted": len(messages), "candidates": 1},
        )
        logged = _decisions_for(system_id, "traceback")
        self.assertEqual(len(logged), 1)
        # Frames ride on the gate window for J-R3 to re-parse.
        frames = parse_traceback(logged[0].get("window", "") or "")
        assert frames is not None
        self.assertEqual(frames.exc_type, "ZeroDivisionError")
        self.assertEqual(len(frames.frames), 2)
        self.assertEqual(frames.frames[1].file, "/srv/shop/cart.py")
        self.assertEqual(frames.frames[1].line, 17)

    def test_traceback_split_across_requests_is_one_candidate(self) -> None:
        tmp = _tmp_data()
        system_id = "acme-split"
        _save_production_system(tmp, system_id)
        key = _make_key(tmp, system_id, "logs")
        messages = SAMPLE_TRACEBACK.splitlines()
        headers = {"Authorization": f"Bearer {key}"}
        with patch.dict(os.environ, {"TA_DATA_DIR": tmp}):
            with TestClient(app) as client:
                first = client.post(
                    "/api/ingest/logs",
                    json={"service": "api", "lines": _lines(messages[:3])},
                    headers=headers,
                )
                second = client.post(
                    "/api/ingest/logs",
                    json={"service": "api", "lines": _lines(messages[3:])},
                    headers=headers,
                )
        self.assertEqual(first.json()["candidates"], 0)
        self.assertEqual(second.json()["candidates"], 1)
        self.assertEqual(len(_decisions_for(system_id, "traceback")), 1)

    def test_plain_lines_have_no_candidates(self) -> None:
        tmp = _tmp_data()
        system_id = "acme-plain"
        _save_production_system(tmp, system_id)
        key = _make_key(tmp, system_id, "logs")
        with patch.dict(os.environ, {"TA_DATA_DIR": tmp}):
            with TestClient(app) as client:
                response = client.post(
                    "/api/ingest/logs",
                    json={
                        "service": "api",
                        "lines": _lines(["serving on :8000", "request ok"]),
                    },
                    headers={"Authorization": f"Bearer {key}"},
                )
        self.assertEqual(response.json(), {"accepted": 2, "candidates": 0})

    def test_first_log_flips_waiting_to_ok_once(self) -> None:
        tmp = _tmp_data()
        system_id = "acme-first"
        _save_production_system(tmp, system_id)
        key = _make_key(tmp, system_id, "logs")
        headers = {"Authorization": f"Bearer {key}"}
        payload = {"service": "api", "lines": _lines(["ERROR boom"])}
        with patch.dict(os.environ, {"TA_DATA_DIR": tmp}):
            with (
                TestClient(app) as client,
                patch.object(
                    api_main.hub, "broadcast", new=AsyncMock()
                ) as broadcast,
            ):
                client.post(
                    "/api/ingest/logs", json=payload, headers=headers
                )
                client.post(
                    "/api/ingest/logs", json=payload, headers=headers
                )
        kinds = [
            call.args[0].kind for call in broadcast.await_args_list
        ]
        self.assertEqual(kinds.count("connection_status"), 1)
        event = next(
            call.args[0]
            for call in broadcast.await_args_list
            if call.args[0].kind == "connection_status"
        )
        self.assertEqual(event.payload["system_id"], system_id)
        self.assertEqual(event.payload["status"], "ok")

    def test_sentry_fixture_produces_traceback_candidate(self) -> None:
        tmp = _tmp_data()
        system_id = "acme-sentry"
        _save_production_system(tmp, system_id)
        key = _make_key(tmp, system_id, "sentry")
        payload = json.loads(
            (ROOT / "tests" / "fixtures" / "sentry_issue.json").read_text(
                encoding="utf-8"
            )
        )
        with patch.dict(os.environ, {"TA_DATA_DIR": tmp}):
            with TestClient(app) as client:
                first = client.post(f"/api/ingest/sentry/{key}", json=payload)
                second = client.post(f"/api/ingest/sentry/{key}", json=payload)
        self.assertEqual(first.json(), {"accepted": 1})
        self.assertEqual(second.json(), {"accepted": 1})
        logged = _decisions_for(system_id, "traceback")
        self.assertEqual(len(logged), 2)
        # Same error, same fingerprint (one PR per fingerprint in J-R3).
        self.assertEqual(logged[0]["fingerprint"], logged[1]["fingerprint"])
        self.assertIn("ZeroDivisionError", logged[0]["signature"])

    def test_production_act_is_recorded_not_run(self) -> None:
        tmp = _tmp_data()
        system_id = "acme-act"
        with patch.dict(os.environ, {"TA_DATA_DIR": tmp}):
            setup_store.save_profile(
                SystemProfile(
                    system_id=system_id,
                    name="Acme",
                    kind="software",
                    environment={"mode": "production"},
                    status="armed",
                    hard_limits=[
                        {
                            "metric": "error_rate",
                            "op": ">",
                            "threshold": 0.5,
                            "provenance": {
                                "source_doc": "manual",
                                "quote": "",
                                "confidence": 1.0,
                            },
                        }
                    ],
                )
            )
            before = set(api_main.software_runs)
            result = asyncio.run(
                ingest_pipeline.process_lines(
                    system_id,
                    "api",
                    ["ERROR error_rate critical"],
                    extra_metrics={"error_rate": 0.9},
                )
            )
            after = set(api_main.software_runs)
        self.assertEqual(result["candidates"], 1)
        self.assertEqual(result["decisions"][0]["decision"], "act")
        self.assertEqual(before, after)  # J-R3 wires the run

    def test_demo_system_delegates_to_existing_gate(self) -> None:
        tmp = _tmp_data()
        system_id = "acme-demo"
        with patch.dict(os.environ, {"TA_DATA_DIR": tmp}):
            setup_store.save_profile(
                SystemProfile(
                    system_id=system_id, name="Demo",
                    kind="software", status="armed",
                )
            )
        key = _make_key(tmp, system_id, "logs")
        before = len(_decisions_for(system_id, "traceback"))
        with patch.dict(os.environ, {"TA_DATA_DIR": tmp}):
            with TestClient(app) as client:
                response = client.post(
                    "/api/ingest/logs",
                    json={
                        "service": "api",
                        "lines": _lines(SAMPLE_TRACEBACK.splitlines()),
                    },
                    headers={"Authorization": f"Bearer {key}"},
                )
        self.assertEqual(response.json()["candidates"], 1)
        # Delegated once: the existing endpoint recorded the decision.
        self.assertEqual(len(_decisions_for(system_id, "traceback")), before + 1)

    def test_forwarder_script_is_served(self) -> None:
        with TestClient(app) as client:
            response = client.get("/forwarder.py")
        self.assertEqual(response.status_code, 200)
        self.assertIn("ta_forward", response.text)
        self.assertIn("urllib.request", response.text)


class ForwarderLiveTests(unittest.TestCase):
    def test_outage_buffers_and_delivers_once_in_order(self) -> None:
        received: list = []
        state = {"fail_until": time.time() + 2.0}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                batch = json.loads(self.rfile.read(length) or b"{}")
                if time.time() < state["fail_until"]:
                    self.send_response(500)
                    self.end_headers()
                    return
                received.extend(
                    line["message"] for line in batch.get("lines", [])
                )
                self.send_response(200)
                self.send_headers()
                self.wfile.write(b'{"accepted":1,"candidates":0}')

            def send_headers(self) -> None:
                self.send_header("Content-Type", "application/json")
                self.end_headers()

            def log_message(self, *args) -> None:  # noqa: ANN002,ANN003
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        tmpdir = tempfile.mkdtemp(prefix="ta-forward-test-")
        log_path = os.path.join(tmpdir, "app.log")
        Path(log_path).write_text("boot ok\n", encoding="utf-8")
        command = [
            sys.executable,
            str(ROOT / "agent" / "ta_forward.py"),
            "--api", f"http://127.0.0.1:{port}",
            "--key", "ta_live_test",
            "--file", log_path,
            "--service", "api",
            "--level", "WARNING",
            "--interval", "0.2",
            "--idle-exit", "6",
        ]
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            time.sleep(0.5)  # forwarder tails from the end
            wanted = [f"ERROR order {index} failed" for index in range(5)]
            with open(log_path, "a", encoding="utf-8") as handle:
                handle.write("INFO all quiet\n")
                for line in wanted:
                    handle.write(line + "\n")
                handle.flush()
            _, _ = process.communicate(timeout=30)
        finally:
            server.shutdown()
            server.server_close()
        self.assertEqual(received, wanted)
