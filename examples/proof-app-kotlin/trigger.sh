#!/usr/bin/env bash
# Trigger the empty-cart bug and print the REAL production trace.
set -euo pipefail
cd "$(dirname "$0")"
PORT="${1:-8323}"
mvn -q compile
CP="target/classes:$(mvn -q dependency:build-classpath -Dmdep.outputFile=/dev/stdout -Dmdep.includeScope=runtime | tail -n 1)"
LOG="$(mktemp /tmp/proof-shop-kotlin.XXXXXX.log)"
java -cp "$CP" com.example.shop.ShopServerKt "$PORT" >"$LOG" 2>&1 &
SRV=$!
cleanup() { kill "$SRV" 2>/dev/null || true; }
trap cleanup EXIT
for _ in $(seq 1 50); do
  curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && break
  sleep 0.2
done
CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST \
  "http://127.0.0.1:$PORT/checkout" -H 'content-type: application/json' \
  -d '{"items": []}')
echo "checkout empty cart -> HTTP $CODE (expect 500)"
sleep 0.5
echo "--- production trace ---"
cat "$LOG"
rm -f "$LOG"
