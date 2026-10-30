"""Go adapter: panic traces + `go test -json` behind the §3 protocol (L-J4)."""

from __future__ import annotations

import re
from typing import Callable, List, Optional

from core.ingest.traceback import Frame, TracebackInfo
from core.repo_fix.lang.base import SuiteResult
from core.repo_fix.lang.results import parse_go_test_json

#: `log.Printf` timestamps its first line (`2026/10/30 15:21:19 panic:`).
_TS_RE = re.compile(r"^\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)? ")

#: `goroutine 19 [running]:`
_GOROUTINE_RE = re.compile(r"^goroutine \d+ \[[^\]]+\]:\s*$")

#: `\t/app/shop/cart.go:70 +0x1b8` (offset optional).
_FILE_RE = re.compile(r"^\s*(\S+?):(\d+)(?: \+0x[0-9a-fA-F]+)?\s*$")

REPRO_RULES = (
    "Write a Go test in the SAME package as the suspect file (same "
    "directory): one function named TestTaRepro... (e.g. "
    "func TestTaReproEmptyCart(t *testing.T)) that fails on the current "
    "code and passes once fixed; use the testing package only."
)


def _strip_ts(line: str) -> str:
    return _TS_RE.sub("", line, count=1)


def _is_func_line(line: str) -> bool:
    if not line or line[0].isspace():
        return False
    stripped = line.strip()
    if stripped.startswith("--- "):
        return False
    return "(" in stripped and stripped.endswith(")")


class _GoAdapter:
    name = "go"
    image = "go"
    install_timeout_s = 300
    suite_timeout_s = 600

    def detect(self, paths: List[str]) -> int:
        score = min(20, len(self.source_files(paths)))
        if any(path.rsplit("/", 1)[-1] == "go.mod" for path in paths):
            score += 10
        return score

    def trace_start(self, line: str) -> bool:
        return _strip_ts(line.strip()).startswith("panic:")

    def trace_continues(self, line: str) -> bool:
        if not line.strip():
            return True
        stripped = line.strip()
        if _GOROUTINE_RE.match(stripped):
            return True
        if stripped.startswith("created by "):
            return True
        if _FILE_RE.match(line):
            return True
        return _is_func_line(line)

    def parse_trace(self, text: str) -> Optional[TracebackInfo]:
        """Panic head + `func`/`file:line` pairs; `created by` kept bare."""
        exc_value = ""
        seen_head = False
        frames: List[Frame] = []
        pending: Optional[str] = None
        last_frameish = False
        for raw_line in text.splitlines():
            line = _strip_ts(raw_line.rstrip("\n"))
            stripped = line.strip()
            if not stripped:
                continue
            if not seen_head:
                head = stripped if stripped.startswith("panic:") else ""
                if head:
                    exc_value = re.sub(
                        r" \[recovered\]$", "",
                        head[len("panic:"):].strip(),
                    )
                    seen_head = True
                last_frameish = False
                continue
            if _GOROUTINE_RE.match(stripped):
                pending = None
                last_frameish = False
                continue
            if stripped.startswith("created by "):
                pending = None  # its file line stands alone (func "")
                last_frameish = False
                continue
            file_match = _FILE_RE.match(line)
            if file_match is not None:
                try:
                    lineno = int(file_match.group(2))
                except ValueError:
                    pending = None
                    last_frameish = False
                    continue
                frames.append(Frame(
                    file=file_match.group(1), line=lineno,
                    func=pending or "",
                ))
                pending = None
                last_frameish = True
                continue
            if _is_func_line(line):
                pending = stripped
                last_frameish = True
                continue
            pending = None
            last_frameish = False  # interior junk tolerated, tail ends it
        if not seen_head or not frames or not last_frameish:
            return None
        return TracebackInfo(
            exc_type="panic", exc_value=exc_value, frames=frames,
            raw=text, language="go",
        )

    def map_frame(
        self, frame_file: str, func: str, paths: List[str]
    ) -> Optional[str]:
        parts = [
            part
            for part in str(frame_file).replace("\\", "/").split("/")
            if part
        ]
        for index in range(len(parts)):
            suffix = "/".join(parts[index:])
            if suffix in paths:
                return suffix
        # Fallback: strip the module prefix segment by segment
        # (`github.com/acme/app/shop/cart.go` → `shop/cart.go`).
        import_path = str(func).rsplit(".", 1)[0].replace("\\", "/")
        segs = [seg for seg in import_path.split("/") if seg]
        name = parts[-1] if parts else ""
        if not name:
            return None
        for index in range(len(segs)):
            candidate = "/".join([*segs[index:], name])
            if candidate in paths:
                return candidate
        return None

    def source_files(self, paths: List[str]) -> List[str]:
        return [path for path in paths if path.endswith(".go")]

    def install_cmds(self, paths: List[str]) -> List[List[str]]:
        if any(path.rsplit("/", 1)[-1] == "go.mod" for path in paths):
            return [["go", "mod", "download"]]
        return []

    def suite_cmd(self, paths: List[str]) -> List[str]:
        _ = paths
        return ["go", "test", "./...", "-json"]

    def single_test_cmd(
        self, test_relpath: str, paths: List[str]
    ) -> List[str]:
        _ = paths
        directory = test_relpath.rsplit("/", 1)[0] if "/" in test_relpath else ""
        target = f"./{directory}" if directory else "."
        return ["go", "test", target, "-run", "TestTaRepro", "-json"]

    def parse_results(
        self, stdout: str, stderr: str, read_file: Callable[[str], Optional[str]]
    ) -> SuiteResult:
        _ = (stderr, read_file)  # -json carries everything on stdout
        return parse_go_test_json(str(stdout))

    def repro_test_path(
        self, fingerprint: str, paths: List[str], located: List[str]
    ) -> str:
        _ = paths
        name = f"ta_repro_{fingerprint[:12]}_test.go"
        if located and "/" in located[0]:
            return f"{located[0].rsplit('/', 1)[0]}/{name}"
        return name

    def repro_rules(self) -> str:
        return REPRO_RULES

    def looks_like_test(self, code: str) -> bool:
        return "func TestTaRepro" in code


ADAPTER = _GoAdapter()
