"""H0 contract tests: registry, result parsers, /connect fields, sandbox I/O.

These pin the §3 surface John and Jude code against. They use no adapters
(the first lands in H1) and mock GitHub/models; the sandbox read/write
test runs against real Docker file I/O (no image needed).
"""

import asyncio
import io
import os
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

from core.connections import github as github_conn
from core.ingest import pipeline as ingest_pipeline
from core.ingest.traceback import Frame, TracebackAssembler, TracebackInfo
from core.repo_fix import lang as lang_registry
from core.repo_fix import run as repo_run
from core.repo_fix.lang import __init__ as registry  # noqa: F401  (package import check)
from core.repo_fix.lang import (
    all_adapters,
    by_name,
    detect_repo,
    parse,
    refined_name,
)
from core.repo_fix.lang.python import ADAPTER as PYTHON_ADAPTER
from core.repo_fix.lang.results import (
    parse_go_test_json,
    parse_jest_json,
    parse_junit_xml,
)
from core.schemas.profile import SystemProfile
from core.setup import store as setup_store
from core.verify import repo_sandbox
from core.verify.local_runner import resolve_docker


JUNIT_OK = """<?xml version="1.0"?>
<testsuite name="calc" tests="3" failures="0" errors="0" skipped="0">
  <testcase classname="calc.CalcTest" name="adds"/>
  <testcase classname="calc.CalcTest" name="divides"/>
  <testcase classname="calc.CalcTest" name="rounds"/>
</testsuite>"""

JUNIT_FAIL = """<?xml version="1.0"?>
<testsuites>
  <testsuite name="calc" tests="3" failures="1" errors="1" skipped="0">
    <testcase classname="calc.CalcTest" name="adds"/>
    <testcase classname="calc.CalcTest" name="divides">
      <failure message="off by one">trace</failure>
    </testcase>
    <testcase classname="calc.CalcTest" name="rounds">
      <error message="boom">trace</error>
    </testcase>
  </testsuite>
</testsuites>"""

JEST_OK = (
    '{"numTotalTests":2,"numPassedTests":2,"numFailedTests":0,'
    '"testResults":[{"name":"tests/a.test.ts","assertionResults":['
    '{"title":"adds","ancestorTitles":["Calc"],"status":"passed"},'
    '{"title":"divides","ancestorTitles":["Calc"],"status":"passed"}]}]}'
)

JEST_FAIL = (
    '{"numTotalTests":2,"numPassedTests":1,"numFailedTests":1,'
    '"testResults":[{"name":"tests/a.test.ts","assertionResults":['
    '{"title":"adds","ancestorTitles":["Calc"],"status":"passed"},'
    '{"title":"divides","ancestorTitles":[],"status":"failed"}]}]}'
)

GO_OK = """{"Time":"2026-01-01T00:00:00Z","Action":"run","Package":"calc","Test":"TestAdd"}
{"Time":"2026-01-01T00:00:00Z","Action":"pass","Package":"calc","Test":"TestAdd","Elapsed":0}
{"Time":"2026-01-01T00:00:00Z","Action":"pass","Package":"calc","Elapsed":0}
"""

GO_FAIL = """{"Time":"2026-01-01T00:00:00Z","Action":"run","Package":"calc","Test":"TestDiv"}
{"Time":"2026-01-01T00:00:00Z","Action":"fail","Package":"calc","Test":"TestDiv","Elapsed":0}
{"Time":"2026-01-01T00:00:00Z","Action":"fail","Package":"calc","Elapsed":0}
"""

GO_BUILD_BROKEN = """calc/calc.go:3:2: no required module provides package foo
{"Time":"2026-01-01T00:00:00Z","Action":"fail","Package":"calc","Elapsed":0}
"""


class RegistryTest(unittest.TestCase):
    def test_python_first_when_present(self):
        names = [adapter.name for adapter in all_adapters()]
        self.assertEqual(sorted(names), sorted(set(names)))  # no duplicates
        if "python" in names:
            self.assertEqual(names[0], "python")

    def test_garbage_parses_to_none(self):
        self.assertIsNone(parse("this is not a stack trace at all\njust logs\n"))

    def test_detect_empty_repo(self):
        self.assertEqual(detect_repo([]), [])

    def test_typescript_refinement(self):
        self.assertEqual(
            refined_name("javascript", ["package.json", "tsconfig.json"]),
            "typescript",
        )
        self.assertEqual(refined_name("javascript", ["package.json"]), "javascript")

    def test_kotlin_refinement(self):
        self.assertEqual(
            refined_name("java", ["app/Main.kt", "pom.xml"]), "kotlin"
        )
        self.assertEqual(refined_name("java", ["pom.xml"]), "java")

    def test_aliases_resolve(self):
        self.assertIs(by_name("no-such-language"), None)
        if by_name("javascript") is not None:
            self.assertIs(by_name("typescript"), by_name("javascript"))
        if by_name("java") is not None:
            self.assertIs(by_name("kotlin"), by_name("java"))


