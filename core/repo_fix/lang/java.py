"""Java + Kotlin adapter: JVM behaviour behind the §3 protocol (L-J3).

One object serves both languages (the wire format is identical): `parse`
presets `kotlin` when `.kt` frames or a `kotlin.*` exception appear, and
the registry's aliases + `refined_name` do the rest. `repro_test_path`
picks the extension from the located file (Kotlin when `.kt`).
"""

from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional, Tuple

from core.ingest.traceback import Frame, TracebackInfo
from core.repo_fix.lang.base import SuiteResult
from core.repo_fix.lang.results import parse_junit_xml

#: `Exception in thread "main" <exc>` — uncaught throws print this head.
_THREAD_RE = re.compile(r'^Exception in thread "([^"]*)"\s+(.+)$')

#: Bare `<qualified.Type>: msg` / `<qualified.Type>` (Caused/Suppressed
#: and frame lines excluded by the caller, not the pattern).
_BARE_RE = re.compile(r"^([A-Za-z_][\w$]*(?:\.[\w$]+)*)(?::\s?(.*))?$")

#: `	at com.foo.Bar.m(File.java:42)` — optional `module/` qualifier,
#: `(Native Method)` / `(Unknown Source)` carry no location.
_FRAME_RE = re.compile(
    r"^\s*at\s+(?:[\w.]+\/)?"
    r"([\w$]+(?:\.[\w$]+)*)\."
    r"([\w$<>]+)"
    r"\(([^)]*)\)\s*$"
)

#: `... 2 more` — frames elided as identical to the enclosing trace.
_ELISION_RE = re.compile(r"^\.\.\.\s+\d+\s+more\s*$")

#: Surefire per-class lines name the XML reports to read.
_RUNNING_RE = re.compile(r"^Running ([\w$.]+)\s*$", re.MULTILINE)

#: `Tests run: 20, Failures: 1, Errors: 0, Skipped: 0` (stdout fallback).
_SUMMARY_RE = re.compile(
    r"Tests run:\s*(\d+),\s*Failures:\s*(\d+),\s*Errors:\s*(\d+)"
    r"(?:,\s*Skipped:\s*(\d+))?"
)

#: `[ERROR]   com.example.FooTest.bar:45 ...` (stdout fallback ids).
_ERROR_ID_RE = re.compile(r"^\[ERROR\]\s+([\w$.]+\.[\w$]+)", re.MULTILINE)

#: `20 tests completed, 1 failed` (Gradle summary).
_GRADLE_SUMMARY_RE = re.compile(
    r"(\d+)\s+tests?\s+completed(?:,\s*(\d+)\s+failed)?"
    r"(?:,\s*(\d+)\s+skipped)?"
)

#: `CartTest > emptyCart FAILED` (Gradle failure ids; spaces only —
#: `\s` would glue `> Task :test FAILED` onto the summary line above).
_GRADLE_FAIL_RE = re.compile(
    r"^([^>\n]+?)[ ]*>[ ]*([^>\n]+?)[ ]+FAILED[ ]*$", re.MULTILINE
)

_JAVA_EXTS = (".java", ".kt")

#: Full online run (failures ignored): warms surefire providers + deps so
#: the offline suite works. Bare `-DskipTests` does NOT prefetch providers
#: under this image's Maven (verified live: offline suite failed resolving
#: surefire-junit-platform:3.2.5); ignoring failures keeps red-baseline
#: repos installing (the offline baseline still measures truly).
_MAVEN_INSTALL = ["mvn", "-B", "-q", "-Dmaven.test.failure.ignore=true", "test"]
_MAVEN_SUITE = ["mvn", "-B", "-o", "test"]

_GRADLE_BUILD_FILES = ("build.gradle", "build.gradle.kts")

REPRO_RULES = (
    "Write a JUnit 5 test: declare the same package as the class under "
    "test, import org.junit.jupiter.api.Test and static "
    "org.junit.jupiter.api.Assertions.*, annotate one method with @Test."
)


def _split_head(line: str) -> Optional[Tuple[str, str]]:
    """(exc_type, exc_value) for a head line, or None when not a head."""
    stripped = line.strip()
    if stripped.startswith(("Caused by:", "Suppressed:", "...", "at ")):
        return None
    thread = _THREAD_RE.match(stripped)
    if thread:
        stripped = thread.group(2).strip()
    found = _BARE_RE.match(stripped)
    if not found:
        return None
    return found.group(1), (found.group(2) or "").strip()


def _split_frame(line: str) -> Optional[Tuple[str, str, int]]:
    """(qualified_func, file, lineno) for an `at` line ("" file if none)."""
    found = _FRAME_RE.match(line)
    if not found:
        return None
    func = f"{found.group(1)}.{found.group(2)}"
    where = found.group(3).strip()
    if ":" in where:
        name, _, lineno = where.rpartition(":")
        try:
            return func, name, int(lineno)
        except ValueError:
            return None
    return func, "", 0  # Native Method / Unknown Source


