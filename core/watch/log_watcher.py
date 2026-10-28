"""Shop log watcher: autonomous grab with `target="inventory"` (Sim 2).

Tails the shop log with the shared rule engine: retry clusters fire early
warnings, Deadlock/ERROR/Traceback lines fire incidents. Each hit sends its
context window to the agent loop and publishes a `watcher_trigger` SimEvent
so the dashboard shows what was grabbed. WARNING/ERROR lines are also
forwarded to /api/logs for the Stream panel, rate-limited to 5/s with errors
first. Send failures are logged, never fatal.
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
    LogForwarder,
    LogTail,
    build_window,
    collect_after,
    match_line,
    post_log,
    publish_sim_event,
    send_run,
    should_send,
)


def classify_forward(line: str) -> Optional[str]:
    """Stream-panel level for a line, or None when it stays out of the feed."""
    trigger = match_line(line)
    if trigger is None:
        return None
    if trigger.level == "crash":
        return "CRITICAL"
    if trigger.level == "error":
        return "ERROR"
    return "WARNING"


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
    forward: bool = True,
    forward_rate: float = 5.0,
    forward_source: str = "shop",
    quiet_s: float = 0.0,
) -> None:
    """Tail `path` forever (or until `max_runs` incidents), grabbing incidents.

    `quiet_s` suppresses new triggers for that long after a run returns: lines
    written while the run was in flight belong to the same incident.
    """
    tail = LogTail(path, from_start=from_start)
    buffer: Deque[str] = deque(maxlen=max(1, before))
    last_sent: Dict[str, float] = {}
    tracker = RetryClusterTracker()
    def forward_sender(message: str, level: str) -> None:
        post_log(api, message, source=forward_source, level=level)

    forwarder = LogForwarder(
        api,
        source=forward_source,
        rate_per_s=forward_rate,
        sender=forward_sender,
    )
    runs = 0
    quiet_until = 0.0
    try:
        while True:
            for line in tail.read_new():
                if forward:
                    level = classify_forward(line)
                    if level is not None:
                        forwarder.push(line, level)
                hit = match_error(line)
                if hit is None:
                    hit = tracker.observe(line, time.time())
                if hit is None or time.time() < quiet_until:
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
                         "fingerprint": fp, "resource": hit.resource,
                         "matched_lines": [line]},
                    )
                except RuntimeError as exc:
                    print(f"[watch] trigger publish failed: {exc}", flush=True)
                try:
                    send_run(api, window, source=source, target=target)
                except RuntimeError as exc:
                    print(f"[watch] run send failed: {exc}", flush=True)
                quiet_until = time.time() + quiet_s
                buffer.append(line)
                buffer.extend(after_lines)
                runs += 1
                if max_runs is not None and runs >= max_runs:
                    forwarder.flush()
                    return
            forwarder.flush()
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
    parser.add_argument("--no-forward", action="store_true",
                        help="Don't forward WARNING/ERROR lines to /api/logs")
    parser.add_argument("--forward-rate", type=float, default=5.0,
                        help="Max forwarded lines per second")
    parser.add_argument("--quiet-seconds", type=float, default=60.0,
                        help="No new runs for this long after a run finishes")
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
        forward=not args.no_forward,
        forward_rate=args.forward_rate,
        quiet_s=args.quiet_seconds,
    )


if __name__ == "__main__":
    main()