class ResultsTest(unittest.TestCase):
    def test_junit_ok(self):
        result = parse_junit_xml(JUNIT_OK)
        self.assertEqual((result.total, result.passed, result.failed), (3, 3, 0))
        self.assertEqual(result.failed_ids, [])
        self.assertFalse(result.errored)

    def test_junit_fail(self):
        result = parse_junit_xml(JUNIT_FAIL)
        self.assertEqual((result.total, result.passed, result.failed), (3, 1, 2))
        self.assertEqual(
            result.failed_ids,
            ["calc.CalcTest.divides", "calc.CalcTest.rounds"],
        )
        self.assertFalse(result.errored)

    def test_junit_garbage_errors(self):
        self.assertTrue(parse_junit_xml("not xml at all {{{").errored)

    def test_jest_ok(self):
        result = parse_jest_json(JEST_OK)
        self.assertEqual((result.total, result.passed, result.failed), (2, 2, 0))
        self.assertEqual(result.failed_ids, [])

    def test_jest_fail_ids(self):
        result = parse_jest_json(JEST_FAIL)
        self.assertEqual((result.total, result.passed, result.failed), (2, 1, 1))
        self.assertEqual(result.failed_ids, ["tests/a.test.ts > divides"])

    def test_jest_garbage_errors(self):
        self.assertTrue(parse_jest_json("{oops").errored)

    def test_go_ok(self):
        result = parse_go_test_json(GO_OK)
        self.assertEqual((result.total, result.passed, result.failed), (1, 1, 0))
        self.assertFalse(result.errored)

    def test_go_fail_ids(self):
        result = parse_go_test_json(GO_FAIL)
        self.assertEqual((result.total, result.passed, result.failed), (1, 0, 1))
        self.assertEqual(result.failed_ids, ["calc.TestDiv"])
        self.assertFalse(result.errored)

    def test_go_build_failure_errors(self):
        result = parse_go_test_json(GO_BUILD_BROKEN)
        self.assertTrue(result.errored)

    def test_go_empty_errors(self):
        self.assertTrue(parse_go_test_json("").errored)


class FakeResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body


class FakeGitHubClient:
    """Canned success: repo → ref → tree → write probe → delete."""

    def __init__(self, language, tree_paths=None):
        self._language = language
        self._tree_paths = list(tree_paths or [])

    def get(self, path, **kwargs):
        _ = kwargs
        if path.endswith("/git/ref/heads/main"):
            return FakeResponse(200, {"object": {"sha": "abc123"}})
        if "/git/trees/" in path:
            return FakeResponse(
                200,
                {
                    "tree": [
                        {"path": name, "type": "blob"}
                        for name in self._tree_paths
                    ],
                    "truncated": False,
                },
            )
        return FakeResponse(
            200, {"default_branch": "main", "language": self._language}
        )

    def post(self, path, json=None):
        return FakeResponse(201, {})

    def delete(self, path):
        return FakeResponse(204, {})


class ConnectFieldsTest(unittest.TestCase):
    def _check(self, language, tree_paths=None):
        return github_conn.check_repo(
            "owner/repo",
            "token",
            "",
            client=FakeGitHubClient(language, tree_paths),
        )

    def test_python_repo_detected_and_autofixable(self):
        result = self._check("Python", ["app.py", "requirements.txt"])
        self.assertTrue(result["ok"])
        self.assertEqual(result["language"], "python")
        self.assertTrue(result["autofix"])

    def test_typescript_autofix_follows_adapter(self):
        result = self._check(
            "TypeScript", ["package.json", "tsconfig.json", "src/a.ts"]
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["language"], "typescript")
        # Gated: False until John's javascript ADAPTER wires, True after.
        self.assertEqual(
            result["autofix"], by_name("typescript") is not None
        )

    def test_rollup_fallback_when_tree_empty(self):
        result = self._check("Go", [])
        self.assertTrue(result["ok"])
        self.assertEqual(result["language"], "go")
        self.assertFalse(result["autofix"])

    def test_unsupported_language_not_autofixable(self):
        result = self._check("Cobol", ["main.cob"])
        self.assertTrue(result["ok"])
        self.assertEqual(result["language"], "cobol")
        self.assertFalse(result["autofix"])

    def test_traceback_info_defaults_to_python(self):
        self.assertEqual(TracebackInfo("E", "v").language, "python")


