#!/usr/bin/env bash
# Simulation-route smoke test (roadmap §3.5): the "simulation route
# preserved" guarantee. Starts the API on a random free port with a temp
# TA_DATA_DIR, so it never touches the live demo (8001/8002/3000).
#
# Needs model keys: sources ../telemetry-agent/.env when present (same
# relative path from both agent worktrees). GITHUB_TOKEN is always unset
# here so the smoke run can never open a real PR.
#
# Web pages are checked only when SMOKE_WEB_URL is set (e.g. John's :3201);
# agents must never probe Akingbade's live :3000, so there is no default.
# Slow by design: two full agent runs (candidate→act, /api/run).
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -x venv/bin/python ]; then PY=venv/bin/python;
elif [ -x ../telemetry-agent/venv/bin/python ]; then PY=../telemetry-agent/venv/bin/python;
else PY=python3; fi

if [ -f ../telemetry-agent/.env ]; then
  set -a; . ../telemetry-agent/.env; set +a
fi
unset GITHUB_TOKEN GH_TOKEN

DATA_DIR="$(mktemp -d "${TMPDIR:-/tmp}/ta-smoke.XXXXXX")"
PORT="$("$PY" -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1])')"
BASE="http://127.0.0.1:${PORT}"
OUT="$(mktemp -d "${TMPDIR:-/tmp}/ta-smoke-out.XXXXXX")"

cleanup() {
  if [ -n "${SERVER_PID:-}" ]; then kill "$SERVER_PID" 2>/dev/null || true; fi
  rm -rf "$DATA_DIR" "$OUT"
}
trap cleanup EXIT

echo "smoke: API on $BASE (data $DATA_DIR)"
TA_DATA_DIR="$DATA_DIR" PRODUCTION_CONNECT_ENABLED=1 \
  "$PY" -m uvicorn apps.api.main:app --host 127.0.0.1 --port "$PORT" \
  >"$OUT/server.log" 2>&1 &
SERVER_PID=$!

for _ in $(seq 1 60); do
  if curl -sf -o /dev/null "$BASE/api/health"; then break; fi
  sleep 1
done
curl -sf -o /dev/null "$BASE/api/health" || {
  echo "smoke: server never came up"; tail -20 "$OUT/server.log"; exit 1
}

need() { # need <file> <dotted.path> <expected>
  "$PY" - "$OUT/$1" "$2" "$3" <<'EOF'
import json, sys
data = json.load(open(sys.argv[1]))
cur = data
for part in sys.argv[2].split("."):
    cur = cur[int(part)] if part.isdigit() else cur[part]
if isinstance(cur, bool):
    cur = str(cur).lower()
assert str(cur) == sys.argv[3], f"{sys.argv[2]}={cur!r} in {data!r}"
EOF
}

need_nonempty() { # need_nonempty <file> <dotted.path>
  "$PY" - "$OUT/$1" "$2" <<'EOF'
import json, sys
data = json.load(open(sys.argv[1]))
cur = data
for part in sys.argv[2].split("."):
    cur = cur[int(part)] if part.isdigit() else cur[part]
assert cur, f"{sys.argv[2]} is empty in {data!r}"
EOF
}

echo "smoke: bootstrap -> sample -> confirm -> arm"
curl -sf -X POST "$BASE/api/demo/bootstrap" -o "$OUT/bootstrap.json"
SHOP="$("$PY" -c 'import json;print(json.load(open("'"$OUT"'/bootstrap.json"))["shop"]["system_id"])')"
curl -sf -X POST "$BASE/api/systems/$SHOP/profile/sample" \
  -H 'Content-Type: application/json' -d '{"sample":"shop"}' \
  -o "$OUT/sample.json"
need sample.json status draft
curl -sf -X POST "$BASE/api/systems/$SHOP/profile/confirm" \
  -H 'Content-Type: application/json' -d '{"confirmed_by":"smoke","resolve":[]}' \
  -o "$OUT/confirm.json"
need confirm.json status confirmed
curl -sf -X POST "$BASE/api/systems/$SHOP/arm" -o "$OUT/arm.json"
need arm.json status armed

echo "smoke: candidate system_id=shop -> act (full agent run)"
curl -sf -X POST "$BASE/api/incidents/candidate" \
  -H 'Content-Type: application/json' \
  -d '{"system_id":"shop","source":"log","rule":"smoke-hard-limit","metrics":{"error_rate":0.9},"signature":"smoke: order error rate 90%"}' \
  --max-time 600 -o "$OUT/candidate.json"
need candidate.json decision.decision act
need_nonempty candidate.json run_id

echo "smoke: fridge state"
curl -sf "$BASE/api/sim/fridge/state" -o "$OUT/fridge.json"

echo "smoke: /api/run deadlock sample -> run_id (full agent run)"
curl -sf "$BASE/api/samples/deadlock" -o "$OUT/sample-log.json"
"$PY" - "$OUT/sample-log.json" "$OUT/run-body.json" <<'EOF'
import json, sys
log = json.load(open(sys.argv[1]))["log_text"]
json.dump({"log_text": log}, open(sys.argv[2], "w"))
EOF
curl -sf -X POST "$BASE/api/run" -H 'Content-Type: application/json' \
  -d @"$OUT/run-body.json" --max-time 600 -o "$OUT/run.json"
need_nonempty run.json run_id

if [ -n "${SMOKE_WEB_URL:-}" ]; then
  echo "smoke: web pages at $SMOKE_WEB_URL"
  for page in /welcome /start /start/setup /shop /setup; do
    curl -sf -o /dev/null "${SMOKE_WEB_URL}${page}" || {
      echo "smoke: $page did not return 200"; exit 1
    }
  done
else
  echo "smoke: web pages SKIP (SMOKE_WEB_URL not set)"
fi

echo "smoke: GREEN"
