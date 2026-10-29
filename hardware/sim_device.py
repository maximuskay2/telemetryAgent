#!/usr/bin/env python3
"""Software ESP32 cold-chain node (John, N-R2).

Stdlib-only: speaks the same device protocol as `hardware/wokwi/sketch.ino`
(readings POST, command poll, ack) with simulated relay state, so the
protocol proves end to end without hardware. Used by tests and the proof run.

    python hardware/sim_device.py --api http://localhost:8201 \\
        --device sim-fridge-01 --key ta_live_... --fault door_open

Device-side safety (last line of defence; the server validates first):
- the compressor never restarts before the commanded `min_off_s` (restart
  is scheduled, never rushed);
- power_cycle during an active defrost is refused (ack ok=false).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

BASE_TEMP_C = 3.5  # shared with the Wokwi sketch + fridge_stream.py
DOOR_INGRESS_C = 0.7
DRIFT = 0.3
DEFROST_S = 600.0


def _parse_args(argv):
    parser = argparse.ArgumentParser(description="Software ESP32 device")
    parser.add_argument("--api", required=True, help="API base URL")
    parser.add_argument("--device", required=True, help="Device id")
    parser.add_argument("--key", required=True, help="Device bearer key")
    parser.add_argument(
        "--fault",
        default="none",
        choices=("none", "door_open"),
        help="Injected fault",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="Seconds between readings",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=5.0,
        help="Seconds between command polls",
    )
    parser.add_argument(
        "--max-readings",
        type=int,
        default=0,
        help="Exit after N readings (0 = run forever)",
    )
    return parser.parse_args(argv)


class SimDevice:
    def __init__(self, api, device, key, fault="none"):
        self.api = api.rstrip("/")
        self.device = device
        self.key = key
        self.fault = fault
        self.temp_c = BASE_TEMP_C
        self.compressor_on = True
        self.off_since = 0.0
        self.pending_restart_at = None
        self.defrost_until = 0.0
        self.backup_on = False
        self.setpoint_c = BASE_TEMP_C
        self.acks = []
        self.acked_ids = set()

    @property
    def defrost_on(self):
        return time.time() < self.defrost_until

    def _request(self, method, path, body=None):
        data = None
        headers = {"Authorization": f"Bearer {self.key}"}
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"{self.api}{path}", data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                raw = response.read().decode()
                return response.status, json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            return exc.code, {"error": exc.read().decode()[:200]}
        except OSError as exc:
            return 0, {"error": str(exc)[:200]}

    def _tick_thermal(self):
        door_open = self.fault == "door_open"
        if door_open:
            self.temp_c += DOOR_INGRESS_C
        else:
            self.temp_c += (BASE_TEMP_C - self.temp_c) * DRIFT
        return door_open

    def post_reading(self):
        door_open = self._tick_thermal()
        status, body = self._request(
            "POST",
            f"/api/devices/{self.device}/readings",
            {
                "appliance_type": "fridge",
                "temperature_c": round(self.temp_c, 2),
                "current_a": round(1.2 if self.compressor_on else 0.05, 3),
                "vibration_g": 0.02,
                "door_open": door_open,
            },
        )
        print(f"POST readings door_open={door_open} -> {status}", flush=True)
        return status, body

    def _stop_compressor(self, now):
        if self.compressor_on:
            self.compressor_on = False
            self.off_since = now

    def _execute(self, action, params, now):
        if action == "defrost":
            self._stop_compressor(now)
            self.defrost_until = now + DEFROST_S
            self.pending_restart_at = self.defrost_until
            return True, "defrost started; compressor resumes after the cycle"
        if action == "setpoint":
            try:
                self.setpoint_c = float(params.get("target_c"))
            except (TypeError, ValueError):
                return False, "setpoint needs a numeric target_c"
            return True, f"setpoint now {self.setpoint_c:g} C"
        if action == "power_cycle":
            if now < self.defrost_until:
                return False, "defrost active — power-cycle refused"
            try:
                min_off = float(params.get("min_off_s", 0))
            except (TypeError, ValueError):
                return False, "power_cycle needs a numeric min_off_s"
            self._stop_compressor(now)
            self.pending_restart_at = self.off_since + min_off
            wait = max(0.0, self.pending_restart_at - now)
            return True, f"compressor off; restart in {wait:.0f}s"
        if action == "backup_on":
            self.backup_on = True
            return True, "backup unit on"
        return False, f"unknown action {action!r}"

    def _tick_relays(self, now):
        if (
            not self.compressor_on
            and self.pending_restart_at is not None
            and now >= self.pending_restart_at
            and now >= self.defrost_until
        ):
            self.compressor_on = True
            self.pending_restart_at = None
            print("compressor restarted", flush=True)

    def poll_and_ack(self):
        now = time.time()
        self._tick_relays(now)
        status, body = self._request(
            "GET", f"/api/devices/{self.device}/commands"
        )
        if status != 200:
            print(f"GET commands -> {status}", flush=True)
            return
        commands = body.get("commands", [])
        for command in commands:
            cid = command.get("id", "")
            if not cid or cid in self.acked_ids:
                continue
            action = command.get("action", "")
            params = command.get("params", {})
            ok, detail = self._execute(action, params or {}, time.time())
            astatus, _ = self._request(
                "POST",
                f"/api/devices/{self.device}/commands/{cid}/ack",
                {"ok": ok, "detail": detail},
            )
            if astatus == 200:
                self.acked_ids.add(cid)
            self.acks.append({"id": cid, "ok": ok, "detail": detail})
            print(
                f"CMD {cid} {action} -> ack ok={ok} ({astatus})",
                flush=True,
            )

    def summary(self):
        return {
            "device": self.device,
            "temp_c": round(self.temp_c, 2),
            "compressor_on": self.compressor_on,
            "defrost_on": self.defrost_on,
            "backup_on": self.backup_on,
            "setpoint_c": self.setpoint_c,
            "acks": list(self.acks),
        }


def main(argv=None):
    args = _parse_args(argv or [])
    device = SimDevice(args.api, args.device, args.key, args.fault)
    readings = 0
    next_poll = 0.0
    while True:
        device.post_reading()
        readings += 1
        now = time.time()
        if now >= next_poll:
            device.poll_and_ack()
            next_poll = now + args.poll_interval
        if args.max_readings and readings >= args.max_readings:
            break
        time.sleep(args.interval)
    # Final poll so a test's last command is never missed.
    device.poll_and_ack()
    return device.summary()


if __name__ == "__main__":
    summary = main(sys.argv[1:])
    print(json.dumps(summary))
