"""Log watcher: tail a service log and auto-start runs on trigger patterns (I3).

Warning-level signals (retries, lock timeouts) start a run before the crash;
error and crash patterns at or after failure. Each incident is fingerprinted
(error type + location) and debounced so a retry storm opens one run.
"""

from __future__ import annotations

import hashlib
import os
import re
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, List, Optional

import httpx

# First match wins: specific patterns before generic ones.
PATTERNS = [
    {"name": "deadlock", "level": "error", "regex": r"deadlock", "flags": re.IGNORECASE},
    {
        "name": "traceback",
        "level": "error",
        "regex": r"Traceback \(most recent call last\)",
        "flags": 0,
    },
    {
        "name": "lock_timeout",
        "level": "warning",
        "regex": r"lock (wait )?timeout|timed out.*lock",
        "flags": re.IGNORECASE,
    },
    {"name": "retry", "level": "warning", "regex": r"retry=\d+|retrying", "flags": re.IGNORECASE},
    {"name": "warning", "level": "warning", "regex": r"\bWARN(ING)?\b", "flags": 0},
    {"name": "error", "level": "error", "regex": r"\bERROR\b|\bfailed\b|\bexception\b", "flags": 0},
    {
        "name": "crash",
        "level": "crash",
        "regex": r"process (exited|died)|health check (failed|down)|\bCRITICAL\b|\bFATAL\b",
        "flags": 0,
    },
]

_COMPILED = [
    (p["name"], p["level"], re.compile(p["regex"], p["flags"])) for p in PATTERNS
]

MAX_LOG_TEXT_CHARS = 20000


@dataclass
class Trigger:
    name: str
    level: str
    line: str


def match_line(line: str) -> Optional[Trigger]:
    """Return the first matching trigger pattern, or None for clean lines."""
    for name, level, compiled in _COMPILED:
        if compiled.search(line):
            return Trigger(name=name, level=level, line=line)
    return None


def fingerprint(trigger_name: str, line: str) -> str:
    """Stable incident id: error type + location with numbers normalized away."""
    normalized = re.sub(r"\d+", "#", line).strip()
    digest = hashlib.sha1(f"{trigger_name}:{normalized}".encode()).hexdigest()
    return digest[:12]


def should_send(
    fp: str, now: float, last_sent: Dict[str, float], debounce_s: float
) -> bool:
    """True when no run for this fingerprint started within the debounce window."""
    previous = last_sent.get(fp)
    if previous is not None and now - previous < debounce_s:
        return False
    last_sent[fp] = now
    return True


def build_window(before: List[str], trigger_line: str, after: List[str]) -> str:
    """Join context lines around a trigger, capped to the API input limit."""
    text = "\n".join([*before, trigger_line, *after])
    if len(text) > MAX_LOG_TEXT_CHARS:
        text = text[-MAX_LOG_TEXT_CHARS:]
    return text


class LogTail:
    """Follow a file across appends, truncation, and rotation (rename+recreate)."""

    def __init__(self, path: str, from_start: bool = False) -> None:
        self.path = path
        self.handle = open(path, "r", encoding="utf-8", errors="replace")
        self._identity = self._stat_identity()
        if not from_start:
            self.handle.seek(0, os.SEEK_END)

    def _stat_identity(self):
        try:
            stat = os.stat(self.path)
        except FileNotFoundError:
            return None
        return (stat.st_dev, stat.st_ino, stat.st_size)

    def read_new(self) -> List[str]:
        """Return lines appended since the last call (single non-blocking pass)."""
        current = self._stat_identity()
        if (
            current is not None
            and self._identity is not None
            and (current[:2] != self._identity[:2] or current[2] < self._identity[2])
        ):
            # Rotated (new inode) or truncated (shrank): start over.
            self.handle.close()
            self.handle = open(self.path, "r", encoding="utf-8", errors="replace")
            current = self._stat_identity()
        lines = self.handle.readlines()
        if current is not None:
            try:
                pos = self.handle.tell()
            except OSError:
                pos = current[2]
            self._identity = (current[0], current[1], pos)
        return [line.rstrip("\n") for line in lines]

    def close(self) -> None:
        self.handle.close()


def send_run(
    api_base: str,
    log_text: str,
    source: str = "watcher",
    target_path: Optional[str] = None,
    target: Optional[str] = None,
    timeout: float = 600.0,
) -> dict:
    """POST a context window to the agent loop; return the parsed response."""
    body: Dict[str, object] = {"log_text": log_text, "source": source}
    if target:
        body["target"] = target
    if target_path:
        body["target_path"] = target_path
    try:
        response = httpx.post(
            f"{api_base.rstrip('/')}/api/run", json=body, timeout=timeout
        )
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Watcher could not reach {api_base}: {exc}.") from exc
    if response.status_code >= 400:
        try:
            detail = response.json().get("Detail", response.text[:200])
        except ValueError:
            detail = response.text[:200]
        raise RuntimeError(f"Agent rejected the incident ({response.status_code}): {detail}.")
    return response.json()


