"""Rust language adapter (L-D2).

Parses both Rust panic formats (§1.1): the Rust ≥1.73
`thread '…' panicked at src/x.rs:L:C:` head (message on the next line,
optional ` (ThreadId)` — current rustc prints one) and the older
`panicked at 'msg', src/x.rs:L:C` head, plus `RUST_BACKTRACE=1` frames
(`   N: symbol` / `             at ./src/x.rs:L:C`).

Frame order is throw-site-first: the panic location always leads (so
`keywords_for` and `match_frames` see the crashing file first), then the
backtrace locations in printed order. `/rustc/…` std frames are kept for
display but never locate code (`map_frame` refuses them).

Assembler note (L-J2): `trace_continues` accepts structural lines only.
The panic message is the single non-blank line after a colon-terminated
head — the assembler must take it like the forwarder's `_prev_rust_head`
rule, or `exc_value` is lost. Heads always start a fresh trace.
"""

from __future__ import annotations

import re
from typing import Callable, List, Optional

from core.ingest.traceback import Frame, TracebackInfo
from core.repo_fix.lang.base import SuiteResult

#: Both panic heads. Group 1 is the legacy inline message (None on the
#: new format); groups 2-4 are the panic location file/line/col.
_PANIC_RE = re.compile(
    r"^thread '[^']*'(?: \(\d+\))? panicked at "
    r"(?:'([^']*)', )?(\S+?):(\d+):(\d+):?\s*$"
)

#: `   0: proof_shop_rust::cart::summary` (symbol may be anything).
_SYMBOL_RE = re.compile(r"^\s*\d+:\s+(\S.*?)\s*$")

#: `             at ./src/cart.rs:70:19` (col optional).
_LOCATION_RE = re.compile(r"^\s*at\s+(\S+?):(\d+)(?::(\d+))?\s*$")

#: `test result: ok. 13 passed; 0 failed; …` / `FAILED. 12 passed; 1 failed`.
_RESULT_RE = re.compile(
    r"test result:\s*(?:ok|FAILED)\.\s*(\d+) passed;\s*(\d+) failed"
)

#: `test cart::tests::x ... FAILED` (doctests: `test src/a.rs - x (line N)`).
_FAILED_TEST_RE = re.compile(r"^test (.+) \.\.\. FAILED\s*$")

_REPRO_PREFIX = "ta_repro"


