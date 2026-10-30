"""L-J1: Python adapter behaviour + parity with the legacy pipeline.

Every parity test pins that the adapter produces byte-identical values
to the pre-refactor helpers; the frozen `test_prod_repofix.py` (untouched)
pins the pipeline end to end.
"""

import asyncio
import unittest
from unittest import mock

from core.ingest.traceback import Frame, parse_traceback
from core.repo_fix import generate as repo_generate
from core.repo_fix import locate as repo_locate
from core.repo_fix import run as repo_run
from core.repo_fix import snapshot as repo_snapshot
from core.repo_fix.lang import all_adapters, by_name, parse
from core.repo_fix.lang.python import ADAPTER

FIXTURE = "tests/fixtures/traces/python/real-traceback.txt"

PYTEST_OUT = (
    "F.\nFAILED tests/a.py::test_x - assert\n"
    "1 failed, 1 passed in 0.05s\n"
)

PATHS = [
    "requirements.txt",
    "shop/orders.py",
    "shop/payments.py",
    "tests/test_orders.py",
]


class AdapterContractTest(unittest.TestCase):
    def test_registry_knows_python_first(self):
        self.assertIs(by_name("python"), ADAPTER)
        self.assertEqual(all_adapters()[0].name, "python")

    def test_registry_parses_python_trace(self):
        with open(FIXTURE) as handle:
            text = handle.read()
        found = parse(text)
        self.assertIsNotNone(found)
        adapter, info = found
        self.assertIs(adapter, ADAPTER)
        self.assertEqual(info.language, "python")
        self.assertTrue(info.frames)

    def test_parse_matches_legacy(self):
        with open(FIXTURE) as handle:
            text = handle.read()
        self.assertEqual(ADAPTER.parse_trace(text), parse_traceback(text))

    def test_trace_start_and_continue(self):
        self.assertTrue(
            ADAPTER.trace_start("Traceback (most recent call last):")
        )
        self.assertFalse(ADAPTER.trace_start("Traceback-ish"))
        self.assertTrue(
            ADAPTER.trace_continues('  File "/srv/shop/a.py", line 1, in f')
        )
        self.assertTrue(
            ADAPTER.trace_continues("During handling of the above exception,")
        )
        self.assertFalse(
            ADAPTER.trace_continues("queue.QueueFull: retry queue is full")
        )
        self.assertFalse(ADAPTER.trace_continues("INFO shop started"))

    def test_detect_scores_python_repos(self):
        self.assertGreater(ADAPTER.detect(PATHS), 0)
        self.assertEqual(ADAPTER.detect(["go.mod", "main.go"]), 0)
        self.assertEqual(ADAPTER.detect([]), 0)

    def test_source_files_match_snapshot(self):
        self.assertEqual(
            ADAPTER.source_files(PATHS), repo_snapshot.python_files(PATHS)
        )

    def test_map_frame_matches_locate(self):
        frames = [
            Frame("/srv/shop/orders.py", 121, "charge"),
            Frame("/other/missing.py", 1, "f"),
        ]
        via_adapter = repo_locate.match_frames(
            frames, PATHS, ADAPTER.map_frame
        )
        legacy = repo_locate.match_frames(frames, PATHS)
        self.assertEqual(via_adapter, legacy)
        self.assertEqual(via_adapter[0]["path"], "shop/orders.py")

    def test_install_cmds(self):
        # No --target: the Docker exec sets PIP_TARGET (fresh containers
        # lose system installs); Modal installs system-wide.
        self.assertEqual(
            ADAPTER.install_cmds(PATHS),
            [["pip", "install", "-r", "requirements.txt"]],
        )
        self.assertEqual(
            ADAPTER.install_cmds(["setup.py", "a.py"]),
            [["pip", "install", "-e", "."]],
        )
        self.assertEqual(ADAPTER.install_cmds(["a.py"]), [])

    def test_commands_match_legacy_pytest(self):
        self.assertEqual(
            ADAPTER.suite_cmd(PATHS),
            [*repo_run.PYTEST, "--tb=no", "-rf"],
        )
        self.assertEqual(
            ADAPTER.single_test_cmd("tests/test_x.py", PATHS),
            [*repo_run.PYTEST, "--tb=short", "tests/test_x.py"],
        )

    def test_parse_results_match_legacy(self):
        legacy = repo_run.parse_pytest(PYTEST_OUT)
        result = ADAPTER.parse_results(
            PYTEST_OUT, "", lambda _path: None
        )
        self.assertEqual(
            (result.passed, result.failed, result.total),
            (legacy["passed"], legacy["failed"], legacy["total"]),
        )
        self.assertEqual(result.failed_ids, legacy["failed_ids"])
        self.assertFalse(result.errored)

    def test_repro_path_format(self):
        self.assertEqual(
            ADAPTER.repro_test_path("ab" * 20, PATHS, []),
            "tests/test_telemetry_agent_abababababab.py",
        )

    def test_repro_rules_and_check(self):
        self.assertIn("pytest", ADAPTER.repro_rules())
        self.assertTrue(
            ADAPTER.looks_like_test("def test_x():\n    assert True\n")
        )
        self.assertFalse(ADAPTER.looks_like_test("x = 1\n"))

    def test_timeouts_match_legacy(self):
        self.assertEqual(
            (ADAPTER.install_timeout_s, ADAPTER.suite_timeout_s), (300, 600)
        )


class GenerateAdapterTest(unittest.TestCase):
    def test_repro_uses_adapter_rules(self) -> None:
        seen = {}

        def fake_generate(system_prompt, user_content):
            seen["system"] = system_prompt
            return '{"test_code": "def test_x(): assert True"}'

        with mock.patch.object(
            repo_generate.baseten_client, "generate", fake_generate
        ):
            code, _ = repo_generate.generate_repro_test(
                "tb", "E", [], ["a.py"], None, 1, 3, "tests/test_x.py",
                adapter=ADAPTER,
            )
        self.assertIn("def test_x", code)
        self.assertEqual(
            seen["system"], repo_generate.REPRO_BASE + ADAPTER.repro_rules()
        )

    def test_repro_rejects_non_test(self) -> None:
        with mock.patch.object(
            repo_generate.baseten_client,
            "generate",
            lambda *args: '{"test_code": "x = 1"}',
        ):
            with self.assertRaises(ValueError):
                repo_generate.generate_repro_test(
                    "tb", "E", [], ["a.py"], None, 1, 3, "tests/test_x.py",
                    adapter=ADAPTER,
                )


class ManifestHookTest(unittest.TestCase):
    def test_python_adapter_ignores_hook(self) -> None:
        with mock.patch.object(
            repo_locate, "read_file_at",
            side_effect=AssertionError("must not fetch"),
        ):
            asyncio.run(repo_run._configure_adapter(
                "o/r", "t", "sha", ["a.py"], object()
            ))  # Python defines no hook: returns without fetching

    def test_manifest_text_passed_to_adapter(self) -> None:
        seen = {}

        class Dummy:
            def manifest_names(self):
                return ["package.json", "missing.json"]

            def configure_manifests(self, manifests):
                seen.update(manifests)

        with mock.patch.object(repo_run, "ADAPTER", Dummy()):
            with mock.patch.object(
                repo_locate, "read_file_at", return_value='{"x":1}'
            ) as reader:
                asyncio.run(repo_run._configure_adapter(
                    "o/r", "t", "sha", ["package.json"], object()
                ))
        self.assertEqual(
            seen, {"package.json": '{"x":1}', "missing.json": None}
        )
        reader.assert_called_once()  # missing.json not fetched


if __name__ == "__main__":
    unittest.main()
