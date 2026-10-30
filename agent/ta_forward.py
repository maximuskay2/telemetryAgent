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

#: In-memory spool while the API is unreachable (oldest drops past this).
MAX_BUFFERED_LINES = 20000


def detect_level(line):
    for level, regex in LEVEL_RES:
        if regex.search(line):
            return level
    return "INFO"


def is_traceback_end(line):
    if not line or line[0] in (" ", "\t"):
        return False
    stripped = line.strip()
    if stripped == TRACEBACK_HEADER:
        return False
    return EXC_RE.match(stripped) is not None


class Tailer:
    """Follows one file from its end; survives rotation + truncation."""

    def __init__(self, path, min_rank=30):
        self.path = path
        self.min_rank = min_rank
        self.handle = None
        self.inode = None
        self.in_traceback = False
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
        """True for lines worth forwarding (level filter + tracebacks)."""
        if self.in_traceback:
            if is_traceback_end(line):
                self.in_traceback = False
            return True
        if line.strip() == TRACEBACK_HEADER:
            self.in_traceback = True
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
