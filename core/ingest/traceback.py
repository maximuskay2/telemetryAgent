"""Python traceback parsing + stream reassembly (J-R1).

The forwarder ships raw lines; batches can split a traceback across
requests. `TracebackAssembler` (one per connection, held by the pipeline)
joins them so a multi-line traceback becomes ONE event with parsed frames.
`parse_traceback` extracts the exception + frames from the joined text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

TRACEBACK_HEADER = "Traceback (most recent call last):"

#: Chained-exception separators: collecting continues past them.
CHAIN_RES = (
    re.compile(r"^During handling of the above exception, .*:$"),
    re.compile(r"^The above exception was the direct cause .*:$"),
    re.compile(r"^The above exception was the cause .*:$"),
)

#: `  File "/a/b.py", line 10, in func` (func may be `<module>`).
FRAME_RE = re.compile(
    r'^\s*File "([^"]+)", line (\d+), in (\S+)\s*$'
)

#: `ValueError: msg`, `module.Error: msg`, or a bare `KeyboardInterrupt`.
EXC_RE = re.compile(r"^([A-Za-z_][\w.]*)(?::\s?(.*))?$")

#: A traceback never exceeds this (force-complete past it).
MAX_TRACEBACK_LINES = 200

#: An uncompleted traceback older than this flushes as plain lines.
STALE_AFTER_S = 30.0


@dataclass
class Frame:
    file: str
    line: int
    func: str


@dataclass
class TracebackInfo:
    exc_type: str
    exc_value: str
    frames: List[Frame] = field(default_factory=list)
    raw: str = ""

    @property
    def signature(self) -> str:
        if self.exc_value:
            return f"{self.exc_type}: {self.exc_value}"
        return self.exc_type


def parse_traceback(text: str) -> Optional[TracebackInfo]:
    """Parse joined traceback text; None when it has no frames or exc."""
    frames: List[Frame] = []
    exc_type = ""
    exc_value = ""
    for raw_line in text.splitlines():
        line = raw_line.rstrip("\n")
        match = FRAME_RE.match(line)
        if match:
            try:
                lineno = int(match.group(2))
            except ValueError:
                continue
            frames.append(
                Frame(
                    file=match.group(1), line=lineno,
                    func=match.group(3),
                )
            )
            continue
        if line.startswith((" ", "\t")):
            continue  # source-display line
        stripped = line.strip()
        if not stripped:
            continue
        if stripped == TRACEBACK_HEADER:
            continue
        if any(rx.match(stripped) for rx in CHAIN_RES):
            continue
        found = EXC_RE.match(stripped)
        if found:
            # The LAST exception line wins (chained tracebacks).
            exc_type = found.group(1)
            exc_value = (found.group(2) or "").strip()
    if not frames and not exc_type:
        return None
    return TracebackInfo(
        exc_type=exc_type, exc_value=exc_value, frames=frames,
        raw=text,
    )


def _is_complete_trigger(line: str) -> bool:
    """An unindented exception line ends the traceback."""
    if not line or line[0] in (" ", "\t"):
        return False
    stripped = line.strip()
    if stripped == TRACEBACK_HEADER:
        return False
    if any(rx.match(stripped) for rx in CHAIN_RES):
        return False
    return EXC_RE.match(stripped) is not None


class TracebackAssembler:
    """Joins traceback lines from an ordered stream into one text."""

    def __init__(self) -> None:
        self._buf: List[str] = []
        self._started_at = 0.0

    @property
    def collecting(self) -> bool:
        return bool(self._buf)

    def feed(self, line: str, now: float) -> Optional[str]:
        """Feed one line; returns completed traceback text, if any."""
        if not self._buf:
            if line.strip() == TRACEBACK_HEADER:
                self._buf = [line]
                self._started_at = now
            return None
        self._buf.append(line)
        if len(self._buf) >= MAX_TRACEBACK_LINES:
            return self._take()
        if _is_complete_trigger(line):
            return self._take()
        return None

    def flush_stale(self, now: float) -> List[str]:
        """Lines of an uncompleted old traceback (treat as plain lines)."""
        if self._buf and now - self._started_at > STALE_AFTER_S:
            return self._take().splitlines()
        return []

    def pending(self) -> List[str]:
        return list(self._buf)

    def _take(self) -> str:
        text = "\n".join(self._buf)
        self._buf = []
        self._started_at = 0.0
        return text
