"""Shop log watcher: autonomous grab with `target="inventory"` (Sim 2).

Tails the shop log with the shared rule engine: retry clusters fire early
warnings, Deadlock/ERROR/Traceback lines fire incidents. Each hit sends its
context window to the agent loop and publishes a `watcher_trigger` SimEvent
so the dashboard shows what was grabbed. Send failures are logged, never fatal.
"""

from __future__ import annotations

import argparse
import time
from collections import deque
from typing import Deque, Dict, Optional

from core.watch.rules import (
    RetryClusterTracker,
    fingerprint_for,
    match_error,
)
from core.watch.watcher import (
    LogTail,
    build_window,
    collect_after,
    publish_sim_event,
    send_run,
    should_send,
)


def run(
    path: str,
    api: str,
    target: str = "inventory",
    source: str = "watcher",
    debounce_minutes: float = 10.0,
    before: int = 30,
    after: int = 10,
    after_timeout_s: float = 2.0,
    poll_s: float = 0.5,
    from_start: bool = False,
    max_runs: Optional[int] = None,
) -> None:
    """Tail `path` forever (or until `max_runs` incidents), grabbing incidents."""
    tail = LogTail(path, from_start=from_start)
    buffer: Deque[str] = deque(maxlen=max(1, before))
    last_sent: Dict[str, float] = {}
    tracker = RetryClusterTracker()
    runs = 0
    try:
        while True:
            for line in tail.read_new():
                hit = match_error(line)
                if hit is None:
                    hit = tracker.observe(line, time.time())
                if hit is None:
                    buffer.append(line)
                    continue
                fp = fingerprint_for(hit.rule, hit.resource, hit.line)
                if not should_send(fp, time.time(), last_sent, debounce_minutes * 60):
                    buffer.append(line)
                    continue
                after_lines = collect_after(tail, buffer, after, after_timeout_s)
                window = build_window(list(buffer), line, after_lines)
                print(
                    f"[watch] {hit.level} {hit.rule} fp={fp} -> {api}",
                    flush=True,
                )
                try:
                    publish_sim_event(
                        api,
                        "watcher_trigger",
                        {"rule": hit.rule, "level": hit.level,
                         "fingerprint": fp, "matched_lines": [line]},
                    )
                except RuntimeError as exc:
                    print(f"[watch] trigger publish failed: {exc}", flush=True)
                try:
                    send_run(api, window, source=source, target=target)
                except RuntimeError as exc:
                    print(f"[watch] run send failed: {exc}", flush=True)
                buffer.append(line)
                buffer.extend(after_lines)
                runs += 1
                if max_runs is not None and runs >= max_runs:
                    return
            time.sleep(poll_s)
    finally:
        tail.close()


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Tail the shop log and grab incidents.")
    parser.add_argument("--file", required=True, help="Log file to tail")
    parser.add_argument("--api", default="http://localhost:8001", help="API base URL")
    parser.add_argument("--target", default="inventory", help="Run target constant")
    parser.add_argument("--source", default="watcher", help="Run source label")
    parser.add_argument("--debounce-minutes", type=float, default=10.0)
    parser.add_argument("--before", type=int, default=30, help="Context lines before")
    parser.add_argument("--after", type=int, default=10, help="Context lines after")
    parser.add_argument("--after-timeout", type=float, default=2.0)
    parser.add_argument("--poll", type=float, default=0.5, help="Tail poll seconds")
    parser.add_argument("--from-start", action="store_true")
    parser.add_argument("--max-runs", type=int, default=None, help="Stop after N incidents")
    args = parser.parse_args(argv)
    run(
        args.file,
        args.api,
        target=args.target,
        source=args.source,
        debounce_minutes=args.debounce_minutes,
        before=args.before,
        after=args.after,
        after_timeout_s=args.after_timeout,
        poll_s=args.poll,
        from_start=args.from_start,
        max_runs=args.max_runs,
    )


if __name__ == "__main__":
    main()
