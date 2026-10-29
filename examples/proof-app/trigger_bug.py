#!/usr/bin/env python3
"""Hit the buggy endpoint: POST an empty cart, expect a 500 + traceback."""
import json
import sys
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8103"

request = urllib.request.Request(
    f"{BASE}/checkout",
    data=json.dumps({"items": []}).encode(),
    headers={"Content-Type": "application/json"},
)
try:
    with urllib.request.urlopen(request, timeout=15) as response:
        print("unexpected", response.status, response.read().decode()[:200])
except urllib.error.HTTPError as exc:
    print("crashed as expected:", exc.code)
