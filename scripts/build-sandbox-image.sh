#!/bin/bash
# Build local verification sandbox images (once per machine/lang).
# Usage: ./scripts/build-sandbox-image.sh [python|node|jvm|go|rust|php|all]
# Used by core/verify/repo_sandbox.py (image=) when Modal is unreachable.
set -euo pipefail
cd "$(dirname "$0")/.."

LANGS="${1:-python}"
case "$LANGS" in
  python|node|jvm|go|rust|php|all) ;;
  *) echo "usage: $0 [python|node|jvm|go|rust|php|all]" >&2; exit 2 ;;
esac

if [ -n "${DOCKER_BIN:-}" ]; then
  DOCKER="$DOCKER_BIN"
elif command -v docker >/dev/null 2>&1; then
  DOCKER="docker"
elif [ -x "$HOME/.docker/bin/docker" ]; then
  DOCKER="$HOME/.docker/bin/docker"
else
  echo "no docker CLI found (PATH, DOCKER_BIN, ~/.docker/bin/docker)" >&2
  exit 1
fi

case "$DOCKER" in
  */*) export PATH="$(dirname "$DOCKER"):$PATH" ;; # credential helpers live beside the CLI
esac

build_one() {
  lang="$1"
  if [ "$lang" = "python" ]; then
    file="docker/sandbox/Dockerfile"
    image="${TA_SANDBOX_IMAGE:-telemetry-agent-sandbox}"
    check="pytest --version"
  else
    file="docker/sandbox/Dockerfile.$lang"
    image="telemetry-agent-sandbox-$lang"
    case "$lang" in
      node) check="node --version" ;;
      jvm) check="mvn -version" ;;
      go) check="go version" ;;
      rust) check="cargo --version" ;;
      php) check="php --version" ;;
    esac
  fi
  "$DOCKER" build -t "$image" -f "$file" docker/sandbox
  "$DOCKER" run --rm --network none "$image" $check
  echo "sandbox image '$image' ready"
}

if [ "$LANGS" = "all" ]; then
  for lang in python node jvm go rust php; do
    build_one "$lang"
  done
else
  build_one "$LANGS"
fi