def _is_kotlin(exc_type: str, files: List[str]) -> bool:
    if exc_type.startswith(("kotlin.", "kotlinx.")):
        return True
    return any(name.endswith(".kt") for name in files)


class _JvmAdapter:
    """Java + Kotlin: one parser, one runner family, two extensions."""

    name = "java"
    image = "jvm"
    install_timeout_s = 900
    suite_timeout_s = 900

    def detect(self, paths: List[str]) -> int:
        score = min(20, len(self.source_files(paths)))
        basenames = {path.rsplit("/", 1)[-1] for path in paths}
        if "pom.xml" in basenames or basenames & set(_GRADLE_BUILD_FILES):
            score += 10
        return score

    def trace_start(self, line: str) -> bool:
        # Streaming needs a stricter head than parse: a bare single word
        # (`more`, `done`, `notes: x`) must not open a trace. Real JVM
        # heads are qualified (`Class.getName()`); default-package customs
        # still parse when windowed directly, they just don't start one.
        head = _split_head(line)
        if head is None:
            return False
        if _THREAD_RE.match(line.strip()):
            return True
        return "." in head[0]

    def trace_continues(self, line: str) -> bool:
        stripped = line.strip()
        if stripped.startswith("at "):
            return True
        if stripped.startswith(("Caused by:", "Suppressed:")):
            return True
        if _ELISION_RE.match(stripped):
            return True
        return False

    def parse_trace(self, text: str) -> Optional[TracebackInfo]:
        """JVM trace: root cause wins, `... N more` skipped, no tail junk."""
        exc_type = ""
        exc_value = ""
        frames: List[Frame] = []
        seen_head = False
        last_meaningful = ""
        for raw_line in text.splitlines():
            line = raw_line.rstrip("\n")
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("Caused by:"):
                cause = _split_head(stripped[len("Caused by:"):].strip())
                if cause is not None:
                    exc_type, exc_value = cause  # root cause wins
                    seen_head = True
                last_meaningful = stripped
                continue
            if stripped.startswith("Suppressed:"):
                last_meaningful = stripped  # side exception: keep frames only
                continue
            if _ELISION_RE.match(stripped):
                last_meaningful = stripped  # identical to the parent: skip
                continue
            split = _split_frame(line)
            if split is not None:
                func, name, lineno = split
                frames.append(Frame(file=name, line=lineno, func=func))
                last_meaningful = stripped
                continue
            head = _split_head(line)
            if head is not None and not seen_head:
                exc_type, exc_value = head
                seen_head = True
                last_meaningful = stripped
                continue
            # Interior junk is tolerated (real logs interleave); a junk
            # TAIL means the trace already ended — the assembler completes
            # without this line instead.
            last_meaningful = ""
        if not seen_head or not frames:
            return None
        if not last_meaningful:
            return None
        language = (
            "kotlin"
            if _is_kotlin(exc_type, [frame.file for frame in frames])
            else "java"
        )
        return TracebackInfo(
            exc_type=exc_type, exc_value=exc_value, frames=frames,
            raw=text, language=language,
        )

    def map_frame(
        self, frame_file: str, func: str, paths: List[str]
    ) -> Optional[str]:
        if not frame_file or frame_file in ("Native Method", "Unknown Source"):
            return None
        name = str(frame_file).rsplit("/", 1)[-1]
        parts = [part for part in str(func).split(".") if part]
        pkg_path = "/".join(parts[:-2]) if len(parts) > 2 else ""
        roots = ("src/main/java", "src/main/kotlin")
        for path in paths:
            for root in roots:
                if pkg_path:
                    if path == f"{root}/{pkg_path}/{name}" or path.endswith(
                        f"/{root}/{pkg_path}/{name}"
                    ):
                        return path
                elif path == f"{root}/{name}" or path.endswith(f"/{root}/{name}"):
                    return path
        # Default package at the repo root (bare `javac` schoolbook code).
        if not pkg_path and name in paths:
            return name
        return None

    def source_files(self, paths: List[str]) -> List[str]:
        return [path for path in paths if path.endswith(_JAVA_EXTS)]

    def _basenames(self, paths: List[str]) -> set:
        return {path.rsplit("/", 1)[-1] for path in paths}

    def _is_maven(self, paths: List[str]) -> bool:
        return "pom.xml" in self._basenames(paths)

    def _gradle_bin(self, paths: List[str]) -> str:
        if "gradlew" in self._basenames(paths):
            return "./gradlew"
        return "gradle"

    def _is_gradle(self, paths: List[str]) -> bool:
        return bool(self._basenames(paths) & set(_GRADLE_BUILD_FILES))

    def install_cmds(self, paths: List[str]) -> List[List[str]]:
        if self._is_maven(paths):
            return [list(_MAVEN_INSTALL)]
        if self._is_gradle(paths):
            return [[self._gradle_bin(paths), "--no-daemon", "testClasses"]]
        return []

    def suite_cmd(self, paths: List[str]) -> List[str]:
        if self._is_maven(paths):
            return list(_MAVEN_SUITE)
        if self._is_gradle(paths):
            return [self._gradle_bin(paths), "--no-daemon", "--offline", "test"]
        return list(_MAVEN_SUITE)  # no build file: fail loudly, then draft

    def single_test_cmd(
        self, test_relpath: str, paths: List[str]
    ) -> List[str]:
        base = test_relpath.rsplit("/", 1)[-1]
        classname = base[:-5] if base.endswith(".java") else base[:-3]
        if self._is_maven(paths):
            return ["mvn", "-B", "-o", f"-Dtest={classname}", "test"]
        return [
            self._gradle_bin(paths), "--no-daemon", "--offline",
            "--tests", f"*{classname}", "test",
        ]

    def parse_results(
        self, stdout: str, stderr: str, read_file: Callable[[str], Optional[str]]
    ) -> SuiteResult:
        text = str(stdout) + "\n" + str(stderr)
        if "Task :test" in text or "tests completed" in text:
            return self._parse_gradle(text)
        return self._parse_maven(text, read_file)

    def _parse_maven(
        self, text: str, read_file: Callable[[str], Optional[str]]
    ) -> SuiteResult:
        total = passed = failed = 0
        failed_ids: List[str] = []
        errored = False
        saw_xml = False
        for classname in dict.fromkeys(_RUNNING_RE.findall(text)):
            try:
                xml = read_file(f"target/surefire-reports/TEST-{classname}.xml")
            except Exception:
                xml = None
            if not xml:
                continue
            saw_xml = True
            result = parse_junit_xml(xml)
            total += result.total
            passed += result.passed
            failed += result.failed
            failed_ids.extend(result.failed_ids)
            errored = errored or result.errored
        if saw_xml:
            return SuiteResult(
                total=total, passed=passed, failed=failed,
                failed_ids=failed_ids, errored=errored,
            )
        # Fallback (no XML): the LAST summary wins — surefire repeats
        # the same counts (per-class line + final summary), so summing
        # would double-count; ids still come from every ERROR line.
        last = None
        for match in _SUMMARY_RE.finditer(text):
            last = match
        failed_ids.extend(_ERROR_ID_RE.findall(text))
        if last is not None:
            total = int(last.group(1))
            failed = int(last.group(2)) + int(last.group(3))
            skipped = int(last.group(4) or 0)
            return SuiteResult(
                total=total, passed=max(0, total - failed - skipped),
                failed=failed, failed_ids=failed_ids,
            )
        return SuiteResult(
            total=0, passed=0, failed=0, failed_ids=[], errored=True,
        )

    def _parse_gradle(self, text: str) -> SuiteResult:
        match = None
        for candidate in _GRADLE_SUMMARY_RE.finditer(text):
            match = candidate  # last summary wins (final task outcome)
        if match is None:
            return SuiteResult(
                total=0, passed=0, failed=0, failed_ids=[], errored=True,
            )
        total = int(match.group(1))
        failed = int(match.group(2) or 0)
        skipped = int(match.group(3) or 0)
        failed_ids = [
            f"{cls.strip()}.{method.strip()}"
            for cls, method in _GRADLE_FAIL_RE.findall(text)
        ]
        return SuiteResult(
            total=total, passed=max(0, total - failed - skipped),
            failed=failed, failed_ids=failed_ids,
        )

    def _repro_package(self, paths: List[str], located: List[str]) -> str:
        for candidate in [*located, *paths]:
            for root in ("src/main/java/", "src/main/kotlin/"):
                index = candidate.find(root)
                if index < 0:
                    continue
                rest = candidate[index + len(root):]
                if "/" not in rest:
                    continue
                pkg = rest.rsplit("/", 1)[0]
                if pkg:
                    return pkg.replace("/", ".")
        return ""

    def repro_test_path(
        self, fingerprint: str, paths: List[str], located: List[str]
    ) -> str:
        kotlin = any(
            path.endswith(".kt") for path in [*located, *paths]
        )
        ext = "kt" if kotlin else "java"
        root = f"src/test/{'kotlin' if kotlin else 'java'}"
        package = self._repro_package(paths, located)
        stem = f"TaRepro{fingerprint[:12]}Test.{ext}"
        if package:
            return f"{root}/{package.replace('.', '/')}/{stem}"
        return f"{root}/{stem}"

    def repro_rules(self) -> str:
        return REPRO_RULES

    def looks_like_test(self, code: str) -> bool:
        return "@Test" in code


ADAPTER = _JvmAdapter()