class DiscoveryTest(unittest.TestCase):
    DUMMY = os.path.join(
        os.path.dirname(__file__),
        "..",
        "core",
        "repo_fix",
        "lang",
        "zz_dummy_test_adapter.py",
    )

    def test_dummy_adapter_is_discovered(self):
        with open(self.DUMMY, "w") as handle:
            handle.write(
                "from core.repo_fix.lang.base import SuiteResult\n"
                "class Dummy:\n"
                "    name = 'zz-dummy'\n"
                "ADAPTER = Dummy()\n"
            )
        try:
            import core.repo_fix.lang as registry

            names = [adapter.name for adapter in registry.all_adapters()]
            self.assertIn("zz-dummy", names)
            self.assertIsNotNone(registry.by_name("zz-dummy"))
        finally:
            if os.path.exists(self.DUMMY):
                os.remove(self.DUMMY)
            sys.modules.pop("core.repo_fix.lang.zz_dummy_test_adapter", None)
        import core.repo_fix.lang as registry

        names = [adapter.name for adapter in registry.all_adapters()]
        self.assertNotIn("zz-dummy", names)

    def test_plural_adapters_are_discovered(self):
        path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "core",
            "repo_fix",
            "lang",
            "zz_dummy_plural_adapter.py",
        )
        with open(path, "w") as handle:
            handle.write(
                "class Dummy:\n"
                "    def __init__(self, name):\n"
                "        self.name = name\n"
                "ADAPTERS = [Dummy('zz-plural-a'), Dummy('zz-plural-b')]\n"
            )
        try:
            import core.repo_fix.lang as registry

            names = [adapter.name for adapter in registry.all_adapters()]
            self.assertIn("zz-plural-a", names)
            self.assertIn("zz-plural-b", names)
            self.assertIsNotNone(registry.by_name("zz-plural-a"))
            self.assertIsNotNone(registry.by_name("zz-plural-b"))
        finally:
            if os.path.exists(path):
                os.remove(path)
            sys.modules.pop(
                "core.repo_fix.lang.zz_dummy_plural_adapter", None
            )
        import core.repo_fix.lang as registry

        names = [adapter.name for adapter in registry.all_adapters()]
        self.assertNotIn("zz-plural-a", names)
        self.assertNotIn("zz-plural-b", names)


def _tiny_tarball():
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        data = b"print('hi')\n"
        member = tarfile.TarInfo("app.py")
        member.size = len(data)
        tar.addfile(member, io.BytesIO(data))
    return buf.getvalue()


@unittest.skipUnless(resolve_docker(), "docker CLI not available")
class SandboxIOTest(unittest.TestCase):
    def test_read_write_roundtrip(self):
        box = repo_sandbox.DockerRepoSandbox.create(
            _tiny_tarball(), resolve_docker()
        )
        try:
            box.write_file("nested/fix.py", "x = 1\n")
            self.assertEqual(box.read_file("nested/fix.py"), "x = 1\n")
            self.assertEqual(box.read_file("app.py"), "print('hi')\n")
            self.assertIsNone(box.read_file("missing.txt"))
            with self.assertRaises(ValueError):
                box.read_file("../escape.txt")
            with self.assertRaises(ValueError):
                box.write_file("/abs.txt", "nope")
        finally:
            box.terminate()

    def test_image_selects_go_image(self):
        with mock.patch.dict(os.environ, {"TA_VERIFY": "local"}):
            box = repo_sandbox.open_repo_sandbox(_tiny_tarball(), image="go")
        try:
            self.assertEqual(box._image, "telemetry-agent-sandbox-go")
        finally:
            box.terminate()

    def test_image_defaults_to_python(self):
        with mock.patch.dict(os.environ, {"TA_VERIFY": "local"}):
            box = repo_sandbox.open_repo_sandbox(_tiny_tarball())
        try:
            self.assertEqual(box._image, "telemetry-agent-sandbox")
        finally:
            box.terminate()


