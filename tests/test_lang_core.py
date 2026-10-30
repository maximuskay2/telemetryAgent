"""H0 contract tests: registry, result parsers, /connect fields, sandbox I/O.

These pin the §3 surface John and Jude code against. They use no adapters
(the first lands in H1) and mock GitHub/models; the sandbox read/write
test runs against real Docker file I/O (no image needed).
"""

import io
import os
import sys
import tarfile
import unittest
from unittest import mock

from core.connections import github as github_conn
from core.ingest.traceback import TracebackInfo
from core.repo_fix.lang import __init__ as registry  # noqa: F401  (package import check)
from core.repo_fix.lang import (
    all_adapters,
    by_name,
    detect_repo,
    parse,
    refined_name,
)
from core.repo_fix.lang.results import (
    parse_go_test_json,
    parse_jest_json,
    parse_junit_xml,
)
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

    def test_typescript_detected_not_autofixable_yet(self):
        result = self._check(
            "TypeScript", ["package.json", "tsconfig.json", "src/a.ts"]
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["language"], "typescript")
        self.assertFalse(result["autofix"])  # John's adapter not landed

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


if __name__ == "__main__":
    unittest.main()