def post_log(
    api_base: str,
    message: str,
    source: str = "shop",
    level: str = "INFO",
    timeout: float = 5.0,
) -> dict:
    """POST one line to /api/logs for the Stream panel; RuntimeError on failure."""
    try:
        response = httpx.post(
            f"{api_base.rstrip('/')}/api/logs",
            json={"message": message, "source": source, "level": level},
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Could not post log to {api_base}: {exc}.") from exc
    if response.status_code >= 400:
        raise RuntimeError(
            f"API rejected log ({response.status_code}): "
            f"{response.text[:200]}."
        )
    return response.json()


class LogForwarder:
    """Rate-limited log line forwarder: errors first, at most N per second.

    The shop writes hundreds of lines under load; the Stream panel wants a
    readable trickle. `sender(message, level)` is injectable for tests.
    """

    def __init__(
        self,
        api_base: str,
        source: str = "shop",
        rate_per_s: float = 5.0,
        max_buffer: int = 200,
        clock=None,
        sender=None,
    ) -> None:
        self.source = source
        self.rate_per_s = rate_per_s
        self.max_buffer = max(1, max_buffer)
        self.clock = clock or time.monotonic
        if sender is None:
            self.sender = lambda message, level: post_log(  # noqa: E731
                api_base, message, source=source, level=level
            )
        else:
            self.sender = sender
        self._buffer: List[tuple] = []  # (level, line), arrival order
        self._tokens = rate_per_s
        self._last = self.clock()
        self.sent = 0
        self.dropped = 0

    def push(self, line: str, level: str) -> None:
        """Queue one classified line, evicting oldest warnings when full."""
        self._buffer.append((level, line))
        while len(self._buffer) > self.max_buffer:
            for index, (candidate, _) in enumerate(self._buffer):
                if candidate != "ERROR" and candidate != "CRITICAL":
                    del self._buffer[index]
                    break
            else:
                del self._buffer[0]
            self.dropped += 1

    def flush(self) -> int:
        """Send what's affordable, errors first; failures drop, never raise."""
        now = self.clock()
        self._tokens = min(
            self.rate_per_s,
            self._tokens + max(0.0, now - self._last) * self.rate_per_s,
        )
        self._last = now
        ordered = sorted(
            range(len(self._buffer)),
            key=lambda i: (
                0 if self._buffer[i][0] in ("ERROR", "CRITICAL") else 1,
                i,
            ),
        )
        sent = 0
        failed = 0
        consumed: set = set()
        for index in ordered:
            if self._tokens < 1.0:
                break
            self._tokens -= 1.0
            level, line = self._buffer[index]
            try:
                self.sender(line, level)
            except Exception:
                failed += 1
                self.dropped += 1
            else:
                sent += 1
            consumed.add(index)
        self._buffer = [
            item for i, item in enumerate(self._buffer) if i not in consumed
        ]
        self.sent += sent
        if failed:
            print(f"[watch] log forward: {failed} send(s) failed, dropped",
                  flush=True)
        return sent


def publish_sim_event(
    api_base: str, kind: str, payload: dict, timeout: float = 5.0
) -> dict:
    """Publish a SimEvent for the dashboard; raise RuntimeError on failure."""
    try:
        response = httpx.post(
            f"{api_base.rstrip('/')}/api/sim/events",
            json={"kind": kind, "payload": payload},
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Could not publish {kind} to {api_base}: {exc}.") from exc
    if response.status_code >= 400:
        raise RuntimeError(
            f"API rejected {kind} ({response.status_code}): "
            f"{response.text[:200]}."
        )
    return response.json()


def run_watcher(
    path: str,
    api: str,
    source: str = "watcher",
    debounce_minutes: float = 10.0,
    before: int = 30,
    after: int = 10,
    after_timeout_s: float = 2.0,
    poll_s: float = 0.5,
    target_path: Optional[str] = None,
    from_start: bool = False,
    max_runs: Optional[int] = None,
) -> None:
    """Tail `path` forever (or until `max_runs` incidents), sending triggers."""
    tail = LogTail(path, from_start=from_start)
    buffer: Deque[str] = deque(maxlen=max(1, before))
    last_sent: Dict[str, float] = {}
    runs = 0
    try:
        while True:
            for line in tail.read_new():
                trigger = match_line(line)
                if trigger is None:
                    buffer.append(line)
                    continue
                fp = fingerprint(trigger.name, line)
                if not should_send(fp, time.time(), last_sent, debounce_minutes * 60):
                    buffer.append(line)
                    continue
                after_lines = collect_after(tail, buffer, after, after_timeout_s)
                window = build_window(list(buffer), line, after_lines)
                print(f"[watch] {trigger.level} {trigger.name} fp={fp} -> {api}", flush=True)
                send_run(api, window, source=source, target_path=target_path)
                buffer.append(line)
                buffer.extend(after_lines)
                runs += 1
                if max_runs is not None and runs >= max_runs:
                    return
            time.sleep(poll_s)
    finally:
        tail.close()


def collect_after(
    tail: LogTail, buffer: Deque[str], count: int, timeout_s: float
) -> List[str]:
    """Gather up to `count` lines after a trigger, waiting at most `timeout_s`."""
    collected: List[str] = []
    deadline = time.time() + max(0.0, timeout_s)
    while len(collected) < count:
        fresh = tail.read_new()
        if fresh:
            collected.extend(fresh[: count - len(collected)])
            continue
        if time.time() >= deadline:
            break
        time.sleep(0.05)
    return collected