class ModalImageTest(unittest.TestCase):
    def test_every_image_key_builds(self):
        try:
            import modal  # noqa: F401
        except ImportError:
            self.skipTest("modal not installed")
        for key in ("python", "node", "jvm", "go", "rust", "php"):
            with self.subTest(key=key):
                self.assertIsNotNone(repo_sandbox._modal_image(key))
        self.assertIsNotNone(repo_sandbox._modal_image("cobol"))

    def test_append_cmd_shapes(self):
        legacy = repo_sandbox._append_cmd("/tmp/x", "QUJD", False)
        self.assertEqual(legacy[:3], ["python", "-c", repo_sandbox._APPEND_CHUNK])
        portable = repo_sandbox._append_cmd("/tmp/x", "QUJD", True)
        self.assertEqual(portable[:2], ["sh", "-c"])
        self.assertIn("base64 -d >>", portable[2])


class _StubAdapter:
    """Minimal non-Python adapter: head, `STUB> file:line`, `STUB-END`."""

    name = "stub"

    def trace_start(self, line: str) -> bool:
        return line == "STUB-HEAD"

    def trace_continues(self, line: str) -> bool:
        return line.startswith("STUB> ")

    def parse_trace(self, text: str):
        lines = text.splitlines()
        if not lines or lines[0] != "STUB-HEAD":
            return None
        frames = []
        for item in lines[1:]:
            if item.startswith("STUB> "):
                rest = item[len("STUB> "):]
                if ":" not in rest:
                    return None
                name, _, lineno = rest.rpartition(":")
                try:
                    frames.append(Frame(name, int(lineno), "s"))
                except ValueError:
                    return None
            elif item.startswith("STUB-END"):
                continue
            else:
                return None
        if not frames:
            return None
        return TracebackInfo("StubError", "boom", frames, text, "stub")


PY_LINES = [
    "Traceback (most recent call last):",
    '  File "/srv/a.py", line 1, in f',
    "    boom()",
    "ValueError: bad",
]

STUB_LINES = ["STUB-HEAD", "STUB> a.js:10", "STUB> b.js:20"]


def _feed_all(lines):
    assembler = TracebackAssembler()
    completed = []
    for line in lines:
        done = assembler.feed(line, 0.0)
        if done is not None:
            completed.append(done)
    return completed


class AssemblerLangsTest(unittest.TestCase):
    def test_mixed_stream_one_trace_each(self):
        with mock.patch.object(
            lang_registry, "all_adapters",
            return_value=[PYTHON_ADAPTER, _StubAdapter()],
        ):
            completed = _feed_all(
                ["noise before", *PY_LINES, "noise", *STUB_LINES, "tail"]
            )
        self.assertEqual(len(completed), 2)
        with mock.patch.object(
            lang_registry, "all_adapters",
            return_value=[PYTHON_ADAPTER, _StubAdapter()],
        ):
            first = parse(completed[0])
            second = parse(completed[1])
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertEqual(first[1].language, "python")
        self.assertEqual(second[1].language, "stub")
        self.assertTrue(first[1].frames)
        self.assertTrue(second[1].frames)

    def test_python_assembly_byte_identical(self):
        with mock.patch.object(
            lang_registry, "all_adapters",
            return_value=[PYTHON_ADAPTER, _StubAdapter()],
        ):
            completed = _feed_all(PY_LINES)
        self.assertEqual(completed, ["\n".join(PY_LINES)])

    def test_generic_completes_without_trailer(self):
        with mock.patch.object(
            lang_registry, "all_adapters",
            return_value=[PYTHON_ADAPTER, _StubAdapter()],
        ):
            completed = _feed_all([*STUB_LINES, "tail"])
        self.assertEqual(completed, ["\n".join(STUB_LINES)])

    def test_generic_completes_with_closing_line(self):
        with mock.patch.object(
            lang_registry, "all_adapters",
            return_value=[PYTHON_ADAPTER, _StubAdapter()],
        ):
            completed = _feed_all([*STUB_LINES, "STUB-END ok"])
        self.assertEqual(completed, ["\n".join([*STUB_LINES, "STUB-END ok"])])

    def test_foreign_start_flushes_and_switches(self):
        with mock.patch.object(
            lang_registry, "all_adapters",
            return_value=[PYTHON_ADAPTER, _StubAdapter()],
        ):
            completed = _feed_all(["STUB-HEAD", *PY_LINES])
        # The stub head (unparseable alone) is preserved as one entry;
        # the Python trace still assembles whole.
        self.assertEqual(completed, ["STUB-HEAD", "\n".join(PY_LINES)])

    def test_assemble_entries_carry_languages(self):
        ingest_pipeline.reset_assemblers()
        with mock.patch.object(
            lang_registry, "all_adapters",
            return_value=[PYTHON_ADAPTER, _StubAdapter()],
        ):
            entries = ingest_pipeline.assemble(
                "ingest:t:api",
                [*PY_LINES, "noise", *STUB_LINES, "tail"],
                0.0,
            )
        texts = [entry.text for entry in entries]
        self.assertEqual(
            texts,
            ["\n".join(PY_LINES), "noise", "\n".join(STUB_LINES), "tail"],
        )
        self.assertEqual(entries[0].traceback.language, "python")
        self.assertIsNone(entries[1].traceback)
        self.assertEqual(entries[2].traceback.language, "stub")
        self.assertIsNone(entries[3].traceback)
        ingest_pipeline.reset_assemblers()


