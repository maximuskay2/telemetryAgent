"""Live demo service (I4): run inventory.py under concurrent load, write logs.

Workers perform real acquire/release cycles against the seeded buggy module.
Acquisition latency is the signal: slow acquires log WARNING retries, and
persistent contention logs a deadlock ERROR block in the sample format. The
log watcher tails this output, so the dashboard lights up with no clicks.

Stdlib only.
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import threading
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from inventory import acquire_all, release_all  # noqa: E402

ITEMS = ["axle", "brake-pad", "chain", "sprocket", "gasket", "piston"]

WARN_WAIT_MS = 5.0
ACQUIRE_TIMEOUT_S = 0.2
MAX_ATTEMPTS = 3


def _stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


class Logger:
    def __init__(self, path: str, echo: bool = True) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.handle = open(path, "a", encoding="utf-8")
        self.lock = threading.Lock()
        self.echo = echo

    def log(self, line: str) -> None:
        stamped = f"{_stamp()} {line}"
        with self.lock:
            self.handle.write(stamped + "\n")
            self.handle.flush()
        if self.echo:
            print(stamped, flush=True)

    def close(self) -> None:
        with self.lock:
            self.handle.close()


def _acquire_timed(items: list, timeout_s: float):
    """Run acquire_all with a timeout; stuck attempts are abandoned (daemon).

    Returns (held, timed_out). Abandoned threads may hold partial locks until
    their wait clears, exactly like wedged workers in a real service.
    """
    box: dict = {}
    thread = threading.Thread(
        target=lambda: box.setdefault("held", acquire_all(items)), daemon=True
    )
    thread.start()
    thread.join(timeout=timeout_s)
    if thread.is_alive():
        return None, True
    return box["held"], False


def transfer(log: Logger, rng: random.Random, tx_id: int, hold_ms: float) -> bool:
    """One transfer with retries; False when every attempt wedges (deadlock)."""
    items = rng.sample(ITEMS, 2)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        started = time.perf_counter()
        held, timed_out = _acquire_timed(items, ACQUIRE_TIMEOUT_S)
        wait_ms = (time.perf_counter() - started) * 1000.0
        if timed_out:
            backoff = min(100, int(10 * (2 ** attempt)))
            log.log(
                f"WARNING retry={attempt} transaction=tx-{tx_id:04d} "
                f"backoff_ms={backoff} items={','.join(items)} "
                f"wait_ms={wait_ms:.0f} (lock wait timeout)"
            )
            time.sleep(backoff / 1000.0)
            continue
        try:
            time.sleep(rng.uniform(0.5 * hold_ms, 1.5 * hold_ms) / 1000.0)
        finally:
            release_all(held)
        if wait_ms >= WARN_WAIT_MS:
            log.log(
                f"WARNING retry=1 transaction=tx-{tx_id:04d} "
                f"backoff_ms=10 items={','.join(items)} wait_ms={wait_ms:.0f}"
            )
        return True
    log.log(f"ERROR transaction=tx-{tx_id:04d} service=inventory")
    log.log(
        "Deadlock detected while acquiring lock on inventory_items; "
        "transaction rolled back."
    )
    return False


def worker(
    log: Logger,
    seed: int,
    ops: int,
    hold_ms: float,
    stop: threading.Event,
    tx_counter: list,
    tx_lock: threading.Lock,
) -> None:
    rng = random.Random(seed)
    for _ in range(ops):
        if stop.is_set():
            return
        with tx_lock:
            tx_counter[0] += 1
            tx_id = tx_counter[0]
        transfer(log, rng, tx_id, hold_ms)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run the demo service under load.")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--ops", type=int, default=200, help="Ops per worker")
    parser.add_argument("--hold-ms", type=float, default=2.0, help="Lock hold time")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument(
        "--log",
        default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "service.log"),
        help="Log file to append",
    )
    parser.add_argument("--quiet", action="store_true", help="No stdout echo")
    args = parser.parse_args(argv)

    log = Logger(args.log, echo=not args.quiet)
    log.log(f"INFO service=inventory workers={args.workers} ops={args.ops} starting")
    stop = threading.Event()
    tx_counter = [0]
    tx_lock = threading.Lock()
    threads = [
        threading.Thread(
            target=worker,
            args=(log, args.seed + i, args.ops, args.hold_ms, stop, tx_counter, tx_lock),
            daemon=True,
        )
        for i in range(max(1, args.workers))
    ]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    except KeyboardInterrupt:
        stop.set()
        log.log("INFO service=inventory stopping on interrupt")
    finally:
        log.log(
            f"INFO service=inventory done transactions={tx_counter[0]}"
        )
        log.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
