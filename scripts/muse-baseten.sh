#!/usr/bin/env bash
# Run Muse Code on Baseten (Muse Spark Open) instead of the Meta API.
#   ./scripts/muse-baseten.sh check            # one test call, prints OK or the error
#   ./scripts/muse-baseten.sh [muse args...]   # interactive, e.g. --worktree existing --worktree-existing ../telemetry-agent-jude
#   ./scripts/muse-baseten.sh exec "prompt"    # headless
# Reads BASETEN_API_KEY from .env (never printed). BASETEN_AGENT_MODEL overrides the model.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
set -a; . "$ROOT/.env"; set +a
: "${BASETEN_API_KEY:?BASETEN_API_KEY missing from .env}"
MODEL="${BASETEN_AGENT_MODEL:-meta-models/muse-spark-open-1026}"
BASE_URL="https://inference.baseten.co/v1"

if [[ "${1:-}" == "check" ]]; then
  code=$(curl -s -o /tmp/ta-baseten-check.json -w '%{http_code}' "$BASE_URL/chat/completions" \
    -H "Authorization: Bearer $BASETEN_API_KEY" -H "Content-Type: application/json" \
    -d "{\"model\":\"$MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with exactly: OK\"}],\"max_tokens\":20}")
  if [[ "$code" == "200" ]]; then echo "Baseten OK ($MODEL)"; else echo "Baseten $code: $(head -c 200 /tmp/ta-baseten-check.json)"; exit 1; fi
  exit 0
fi

export MUSE_NO_UPDATE_CHECK=1
SUB=()
if [[ "${1:-}" == "exec" || "${1:-}" == "resume" ]]; then SUB=("$1"); shift; fi
META_API_KEY="$BASETEN_API_KEY" exec muse ${SUB[@]+"${SUB[@]}"} \
  -c "endpoint_transport={\"base_url\":\"$BASE_URL\",\"auth\":\"bearer\"}" \
  --model "$MODEL" "$@"
