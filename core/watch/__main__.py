"""CLI entry point: python -m core.watch --file <log> --api <base>."""

from __future__ import annotations

import argparse

from core.watch.watcher import run_watcher


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Tail a log and auto-start agent runs.")
    parser.add_argument("--file", required=True, help="Log file to tail")
    parser.add_argument("--api", default="http://localhost:8001", help="API base URL")
    parser.add_argument("--source", default="watcher", help="Run source label")
    parser.add_argument("--debounce-minutes", type=float, default=10.0)
    parser.add_argument("--before", type=int, default=30, help="Context lines before")
    parser.add_argument("--after", type=int, default=10, help="Context lines after")
    parser.add_argument("--after-timeout", type=float, default=2.0)
    parser.add_argument("--poll", type=float, default=0.5, help="Tail poll seconds")
    parser.add_argument("--target-path", default=None, help="Allowlisted target file")
    parser.add_argument("--from-start", action="store_true", help="Read existing content first")
    parser.add_argument("--max-runs", type=int, default=None, help="Stop after N incidents")
    args = parser.parse_args(argv)
    run_watcher(
        args.file,
        args.api,
        source=args.source,
        debounce_minutes=args.debounce_minutes,
        before=args.before,
        after=args.after,
        after_timeout_s=args.after_timeout,
        poll_s=args.poll,
        target_path=args.target_path,
        from_start=args.from_start,
        max_runs=args.max_runs,
    )


if __name__ == "__main__":
    main()
