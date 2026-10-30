"""Python adapter: today's behaviour behind the §3 protocol (L-J1).

Pure move: every rule here is copied from run.py / generate.py /
snapshot.py / locate.py without changes. The pipeline calls this instead
of the module helpers; the legacy names stay in run.py as shims because
the frozen tests import them.
"""

from __future__ import annotations

import re
from typing import Callable, List, Optional

from core.ingest.traceback import TracebackInfo, parse_traceback
from core.repo_fix.lang.base import SuiteResult

#: `python -m` puts the repo root on sys.path; bare `pytest` does not, so
#: `from app.x import y` in tests/ fails collection on common layouts.
PYTEST_BASE = ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]


def _python_files(paths: List[str]) -> List[str]:
    return [path for path in paths if path.endswith(".py")]


def _has_requirements(paths: List[str]) -> bool:
    names = {path.rsplit("/", 1)[-1] for path in paths}
    return "requirements.txt" in names


def _has_packaging(paths: List[str]) -> bool:
    names = {path.rsplit("/", 1)[-1] for path in paths}
    return bool(names & {"setup.py", "setup.cfg", "pyproject.toml"})

#: Appended to the generic repro prompt (§3: rules, not the prompt).
REPRO_RULES = "Write a pytest file: define at least one test_ function."


class _PythonAdapter:
    """The reference adapter; every method mirrors legacy behaviour."""

    name = "python"
    image = "python"
    install_timeout_s = 300
    suite_timeout_s = 600

    def detect(self, paths: List[str]) -> int:
        score = len(self.source_files(paths))
        if _has_requirements(paths) or _has_packaging(paths):
            score += 5
        return score

    def trace_start(self, line: str) -> bool:
        return line.strip() == "Traceback (most recent call last):"

    def trace_continues(self, line: str) -> bool:
        # Indented frame lines; the final `ExcType: message` line does NOT
        # continue (the assembler takes one trailing line — see L-J2).
        if line[:1] in (" ", "\t"):
            return True
        stripped = line.strip()
        return stripped.startswith("File ") or stripped.startswith(
            (
                "During handling",
                "The above exception",
                "Traceback (most recent",
            )
        )

    def parse_trace(self, text: str) -> Optional[TracebackInfo]:
        # Claim only Python-shaped traces: the bare `Exc: msg` pattern
        # also matches V8/Go/JVM/Rust/PHP heads, and python sorts first
        # in registry.parse — without this gate no other language routes.
        info = parse_traceback(text)
        if info is None:
            return None
        if info.frames:
            return info
        if "Traceback (most recent call last):" in text:
            return info
        return None

    def map_frame(
        self, frame_file: str, func: str, paths: List[str]
    ) -> Optional[str]:
        _ = func  # Python frames carry full paths; suffix match suffices.
        parts = [
            part
            for part in str(frame_file).replace("\\", "/").split("/")
            if part
        ]
        for index in range(len(parts)):
            suffix = "/".join(parts[index:])
            if suffix in paths:
                return suffix
        return None

    def source_files(self, paths: List[str]) -> List[str]:
        return [path for path in paths if path.endswith(".py")]

    def install_cmds(self, paths: List[str]) -> List[List[str]]:
        # No --target: the Docker exec sets PIP_TARGET=/work/.deps (fresh
        # containers would lose system installs); Modal installs system-wide.
        if _has_requirements(paths):
            req = next(
                path
                for path in paths
                if path.rsplit("/", 1)[-1] == "requirements.txt"
            )
            return [["pip", "install", "-r", req]]
        if _has_packaging(paths):
            return [["pip", "install", "-e", "."]]
        return []

    def suite_cmd(self, paths: List[str]) -> List[str]:
        _ = paths
        return [*PYTEST_BASE, "--tb=no", "-rf"]

    def single_test_cmd(
        self, test_relpath: str, paths: List[str]
    ) -> List[str]:
        _ = paths
        return [*PYTEST_BASE, "--tb=short", test_relpath]

    def parse_results(
        self, stdout: str, stderr: str, read_file: Callable[[str], Optional[str]]
    ) -> SuiteResult:
        _ = read_file  # pytest prints everything; no report files.
        text = str(stdout) + "\n" + str(stderr)
        passed = failed = 0
        tail = [
            line.strip() for line in text.splitlines() if line.strip()
        ][-5:]
        for line in tail:
            for count, word in re.findall(
                r"(\d+)\s+(passed|failed|error)", line
            ):
                if word == "passed":
                    passed += int(count)
                else:
                    failed += int(count)
        failed_ids: List[str] = []
        for line in text.splitlines():
            match = re.match(
                r"^(?:FAILED|ERROR)\s+(\S+)", line.strip()
            )
            if match:
                failed_ids.append(match.group(1))
        return SuiteResult(
            total=passed + failed,
            passed=passed,
            failed=failed,
            failed_ids=failed_ids,
        )

    def repro_test_path(
        self, fingerprint: str, paths: List[str], located: List[str]
    ) -> str:
        _ = (paths, located)
        return f"tests/test_telemetry_agent_{fingerprint[:12]}.py"

    def repro_rules(self) -> str:
        return REPRO_RULES

    def looks_like_test(self, code: str) -> bool:
        return "def test_" in code


ADAPTER = _PythonAdapter()