class _RustAdapter:
    """§3 adapter for Rust; stateless (no manifest hook needed)."""

    name = "rust"
    image = "rust"
    install_timeout_s = 900
    suite_timeout_s = 900

    # -- repo matching -------------------------------------------------

    def detect(self, paths: List[str]) -> int:
        score = len(self.source_files(paths))
        if any(path.rsplit("/", 1)[-1] == "Cargo.toml" for path in paths):
            score += 5
        return score

    def source_files(self, paths: List[str]) -> List[str]:
        return [path for path in paths if path.endswith(".rs")]

    def map_frame(
        self, frame_file: str, func: str, paths: List[str]
    ) -> Optional[str]:
        _ = func  # Rust frames carry paths; suffix match suffices.
        norm = str(frame_file).replace("\\", "/")
        if norm.startswith("./"):
            norm = norm[2:]
        if norm.startswith("/rustc/"):
            return None  # std frames never locate repo code
        parts = [part for part in norm.split("/") if part]
        for index in range(len(parts)):
            suffix = "/".join(parts[index:])
            if suffix in paths:
                return suffix
        return None

    # -- trace detection ------------------------------------------------

    def trace_start(self, line: str) -> bool:
        return _PANIC_RE.match(line.strip()) is not None

    def trace_continues(self, line: str) -> bool:
        stripped = line.strip()
        if not stripped:
            return False
        if self.trace_start(line):
            return False  # a new head ends the previous trace
        if stripped == "stack backtrace:":
            return True
        if re.match(r"^\d+:\s", stripped):
            return True
        if stripped.startswith("at ") and re.search(r":\d+", stripped):
            return True
        if stripped.startswith("note: "):
            return True
        return False

    # -- trace parsing --------------------------------------------------

    def parse_trace(self, text: str) -> Optional[TracebackInfo]:
        """Parse joined panic text; None unless it holds a Rust head."""
        lines = text.splitlines()
        head_at: Optional[int] = None
        legacy_msg: Optional[str] = None
        head_file = ""
        head_line = 0
        for index, raw in enumerate(lines):
            match = _PANIC_RE.match(raw.strip())
            if match is None:
                continue
            head_at = index
            legacy_msg = match.group(1)
            head_file = match.group(2)
            try:
                head_line = int(match.group(3))
            except ValueError:
                head_line = 0
            break
        if head_at is None:
            return None
        if head_file.startswith("./"):
            head_file = head_file[2:]
        frames = self._parse_frames(lines, head_at)
        if legacy_msg is not None:
            exc_value = legacy_msg
        else:
            exc_value = self._message_after(lines, head_at)
        head_func = ""
        for frame in frames:
            if not frame.file.startswith("/rustc/"):
                head_func = frame.func
                break
        frames = [Frame(file=head_file, line=head_line, func=head_func)] + frames
        return TracebackInfo(
            exc_type="panic",
            exc_value=exc_value,
            frames=frames,
            raw=text,
            language="rust",
        )

    @staticmethod
    def _is_structural(stripped: str) -> bool:
        return (
            stripped == "stack backtrace:"
            or re.match(r"^\d+:\s", stripped) is not None
            or (
                stripped.startswith("at ")
                and re.search(r":\d+", stripped) is not None
            )
            or stripped.startswith("note: ")
            or _PANIC_RE.match(stripped) is not None
        )

    @classmethod
    def _message_after(cls, lines: List[str], head_at: int) -> str:
        """First message line after a new-format head (may be multi-line)."""
        for raw in lines[head_at + 1 :]:
            stripped = raw.strip()
            if not stripped:
                continue
            if cls._is_structural(stripped):
                break
            return stripped
        return ""

    @classmethod
    def _parse_frames(cls, lines: List[str], head_at: int) -> List[Frame]:
        """`symbol` + `at path:L:C` pairs after the head, in order."""
        frames: List[Frame] = []
        index = head_at + 1
        while index < len(lines):
            symbol = _SYMBOL_RE.match(lines[index].strip())
            if symbol is None:
                index += 1
                continue
            location = None
            if index + 1 < len(lines):
                location = _LOCATION_RE.match(lines[index + 1].strip())
            if location is not None:
                path = location.group(1)
                if path.startswith("./"):
                    path = path[2:]
                try:
                    lineno = int(location.group(2))
                except ValueError:
                    lineno = 0
                frames.append(
                    Frame(file=path, line=lineno, func=symbol.group(1))
                )
                index += 2
            else:
                index += 1  # symbol without a location locates nothing
        return frames

    # -- build & test ----------------------------------------------------

    def install_cmds(self, paths: List[str]) -> List[List[str]]:
        if not any(
            path.rsplit("/", 1)[-1] == "Cargo.toml" for path in paths
        ):
            return []
        # Network on: fetch deps, then compile the test targets once so
        # the offline suite step never waits on a build (§1.1).
        return [["cargo", "fetch"], ["cargo", "test", "--no-run"]]

    def suite_cmd(self, paths: List[str]) -> List[str]:
        _ = paths
        return ["cargo", "test", "--offline", "--no-fail-fast"]

    def single_test_cmd(
        self, test_relpath: str, paths: List[str]
    ) -> List[str]:
        _ = paths
        if test_relpath.startswith("tests/") and test_relpath.endswith(".rs"):
            stem = test_relpath.rsplit("/", 1)[-1][:-3].replace("-", "_")
            return ["cargo", "test", "--offline", "--test", stem]
        # Inline `#[cfg(test)]` module: only one repro module exists at a
        # time, so the shared prefix filters it on any target.
        return ["cargo", "test", "--offline", _REPRO_PREFIX]

    def parse_results(
        self, stdout: str, stderr: str, read_file: Callable[[str], Optional[str]]
    ) -> SuiteResult:
        _ = read_file  # cargo prints everything; no report files.
        text = str(stdout) + "\n" + str(stderr)
        passed = failed = 0
        saw_results = False
        for line in text.splitlines():
            match = _RESULT_RE.search(line)
            if match:
                saw_results = True
                passed += int(match.group(1))
                failed += int(match.group(2))
        if not saw_results:
            # No `test result:` line: compile error or the runner died.
            return SuiteResult(
                total=0, passed=0, failed=0, failed_ids=[], errored=True
            )
        failed_ids: List[str] = []
        for line in text.splitlines():
            match = _FAILED_TEST_RE.match(line.strip())
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
        name = f"{_REPRO_PREFIX}_{fingerprint[:12]}"
        binary_only = "src/lib.rs" not in paths
        bin_target = bool(located and located[0].startswith("src/bin/"))
        if not binary_only and not bin_target:
            return f"tests/{name}.rs"
        # No lib target (or the crash is in one): an integration test
        # cannot import the code, so the repro is an inline module
        # appended to the located file (§1.1).
        if located:
            return located[0]
        for path in paths:
            if path == "src/main.rs":
                return path
        for path in sorted(paths):
            if path.startswith("src/") and path.endswith(".rs"):
                return path
        return "src/main.rs"

    def repro_rules(self) -> str:
        return (
            "Rust (cargo test). If the test file is tests/*.rs it is an "
            "integration test: `use` the target crate by its Cargo.toml "
            "[package] name with `-` replaced by `_`, define `#[test] fn "
            "…` functions, plain asserts only. Otherwise the file is an "
            "existing source file: append `#[cfg(test)] mod ta_repro_… { "
            "use super::*; … }` at the end (one module, that name). The "
            "test MUST fail on the current code and pass once the bug is "
            "fixed; no network, no threads, deterministic."
        )

    def looks_like_test(self, code: str) -> bool:
        return "#[test]" in code


ADAPTER = _RustAdapter()
