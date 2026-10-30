#!/usr/bin/env bash
# End-to-end language matrix (languages-roadmap L-D4, Jude).
#
#   ./scripts/lang_e2e.sh [lang ...] [--live]
#
# For each language, runs the repo-fix pipeline against its proof app in
# Docker. GitHub is always mocked (no real PRs). Default mode also mocks
# the models with canned repro+patch pairs (deterministic plumbing proof);
# --live uses the real models (Baseten first, Muse Wonder last attempt).
# Prints PASS/DRAFT/SKIP per language with timings.
#
# Langs: python javascript java kotlin go rust php (default: all).
# Live budget: at most 3 live runs per language per day (tracked in
# $TA_E2E_BUDGET_DIR, default ~/.cache/ta-lang-e2e).
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -x venv/bin/python ]; then PY=venv/bin/python;
elif [ -x ../telemetry-agent/venv/bin/python ]; then PY=../telemetry-agent/venv/bin/python;
else PY=python3; fi

LIVE=0
LANGS=()
for arg in "$@"; do
  case "$arg" in
    --live) LIVE=1 ;;
    python|javascript|java|kotlin|go|rust|php) LANGS+=("$arg") ;;
    all) LANGS=() ;;
    -h|--help)
      sed -n '2,17p' "$0"; exit 0 ;;
    *)
      echo "lang_e2e.sh: unknown arg '$arg' (try --help)" >&2; exit 2 ;;
  esac
done
if [ "${#LANGS[@]}" -eq 0 ]; then
  LANGS=(python javascript java kotlin go rust php)
fi

export TA_E2E_LANGS
TA_E2E_LANGS=$(IFS=,; echo "${LANGS[*]}")

if [ "$LIVE" -eq 1 ]; then
  if [ ! -f ../telemetry-agent/.env ]; then
    echo "lang_e2e.sh --live needs ../telemetry-agent/.env" >&2; exit 2
  fi
  set -a; . ../telemetry-agent/.env; set +a
  export BASETEN_PATCH_MODEL=meta-models/muse-spark-open-1026
  export TA_E2E_LIVE=1
  # Live-run budget: 3 per language per day.
  BUDGET_DIR="${TA_E2E_BUDGET_DIR:-$HOME/.cache/ta-lang-e2e}"
  mkdir -p "$BUDGET_DIR"
  TODAY=$(date +%F)
  REMAIN=()
  for lang in "${LANGS[@]}"; do
    COUNT_FILE="$BUDGET_DIR/$TODAY.$lang"
    COUNT=$(cat "$COUNT_FILE" 2>/dev/null || echo 0)
    if [ "$COUNT" -ge 3 ]; then
      echo "E2E lang=$lang result=SKIP seconds=0 pr= model=live reason=live-budget-spent"
    else
      echo $((COUNT + 1)) > "$COUNT_FILE"
      REMAIN+=("$lang")
    fi
  done
  if [ "${#REMAIN[@]}" -eq 0 ]; then
    echo "lang_e2e.sh: live budget spent for all selected langs" >&2; exit 0
  fi
  LANGS=("${REMAIN[@]}")
  TA_E2E_LANGS=$(IFS=,; echo "${LANGS[*]}")
fi

OUT=$(mktemp /tmp/lang-e2e.XXXXXX)
set +e
"$PY" -m unittest tests.test_lang_e2e -v >"$OUT" 2>&1
STATUS=$?
set -e
grep -E "^E2E lang=" "$OUT" || true
echo "---"
grep -E "^(OK|FAILED|Ran )" "$OUT" || true
echo "full log: $OUT"
exit "$STATUS"
