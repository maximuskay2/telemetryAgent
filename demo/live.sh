#!/bin/bash
# Live autonomous demo: API + log watcher + load service in one command.
# Dashboard separately: npm run dev (then open http://localhost:3000).
set -euo pipefail
cd "$(dirname "$0")/.."
trap 'kill 0' INT TERM
venv/bin/python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8001 &
sleep 3
venv/bin/python -m core.watch --file demo/target-service/logs/service.log \
  --api http://localhost:8001 --target-path inventory.py &
venv/bin/python demo/target-service/run_service.py --workers 6 --ops 200 &
wait
