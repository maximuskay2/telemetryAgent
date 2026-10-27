"""Concurrent shoppers against the demo shop (Sim 1)."""

from __future__ import annotations

import argparse
import random
import threading
import time

import httpx

SKUS = ["axle", "brake-pad", "chain", "sprocket", "gasket", "piston",
        "alternator", "starter", "radiator", "muffler", "shock", "headlight"]


def shopper(
    shop_base: str,
    rate_per_s: float,
    duration_s: float,
    seed: int,
    tally: dict,
    lock: threading.Lock,
) -> None:
    rng = random.Random(seed)
    deadline = time.time() + duration_s
    gap = 1.0 / max(0.1, rate_per_s)
    while time.time() < deadline:
        items = rng.sample(SKUS, rng.choice([2, 3]))
        try:
            response = httpx.post(
                f"{shop_base.rstrip('/')}/orders", json={"items": items}, timeout=10.0
            )
            ok = response.status_code == 200
        except httpx.HTTPError:
            ok = False
        with lock:
            tally["ok" if ok else "failed"] += 1
        time.sleep(gap * rng.uniform(0.5, 1.5))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Load the demo shop.")
    parser.add_argument("--shop", default="http://localhost:8002")
    parser.add_argument("--shoppers", type=int, default=6)
    parser.add_argument("--rate", type=float, default=4.0, help="Orders/sec total")
    parser.add_argument("--duration", type=float, default=30.0, help="Seconds")
    parser.add_argument("--seed", type=int, default=11)
    args = parser.parse_args(argv)

    tally = {"ok": 0, "failed": 0}
    lock = threading.Lock()
    threads = [
        threading.Thread(
            target=shopper,
            args=(args.shop, args.rate / max(1, args.shoppers),
                  args.duration, args.seed + i, tally, lock),
            daemon=True,
        )
        for i in range(max(1, args.shoppers))
    ]
    started = time.time()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    total = tally["ok"] + tally["failed"]
    rate = total / max(0.1, time.time() - started)
    print(f"orders={total} ok={tally['ok']} failed={tally['failed']} rate={rate:.1f}/s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
