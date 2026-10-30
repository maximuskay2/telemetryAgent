"""PHP language adapter (L-D3).

Parses the CLI fatal shape (§1.1)
`PHP Fatal error:  Uncaught X: msg in /path/F.php:12` + `Stack trace:`
+ `#N /path/G.php(L): fn()` + `  thrown in …`, the bare `Fatal error:`
shutdown repeat, `PHP Parse error: … in f.php on line N`, `Next …`
chains (the FIRST block wins — PHP prints the root cause first, then
`Next <outer>`), and Laravel/Monolog `[stacktrace]` blocks
(`"exception":"[object] (Class(code: N): msg at f.php:L)\n[stacktrace]
\n#0 …"`).

Frame order is throw-site-first: the head location leads (with the `#0`
function), then the `#N` frames in printed order. `{main}` and
`[internal function]` frames carry no file and are skipped.

Pest vs PHPUnit is detected from paths (`tests/Pest.php` ⇒ Pest); the
adapter is stateless and defines no manifest hook.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Callable, List, Optional

from core.ingest.traceback import Frame, TracebackInfo
from core.repo_fix.lang.base import SuiteResult
from core.repo_fix.lang.results import parse_junit_xml

#: `PHP Fatal error:  Uncaught DivisionByZeroError: msg in /f.php:62`
#: (two spaces, `Uncaught` optional, bare `Fatal error:` repeat matches).
_CLI_HEAD_RE = re.compile(
    r"^(?:PHP\s+)?(?:Fatal error|Catchable fatal error)\s*:\s*"
    r"(?:Uncaught\s+)?([A-Za-z_\\][\w\\]*)\s*:\s*(.*)\s+in\s+(\S+):(\d+)\s*$"
)

#: `PHP Parse error:  syntax error, … in /f.php on line 5`.
_PARSE_HEAD_RE = re.compile(
    r"^(?:PHP\s+)?Parse error\s*:\s*(.*)\s+in\s+(\S+)\s+on\s+line\s+(\d+)\s*$"
)

#: `Next RuntimeException: msg in /f.php:12` (outer exceptions, skipped).
_NEXT_HEAD_RE = re.compile(
    r"^Next\s+([A-Za-z_\\][\w\\]*)\s*:\s*(.*)\s+in\s+(\S+):(\d+)\s*$"
)

#: `"exception":"[object] (Class(code: 0): msg at /f.php:11)` — the class
#: may be JSON-escaped (`Illuminate\\\\Log…`), normalised after matching.
_MONOLOG_HEAD_RE = re.compile(
    r'"exception"\s*:\s*"\[object\] \(\s*'
    r"([A-Za-z_\\][\w\\]*)\(code:\s*[^)]*\)\s*:\s*(.*)\s+at\s+(\S+):(\d+)\)"
)

#: `#0 /path/F.php(30): ProofShop\Cart::summary(Array)`.
_FRAME_RE = re.compile(r"^#(\d+)\s+(\S+?)\((\d+)\):\s*(\S+?)\s*\(")

#: SAPI/drain timestamp prefixes (`[Fri Oct 30 14:12:35 2026] …`) that the
#: PHP server SAPIs prepend to (at least the first) error line.
_LOG_PREFIX_RE = re.compile(r"^\[[^\]]*\]\s*")


def _unprefixed(stripped: str) -> str:
    return _LOG_PREFIX_RE.sub("", stripped, count=1)

_JUNIT_REPORT = "ta-results.xml"

#: `OK (20 tests, 31 assertions)` / `OK, but there were issues!`.
_PHPUNIT_OK_RE = re.compile(r"^OK(?:, but .*?)? \((?:No tests|(\d+) tests?)")

#: `Tests: 21, Assertions: 40, Failures: 1.` after `FAILURES!`/`ERRORS!`/…
_PHPUNIT_COUNT_RE = re.compile(
    r"^Tests:\s*(\d+),\s*Assertions:\s*\d+"
    r"(?:,\s*(?:Failures|Errors):\s*(\d+))?"
)

#: `Tests:    1 failed, 19 passed (20 assertions)` (Pest).
_PEST_COUNT_RE = re.compile(r"^Tests:\s*(\d+) failed,\s*(\d+) passed")

#: `1) ProofShop\Tests\ShopTest::test_empty_cart` (+ optional data set).
_FAILED_ID_RE = re.compile(r"^\d+\)\s+(\S+)")


def _leaf_junit_xml(text: str) -> str:
    """Rewrap nested JUnit so the shared parser counts each test once.

    PHPUnit nests suites (config > suite > class) with aggregate counts
    at every level; `parse_junit_xml` sums all levels and repeats every
    failed id. Flat reports (Surefire/Gradle) pass through untouched.
    """
    try:
        root = ET.fromstring(text.strip())
    except ET.ParseError:
        return text
    if root.tag == "testsuite":
        candidates = [root]
    elif root.tag == "testsuites":
        candidates = list(root.iter("testsuite"))
    else:
        return text
    leaves = [
        suite
        for suite in candidates
        if not any(child.tag == "testsuite" for child in suite)
    ]
    if len(leaves) == len(candidates):
        return text
    inner = "".join(
        ET.tostring(suite, encoding="unicode") for suite in leaves
    )
    return f"<testsuites>{inner}</testsuites>"

#: `FAILED  Tests\CartPestTest > empty cart …  DivisionByZeroError` (Pest
#: truncates long names with `…`, but truncation is stable per run).
_PEST_FAILED_RE = re.compile(r"^FAILED\s+(.*?)\s{2,}\S+\s*$")


class _PhpAdapter:
    """§3 adapter for PHP (PHPUnit or Pest); stateless."""

    name = "php"
    image = "php"
    install_timeout_s = 300
    suite_timeout_s = 600

    # -- repo matching -------------------------------------------------

    def detect(self, paths: List[str]) -> int:
        score = len(self.source_files(paths))
        if any(path.rsplit("/", 1)[-1] == "composer.json" for path in paths):
            score += 5
        return score

    def source_files(self, paths: List[str]) -> List[str]:
        # vendor/ is third-party code: never shown to the model, never
        # scored, never located.
        return [
            path
            for path in paths
            if path.endswith(".php") and "/vendor/" not in f"/{path}"
        ]

    @staticmethod
    def _is_vendor(path: str) -> bool:
        return "/vendor/" in f"/{path.replace(chr(92), '/')}"

    def map_frame(
        self, frame_file: str, func: str, paths: List[str]
    ) -> Optional[str]:
        _ = func  # PHP frames carry paths; suffix match suffices.
        norm = str(frame_file).replace("\\", "/")
        if norm.startswith("./"):
            norm = norm[2:]
        parts = [part for part in norm.split("/") if part]
        for index in range(len(parts)):
            suffix = "/".join(parts[index:])
            if suffix in paths:
                if self._is_vendor(suffix):
                    return None
                return suffix
        return None

    # -- trace detection ------------------------------------------------

    def trace_start(self, line: str) -> bool:
        stripped = line.strip()
        if not stripped:
            return False
        if re.match(
            r"^(?:PHP\s+)?(?:Fatal error|Parse error|Catchable fatal error)\s*:",
            _unprefixed(stripped),
        ):
            return True
        return _MONOLOG_HEAD_RE.search(stripped) is not None

    def trace_continues(self, line: str) -> bool:
        stripped = line.strip()
        if not stripped:
            return False
        if "[stacktrace]" in stripped:
            return True
        if self.trace_start(line):
            return False  # a new head ends the previous trace
        plain = _unprefixed(stripped)
        if plain == "Stack trace:":
            return True
        if re.match(r"^#\d+\s", plain):
            return True
        if plain.startswith("thrown in "):
            return True
        if plain.startswith("Next ") and ":" in plain:
            return True
        return False

    # -- trace parsing --------------------------------------------------

    def parse_trace(self, text: str) -> Optional[TracebackInfo]:
        """Parse joined PHP trace text; None without a PHP head."""
        lines = text.splitlines()
        head = self._first_head(lines)
        if head is None:
            return None
        exc_type, exc_value, head_file, head_line, head_at = head
        frames = self._parse_frames(lines, head_at)
        head_func = frames[0].func if frames else ""
        frames = [
            Frame(file=head_file, line=head_line, func=head_func)
        ] + frames
        return TracebackInfo(
            exc_type=exc_type,
            exc_value=exc_value,
            frames=frames,
            raw=text,
            language="php",
        )

    @classmethod
    def _first_head(cls, lines: List[str]):
        """First exception head wins (PHP prints the root cause first)."""
        for index, raw in enumerate(lines):
            stripped = raw.strip()
            plain = _unprefixed(stripped)
            match = _CLI_HEAD_RE.match(plain)
            if match:
                return (
                    match.group(1),
                    match.group(2).strip(),
                    match.group(3),
                    cls._lineno(match.group(4)),
                    index,
                )
            match = _PARSE_HEAD_RE.match(plain)
            if match:
                return (
                    "ParseError",
                    match.group(1).strip(),
                    match.group(2),
                    cls._lineno(match.group(3)),
                    index,
                )
            match = _NEXT_HEAD_RE.match(plain)
            if match:
                return (
                    match.group(1),
                    match.group(2).strip(),
                    match.group(3),
                    cls._lineno(match.group(4)),
                    index,
                )
            match = _MONOLOG_HEAD_RE.search(stripped)
            if match:
                return (
                    match.group(1).replace("\\\\", "\\"),
                    match.group(2).strip(),
                    match.group(3),
                    cls._lineno(match.group(4)),
                    index,
                )
        return None

    @staticmethod
    def _lineno(raw: str) -> int:
        try:
            return int(raw)
        except ValueError:
            return 0

    def _parse_frames(self, lines: List[str], head_at: int) -> List[Frame]:
        """`#N file(line): func()` lines after the head, in order."""
        frames: List[Frame] = []
        for raw in lines[head_at + 1 :]:
            stripped = raw.strip()
            if self.trace_start(raw):
                break  # a later head (chain outer, repeat, next entry)
            plain = _unprefixed(stripped)
            if plain.startswith("thrown in "):
                break
            if plain.startswith("Next "):
                break
            match = _FRAME_RE.match(plain)
            if match is None:
                continue  # `{main}`, blanks, `Stack trace:`, `"}`, …
            frames.append(
                Frame(
                    file=match.group(2),
                    line=self._lineno(match.group(3)),
                    func=match.group(4).replace("\\\\", "\\"),
                )
            )
        return frames

    # -- build & test ----------------------------------------------------

    @staticmethod
    def _uses_pest(paths: List[str]) -> bool:
        return "tests/Pest.php" in paths

    def install_cmds(self, paths: List[str]) -> List[List[str]]:
        if not any(
            path.rsplit("/", 1)[-1] == "composer.json" for path in paths
        ):
            return []
        return [["composer", "install", "--no-interaction", "--no-progress"]]

    def _runner(self, paths: List[str]) -> str:
        return "vendor/bin/pest" if self._uses_pest(paths) else "vendor/bin/phpunit"

    def suite_cmd(self, paths: List[str]) -> List[str]:
        return [self._runner(paths), "--log-junit", _JUNIT_REPORT]

    def single_test_cmd(
        self, test_relpath: str, paths: List[str]
    ) -> List[str]:
        return [self._runner(paths), test_relpath]

    def parse_results(
        self, stdout: str, stderr: str, read_file: Callable[[str], Optional[str]]
    ) -> SuiteResult:
        report = None
        try:
            report = read_file(_JUNIT_REPORT)
        except Exception:
            report = None
        if report:
            return parse_junit_xml(_leaf_junit_xml(report))
        return self._parse_stdout(str(stdout) + "\n" + str(stderr))

    @classmethod
    def _parse_stdout(cls, text: str) -> SuiteResult:
        passed = failed = 0
        matched = False
        for raw in text.splitlines():
            line = raw.strip()
            ok_match = _PHPUNIT_OK_RE.match(line)
            if ok_match:
                matched = True
                if ok_match.group(1) is not None:
                    passed = int(ok_match.group(1))
                continue
            count_match = _PHPUNIT_COUNT_RE.match(line)
            if count_match:
                matched = True
                total = int(count_match.group(1))
                failed = (
                    int(count_match.group(2))
                    if count_match.group(2) is not None
                    else 0
                )
                passed = max(0, total - failed)
                continue
            pest_match = _PEST_COUNT_RE.match(line)
            if pest_match:
                matched = True
                failed = int(pest_match.group(1))
                passed = int(pest_match.group(2))
        if not matched:
            return SuiteResult(
                total=0, passed=0, failed=0, failed_ids=[], errored=True
            )
        failed_ids: List[str] = []
        for raw in text.splitlines():
            line = raw.strip()
            match = _FAILED_ID_RE.match(line)
            if match is None:
                match = _PEST_FAILED_RE.match(line)
            if match and match.group(1) not in failed_ids:
                failed_ids.append(match.group(1))
        return SuiteResult(
            total=passed + failed,
            passed=passed,
            failed=failed,
            failed_ids=failed_ids,
        )

    # -- repro test -------------------------------------------------------

    def repro_test_path(
        self, fingerprint: str, paths: List[str], located: List[str]
    ) -> str:
        _ = (paths, located)
        return f"tests/TaRepro{fingerprint[:12]}Test.php"

    def repro_rules(self) -> str:
        return (
            "PHP (PHPUnit): declare the same `namespace …Tests;` as the "
            "neighbouring tests, `use PHPUnit\\Framework\\TestCase;`, "
            "`final class TaRepro…Test extends TestCase`, "
            "`public function test…(): void` methods, `$this->assert…` "
            "only. In Pest repos (tests/Pest.php in the layout) write "
            "`test('…', function () { … expect(…)->…; })` instead. The "
            "test MUST fail on the current code and pass once the bug "
            "is fixed; no network, no sleep, deterministic."
        )

    def looks_like_test(self, code: str) -> bool:
        phpunit = "extends TestCase" in code and "function test" in code
        pest_fn = re.search(r"(?:^|[^\w$>])test\s*\(", code) is not None or (
            re.search(r"(?:^|[^\w$>])it\s*\(", code) is not None
        )
        pest = pest_fn and ("expect" in code or "assert" in code)
        return phpunit or pest


ADAPTER = _PhpAdapter()
