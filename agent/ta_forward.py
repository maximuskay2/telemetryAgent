#!/usr/bin/env python3
"""TelemetryAgent log forwarder (J-R1): tail files, POST to /api/ingest/logs.

Stdlib only, single file. Tails from the end of each file, forwards
WARNING+ lines plus full tracebacks, batches every few seconds, and buffers
in memory while the API is down (nothing lost on a short outage).

Served by the API at GET /forwarder.py so the /connect wizard can print a
one-liner. Run it on the customer's machine::

    curl -s http://YOUR-API:8001/forwarder.py -o ta_forward.py
    python3 ta_forward.py --api http://YOUR-API:8001 \\
        --key ta_live_... --file /var/log/app.log --service api
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

LEVEL_RES = [
    ("CRITICAL", re.compile(r"\b(critical|fatal|panic)\b", re.IGNORECASE)),
    ("ERROR", re.compile(r"\b(error|exception|failed|failure|traceback)\b", re.IGNORECASE)),
    ("WARNING", re.compile(r"\b(warn|warning|timeout|timed out|deadlock|retry)\b", re.IGNORECASE)),
    ("INFO", re.compile(r"\b(info|notice)\b", re.IGNORECASE)),
    ("DEBUG", re.compile(r"\b(debug|trace)\b", re.IGNORECASE)),
]
LEVEL_RANK = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}

TRACEBACK_HEADER = "Traceback (most recent call last):"
EXC_RE = re.compile(r"^([A-Za-z_][\w.]*)(?::\s?(.*))?$")

#: Trace heads for every §1.1 language (L-N2; union semantics — the
#: forwarder only decides *whether* to forward, the server re-parses).
#: Secondary heads (`goroutine N`, `Stack trace:`, ...) also recover a
#: trace whose head was missed (rotation, reconnect).
TRACE_START_RES = [
    ("javascript",
     re.compile(r"^(?:[\u2a2f\u00d7]\s*)?(?:Uncaught\s+)?[A-Z][\w$]*(?:\.[A-Za-z_$][\w$]*)*(?:\s+\[[^\]\n]+\])?\s*:\s?")),
    ("javascript",
     re.compile(r"^\[[A-Z][\w$]*\s*:\s?.*\]\s*\{?\s*$")),
    ("java",
     re.compile(r"^(Exception in thread \"[^\"]*\"\s+)?[A-Za-z_$][\w$]*(?:\.[\w$]+)+\s*:")),
    ("java", re.compile(r"^\s*Caused by:\s")),
    ("go", re.compile(r"^(panic|fatal error):\s")),
    ("go", re.compile(r"^goroutine \d+")),
    ("go", re.compile(r"^\[signal ")),
    ("rust", re.compile(r"^\s*stack backtrace:\s*$")),
    ("rust", re.compile(r"^thread '[^']*' panicked at ")),
    ("php", re.compile(r"^PHP (Fatal error|Parse error):")),
    ("php", re.compile(r"^Stack trace:$")),
]

#: Continuation lines for any language trace (checked mid-trace only).
TRACE_CONT_RES = [
    re.compile(r"^\s*at\s+"),                      # V8, `at ./`, Java tab-at
    re.compile(r"^\s*Caused by:\s"),
    re.compile(r"^\s*Suppressed:\s"),
    re.compile(r"^\s*\.\.\."),                   # `... N more`, V8 elision
    re.compile(r"^goroutine \d+"),
    re.compile(r"^\[signal "),
    re.compile(r"^\t\S+:\d+"),                    # Go `pkg/x.go:12 +0x1d`
    re.compile(r"^[A-Za-z_][\w./~-]*(\.\([\w~*]+\))?\.\w[\w~]*(\[[^\]]*\])?\(.*\)$"),
    re.compile(r"^created by \S+(\s+in\s+goroutine\s+\d+)?$"),
    re.compile(r"^\s*stack backtrace:\s*$"),
    re.compile(r"^\s*\d+:\s"),                    # Rust `0: symbol`
    re.compile(r"^note: "),                          # Rust tail note
    re.compile(r"^Stack trace:$"),
    re.compile(r"^#\d+\s"),                        # PHP `#0 /F.php(1):`
    re.compile(r"^\s*\[cause\]:"),
    re.compile(r"^\s*>?\s*\d*\s*\|"),           # Next.js code gutters
    re.compile(r"^\s*[\{\}]\s*$"),
    re.compile(r"^Node\.js v\d"),                  # Node trailer
]


def trace_start_lang(line):
    """Language whose trace `line` opens, or None (L-N2 union)."""
    stripped = line.strip()
    if not stripped:
        return None
    if stripped == TRACEBACK_HEADER:
        return None  # Python keeps its own path below
    for lang, regex in TRACE_START_RES:
        if regex.match(stripped):
            if lang == "javascript" and not stripped.startswith("["):
                name = re.match(
                    r"^(?:[\u2a2f\u00d7]\s*)?(?:Uncaught\s+)?([A-Z][\w$]*)",
                    stripped)
                if name is None or len(name.group(1)) < 2:
                    continue  # `C:\...` drive paths are not errors
            return lang
    return None


def trace_continues(line):
    """True when `line` extends any open non-Python trace (L-N2 union)."""
    stripped = line.strip()
    if not stripped:
        return False
    if "[stacktrace]" in stripped:  # Laravel/Monolog context blocks
        return True
    if "thrown in " in stripped:  # PHP tail
        return True
    return any(regex.match(line) for regex in TRACE_CONT_RES)

#: In-memory spool while the API is unreachable (oldest drops past this).
MAX_BUFFERED_LINES = 20000


def detect_level(line):
    for level, regex in LEVEL_RES:
        if regex.search(line):
            return level
    return "INFO"


def is_traceback_end(line):
    """End of the open trace: a Python exc line or any new head (L-N2)."""
    if not line or line[0] in (" ", "\t"):
        return False
    stripped = line.strip()
    if stripped == TRACEBACK_HEADER:
        return False
    if trace_start_lang(line) is not None:
        return True  # a new head ends the previous trace
    return EXC_RE.match(stripped) is not None


class Tailer:
    """Follows one file from its end; survives rotation + truncation."""

    def __init__(self, path, min_rank=30):
        self.path = path
        self.min_rank = min_rank
        self.handle = None
        self.inode = None
        self.in_traceback = False
        self.in_lang_trace = False
        self._prev_rust_head = False
        try:
            self._open()
        except OSError:
            print(f"[ta_forward] {self.path}: not there yet, waiting",
                  file=sys.stderr)

    def _open(self, from_start=False):
        self.handle = open(self.path, "r", encoding="utf-8", errors="replace")
        if not from_start:
            self.handle.seek(0, os.SEEK_END)
        try:
            self.inode = os.fstat(self.handle.fileno()).st_ino
        except OSError:
            self.inode = None

    def _reopen_if_needed(self):
        if self.handle is None:
            # A file created after start is new: read it from the top.
            try:
                self._open(from_start=True)
            except OSError:
                return
            print(f"[ta_forward] {self.path}: appeared, tailing",
                  file=sys.stderr)
            return
        try:
            stat = os.stat(self.path)
        except OSError:
            return
        if self.inode is not None and stat.st_ino != self.inode:
            self._reopen(reason="rotated")
            return
        try:
            pos = self.handle.tell()
        except OSError:
            self._reopen(reason="unreadable")
            return
        if stat.st_size < pos:
            self._reopen(reason="truncated")

    def _reopen(self, reason):
        try:
            self.handle.close()
        except OSError:
            pass
        self.in_traceback = False
        self.in_lang_trace = False
        self._prev_rust_head = False
        try:
            self._open()
        except OSError:
            self.handle = None
            return
        print(f"[ta_forward] {self.path}: {reason}, reopened", file=sys.stderr)

    def read_new(self):
        self._reopen_if_needed()
        if self.handle is None:
            return []
        try:
            chunk = self.handle.read()
        except OSError as exc:
            print(f"[ta_forward] {self.path}: read error {exc}", file=sys.stderr)
            return []
        if not chunk:
            return []
        return chunk.splitlines()

    def wanted(self, line):
        """True for lines worth forwarding (level filter + all traces)."""
        if self.in_traceback:
            if is_traceback_end(line):
                # The end line is re-evaluated below: usually a plain
                # line, sometimes the head of the next trace.
                self.in_traceback = False
            else:
                return True
        if line.strip() == TRACEBACK_HEADER:
            self.in_traceback = True
            self.in_lang_trace = False
            self._prev_rust_head = False
            return True
        if self.in_lang_trace:
            if self._prev_rust_head and line.strip():
                # Rust >=1.73 prints the panic message on the line after
                # a colon-terminated head; it is the exception value.
                self._prev_rust_head = False
                return True
            if trace_continues(line) or trace_start_lang(line) is not None:
                return True
            self.in_lang_trace = False
            self._prev_rust_head = False
        lang = trace_start_lang(line)
        if lang is not None:
            self.in_lang_trace = True
            self._prev_rust_head = (
                lang == "rust" and line.strip().endswith(":"))
            return True
        return LEVEL_RANK.get(detect_level(line), 20) >= self.min_rank

    def close(self):
        try:
            self.handle.close()
        except OSError:
            pass


class Sender:
    """POSTs batches with backoff; buffers while the API is down."""

    def __init__(self, api, key, service, release, commit):
        self.url = api.rstrip("/") + "/api/ingest/logs"
        self.key = key
        self.service = service
        self.release = release
        self.commit = commit
        self.queue = []
        self.dropped = 0
        self.backoff_s = 1.0

    def add(self, ts, level, message):
        self.queue.append({"ts": ts, "level": level, "message": message})
        if len(self.queue) > MAX_BUFFERED_LINES:
            del self.queue[: len(self.queue) - MAX_BUFFERED_LINES]
            self.dropped += 1

    def flush(self):
        while self.queue:
            batch = self.queue[:500]
            if not self._post(batch):
                return False
            del self.queue[: len(batch)]
        self.backoff_s = 1.0
        return True

    def _post(self, batch):
        body = json.dumps(
            {
                "service": self.service,
                "release": self.release,
                "commit": self.commit,
                "lines": batch,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            self.url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                response.read()
                status = response.status
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                # A wrong key never starts working: report loudly and drop
                # this batch so one bad key can't wedge the queue forever.
                print(
                    "[ta_forward] API rejected the key (401); "
                    "check --key and the connection",
                    file=sys.stderr,
                )
                return True
            print(
                f"[ta_forward] API error {exc.code}; retrying in {self.backoff_s:.0f}s",
                file=sys.stderr,
            )
            self._sleep_backoff()
            return False
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            print(
                f"[ta_forward] API unreachable ({exc}); "
                f"buffered {len(self.queue)} lines, retry in {self.backoff_s:.0f}s",
                file=sys.stderr,
            )
            self._sleep_backoff()
            return False
        if status >= 500:
            self._sleep_backoff()
            return False
        return True

    def _sleep_backoff(self):
        time.sleep(self.backoff_s)
        self.backoff_s = min(60.0, self.backoff_s * 2.0)


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Forward app logs to TelemetryAgent.")
    parser.add_argument("--api", required=True, help="API base URL, e.g. http://host:8001")
    parser.add_argument("--key", required=True, help="ta_live_* ingest key")
    parser.add_argument("--file", dest="files", action="append", required=True)
    parser.add_argument("--service", default="app")
    parser.add_argument("--release", default="")
    parser.add_argument("--commit", default="")
    parser.add_argument("--level", default="WARNING",
                        choices=sorted(LEVEL_RANK, key=LEVEL_RANK.get))
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--idle-exit", type=float, default=0.0,
                        help="exit after N idle seconds (tests); 0 = run forever")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])
    min_rank = LEVEL_RANK[args.level]
    tailers = [Tailer(path, min_rank) for path in args.files]
    sender = Sender(args.api, args.key, args.service, args.release, args.commit)
    print(
        f"[ta_forward] tailing {len(tailers)} file(s) -> {sender.url}",
        file=sys.stderr,
    )
    idle_since = time.time()
    try:
        while True:
            seen = 0
            for tailer in tailers:
                for line in tailer.read_new():
                    if tailer.wanted(line):
                        sender.add(time.time(), detect_level(line), line)
                        seen += 1
            if seen:
                idle_since = time.time()
            if sender.queue and (seen or len(sender.queue) >= args.batch_size):
                sender.flush()
            elif sender.queue:
                sender.flush()
            if args.idle_exit and time.time() - idle_since > args.idle_exit:
                sender.flush()
                return 0
            time.sleep(min(args.interval, 1.0))
    except KeyboardInterrupt:
        return 0
    finally:
        for tailer in tailers:
            tailer.close()


if __name__ == "__main__":
    sys.exit(main())