def _sentry_payload(platform=None, frames=(), exc_type="", exc_value=""):
    issue = {
        "title": "t",
        "metadata": {"type": exc_type, "value": exc_value},
        "entries": [
            {"type": "stacktrace", "data": {"frames": list(frames)}}
        ],
    }
    if platform is not None:
        issue["platform"] = platform
    return {"data": {"issue": issue}}


class SentryLangsTest(unittest.TestCase):
    def test_sentry_language_mapping(self):
        cases = [
            (None, (), "python"),
            ("python", (), "python"),
            ("node", (), "javascript"),
            ("javascript", (), "javascript"),
            ("java", (), "java"),
            ("go", (), "go"),
            ("rust", (), "rust"),
            ("php", (), "php"),
            ("ruby", (), "ruby"),
        ]
        for platform, frames, want in cases:
            with self.subTest(platform=platform):
                self.assertEqual(
                    ingest_pipeline.sentry_language(
                        _sentry_payload(platform, frames)
                    ),
                    want,
                )

    def test_sentry_language_refines_siblings(self):
        ts = [{"filename": "src/a.ts", "lineno": 1, "function": "f"}]
        self.assertEqual(
            ingest_pipeline.sentry_language(
                _sentry_payload("node", ts)
            ),
            "typescript",
        )
        kt = [{"filename": "App.kt", "lineno": 1, "function": "f"}]
        self.assertEqual(
            ingest_pipeline.sentry_language(
                _sentry_payload("java", kt)
            ),
            "kotlin",
        )

    def test_sentry_python_rendering_unchanged(self):
        payload = _sentry_payload(
            None,
            [
                {"filename": "shop/views.py", "lineno": 42,
                 "function": "checkout"},
                {"filename": "shop/cart.py", "lineno": 17,
                 "function": "total"},
            ],
            "ZeroDivisionError", "division by zero",
        )
        self.assertEqual(
            ingest_pipeline.sentry_texts(payload),
            [
                "Traceback (most recent call last):",
                '  File "shop/views.py", line 42, in checkout',
                '  File "shop/cart.py", line 17, in total',
                "ZeroDivisionError: division by zero",
            ],
        )

    def test_sentry_java_marker_and_shape(self):
        payload = _sentry_payload(
            "java",
            [{"filename": "Cart.java", "lineno": 17,
              "function": "total", "module": "com.acme.Cart"}],
            "com.acme.CartException", "empty",
        )
        texts = ingest_pipeline.sentry_texts(payload)
        self.assertEqual(
            texts,
            [
                "ta-language: java",
                "com.acme.CartException: empty",
                "\tat com.acme.Cart.total(Cart.java:17)",
            ],
        )

    def test_assemble_collects_java_despite_marker(self):
        # The java adapter is registered now: the trace assembles and
        # parses (parsed language wins, no hint needed).
        ingest_pipeline.reset_assemblers()
        entries = ingest_pipeline.assemble(
            "ingest:t:sentry",
            ["ta-language: java", "com.acme.E: empty",
             "\tat com.acme.C.m(C.java:1)", "done"],
            0.0,
        )
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].traceback.language, "java")
        self.assertIsNone(entries[0].hint)
        self.assertNotIn("ta-language", entries[0].text)
        self.assertEqual(entries[1].text, "done")
        ingest_pipeline.reset_assemblers()

    def test_assemble_hints_unparsed_language(self):
        ingest_pipeline.reset_assemblers()
        entries = ingest_pipeline.assemble(
            "ingest:t:sentry",
            ["ta-language: ruby", "boom happened", "more"],
            0.0,
        )
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].hint, "ruby")
        self.assertIsNone(entries[0].traceback)
        self.assertIsNone(entries[1].hint)
        self.assertNotIn("ta-language", entries[0].text)
        ingest_pipeline.reset_assemblers()

    def test_marker_ignored_for_log_keys(self):
        ingest_pipeline.reset_assemblers()
        entries = ingest_pipeline.assemble(
            "ingest:t:api", ["ta-language: java"], 0.0
        )
        self.assertEqual(len(entries), 1)
        self.assertIsNone(entries[0].hint)
        self.assertEqual(entries[0].text, "ta-language: java")
        ingest_pipeline.reset_assemblers()


