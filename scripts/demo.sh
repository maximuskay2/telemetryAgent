#!/bin/bash
# One-command demo (Sim 6): API + shop + dashboard + log watcher.
# The fridge ticks inside the API. From a clean clone with .env:
#   ./scripts/demo.sh   # then open http://localhost:3000 and press Play scenario
set -euo pipefail
cd "$(dirname "$0")/.."

API_PORT="${API_PORT:-8001}"
SHOP_PORT="${SHOP_PORT:-8002}"
WEB_PORT="${WEB_PORT:-3000}"
# API_HOST=0.0.0.0 exposes the API on the LAN so a phone on the same Wi-Fi
# can pair (M1); the shop, watcher, and dashboard keep using localhost.
API_HOST="${API_HOST:-127.0.0.1}"

if [ ! -x venv/bin/python ]; then
  echo "missing venv/bin/python — create the venv and install requirements first" >&2
  exit 1
fi
if [ ! -d apps/web/node_modules ]; then
  echo "missing apps/web/node_modules — run 'npm install --prefix apps/web' first" >&2
  exit 1
fi
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
else
  echo "no .env — model features will 503 until keys are set (world still sims)"
fi

trap 'kill 0' INT TERM

FRIDGE_STREAM=1 venv/bin/python -m uvicorn apps.api.main:app \
  --host "$API_HOST" --port "$API_PORT" &
sleep 3
AGENT_API="http://localhost:${API_PORT}" SHOP_PORT="$SHOP_PORT" \
  venv/bin/python -m uvicorn demo.shop.app:app \
  --host 127.0.0.1 --port "$SHOP_PORT" &
NEXT_PUBLIC_API_URL="http://localhost:${API_PORT}" \
  npm run dev --prefix apps/web -- --port "$WEB_PORT" &
sleep 2
venv/bin/python -m core.watch.log_watcher \
  --file demo/shop/logs/shop.log --api "http://localhost:${API_PORT}" \
  --target inventory &

echo "demo up: dashboard http://localhost:${WEB_PORT}  api :${API_PORT}  shop :${SHOP_PORT}"
echo "press Play scenario, or Ctrl-C to stop everything"
wait
