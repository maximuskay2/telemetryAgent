"""Accelerated baseline learning for the demo (P7, stdlib only).

Starts a learning window on a setup system, plays two minutes of normal
traffic through the public endpoints (normal readings plus one defrost
hump for appliances; order logs plus low-error metrics snapshots for
software), then finishes and prints the learned baseline summary.

Usage:
    venv/bin/python demo/setup/accelerated_learn.py SYS_ID [--api URL]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request

DEFAULT_API = "http://localhost:8001"


def api_post(base: str, path: str, body: dict) -> dict:
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        base + path, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def api_get(base: str, path: str) -> dict:
    with urllib.request.urlopen(base + path, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def play_appliance(base: str, system_id: str, ends_at: float) -> int:
    """Normal readings with one defrost hump mid-window; returns rounds."""
    rounds = 0
    start = time.time()
    span = max(1.0, ends_at - start)
    while time.time() < ends_at:
        frac = (time.time() - start) / span
        # Defrost hump between 40% and 65% of the window.
        if 0.40 <= frac <= 0.65:
            peak = 1.0 - abs(frac - 0.525) / 0.125
            temp = 4.0 + 2.5 * max(0.0, peak)
            current = 1.1 + 2.0 * max(0.0, peak)
        else:
            temp = 4.0 + 0.2 * (rounds % 3 - 1)
            current = 3.8 if rounds == 0 else 1.1
        api_post(
            base,
            "/api/telemetry/appliance",
            {
                "source_id": "learn-driver",
                "system_id": system_id,
                "temperature_c": round(temp, 2),
                "current_a": current,
                "vibration_g": 0.02,
            },
        )
        rounds += 1
        time.sleep(2.0)
    return rounds


def play_software(base: str, system_id: str, ends_at: float) -> int:
    """Order logs plus low-error metric snapshots; returns rounds."""
    rounds = 0
    order = 1000
    while time.time() < ends_at:
        order += 1
        api_post(
            base,
            "/api/logs",
            {
                "message": (
                    f"INFO order=a{order} items=axle,chain latency_ms=42"
                ),
                "source": "shop",
                "system_id": system_id,
            },
        )
        if rounds % 10 == 5:
            api_post(
                base,
                "/api/logs",
                {
                    "message": f"WARN order=a{order} retry=1 backoff_ms=250",
                    "source": "shop",
                    "system_id": system_id,
                },
            )
        api_post(
            base,
            "/api/sim/events",
            {
                "kind": "shop_metrics",
                "payload": {
                    "orders_per_min": 30.0,
                    "error_rate": 0.005,
                    "p95_ms": 120.0,
                },
            },
        )
        rounds += 1
        time.sleep(2.0)
    return rounds


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Accelerated baseline learning.")
    parser.add_argument("system_id")
    parser.add_argument("--api", default=DEFAULT_API)
    parser.add_argument("--duration", type=float, default=120.0)
    args = parser.parse_args(argv)

    profile = api_get(args.api, f"/api/systems/{args.system_id}/profile")
    kind = (profile.get("profile") or {}).get("kind", "software")
    started = api_post(
        args.api,
        f"/api/systems/{args.system_id}/baseline/start",
        {"duration_s": args.duration},
    )
    print(f"learning {args.system_id} ({kind}) until {started['ends_at']:.0f}")
    if kind == "appliance":
        rounds = play_appliance(args.api, args.system_id, started["ends_at"])
    else:
        rounds = play_software(args.api, args.system_id, started["ends_at"])
    try:
        request = urllib.request.Request(
            args.api + f"/api/systems/{args.system_id}/baseline/finish",
            data=b"",
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            done = json.loads(response.read().decode("utf-8"))
    except Exception:
        done = api_get(args.api, f"/api/systems/{args.system_id}/baseline")
    baseline = done.get("baseline", done)
    print(f"rounds: {rounds}")
    print(f"status: {baseline.get('status')}")
    print(f"log templates: {len(baseline.get('log_templates', []))}")
    print(f"sensor metrics: {sorted((baseline.get('sensor_bands') or {}).keys())}")
    print(f"metric bands: {sorted((baseline.get('metric_bands') or {}).keys())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