class TriggerLangsTest(unittest.TestCase):
    def _profile(self):
        return SystemProfile(
            system_id="acme",
            name="Acme",
            kind="software",
            environment={"mode": "production"},
            status="armed",
        )

    def test_should_trigger_names_python_adapter(self):
        decision = {
            "decision": "observe",
            "rule": "traceback",
            "fingerprint": "fp0011223344",
            "window": "\n".join(PY_LINES),
            "commit": "abc123",
        }
        with mock.patch.object(
            github_conn, "connection_repo",
            return_value={"repo": "a/b", "base": "", "token": "t"},
        ):
            ctx = repo_run.should_trigger(self._profile(), decision)
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx["adapter_name"], "python")
        self.assertEqual(ctx["language"], "python")

    def test_should_trigger_rejects_unparseable(self):
        decision = {
            "decision": "observe",
            "rule": "error",
            "fingerprint": "fp0011223344",
            "window": "ERROR something broke",
            "commit": "abc123",
        }
        with mock.patch.object(
            github_conn, "connection_repo",
            return_value={"repo": "a/b", "base": "", "token": "t"},
        ):
            self.assertIsNone(
                repo_run.should_trigger(self._profile(), decision)
            )

    def test_gate_body_carries_language_and_note(self):
        # Ruby has no adapter: the hint still names the language and the
        # decision says auto-fix is unsupported.
        tmp = tempfile.mkdtemp(prefix="ta-lang-ingest-")
        system_id = "acme-lang"
        with mock.patch.dict(os.environ, {"TA_DATA_DIR": tmp}):
            setup_store.save_profile(
                SystemProfile(
                    system_id=system_id,
                    name="Acme",
                    kind="software",
                    environment={"mode": "production"},
                    status="armed",
                )
            )
            ingest_pipeline.reset_assemblers()
            result = asyncio.run(
                ingest_pipeline.process_lines(
                    system_id, "sentry",
                    ["ta-language: ruby", "boom happened"],
                )
            )
            ingest_pipeline.reset_assemblers()
        self.assertEqual(result["candidates"], 1)
        self.assertEqual(len(result["decisions"]), 1)
        body = result["decisions"][0]
        self.assertEqual(body["language"], "ruby")
        self.assertFalse(body["autofix"])
        self.assertEqual(
            body["autofix_note"], "auto-fix not supported for ruby yet"
        )

    def test_gate_body_marks_python_supported(self):
        tmp = tempfile.mkdtemp(prefix="ta-lang-ingest-")
        system_id = "acme-lang-py"
        with mock.patch.dict(os.environ, {"TA_DATA_DIR": tmp}):
            setup_store.save_profile(
                SystemProfile(
                    system_id=system_id,
                    name="Acme",
                    kind="software",
                    environment={"mode": "production"},
                    status="armed",
                )
            )
            ingest_pipeline.reset_assemblers()
            result = asyncio.run(
                ingest_pipeline.process_lines(system_id, "api", PY_LINES)
            )
            ingest_pipeline.reset_assemblers()
        self.assertEqual(result["candidates"], 1)
        body = result["decisions"][0]
        self.assertEqual(body["language"], "python")
        self.assertTrue(body["autofix"])
        self.assertNotIn("autofix_note", body)


if __name__ == "__main__":
    unittest.main()
