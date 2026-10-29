#!/usr/bin/env bash
# Pre-merge gate for the production build (roadmap §3.5, written at H0).
# Both agents run this before every merge to main. Exit non-zero when any
# non-skipped step fails.
#
#   1. unittest discover (existing + new tests)
#   2. scripts/smoke_demo.sh (simulation route preserved; slow, uses .env keys)
#   3. npm run build -w apps/web (SKIP when npm is missing)
#   4. flutter analyze + flutter test (SKIP when flutter is missing)
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -x venv/bin/python ]; then PY=venv/bin/python;
elif [ -x ../telemetry-agent/venv/bin/python ]; then PY=../telemetry-agent/venv/bin/python;
else PY=python3; fi

fail=0

echo "=== check 1/4: python tests ==="
if "$PY" -m unittest discover -s tests; then
  echo "PASS: python tests"
else
  echo "FAIL: python tests"; fail=1
fi

echo "=== check 2/4: simulation-route smoke ==="
if ./scripts/smoke_demo.sh; then
  echo "PASS: smoke_demo"
else
  echo "FAIL: smoke_demo"; fail=1
fi

echo "=== check 3/4: web build ==="
if command -v npm >/dev/null 2>&1; then
  if npm run build -w apps/web; then
    echo "PASS: web build"
  else
    echo "FAIL: web build"; fail=1
  fi
else
  echo "SKIP (npm not found): web build"
fi

echo "=== check 4/4: flutter analyze + test ==="
if command -v flutter >/dev/null 2>&1; then
  if (cd apps/mobile && flutter analyze && flutter test); then
    echo "PASS: flutter"
  else
    echo "FAIL: flutter"; fail=1
  fi
else
  echo "SKIP (flutter not found): flutter"
fi

if [ "$fail" -ne 0 ]; then echo "check.sh: RED"; exit 1; fi
echo "check.sh: GREEN"
