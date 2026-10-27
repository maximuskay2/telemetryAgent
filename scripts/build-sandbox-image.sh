#!/bin/bash
# Build the local verification sandbox image (once per machine).
# Used by core/verify/local_runner.py when Modal is unreachable.
set -euo pipefail
cd "$(dirname "$0")/.."

IMAGE="${TA_SANDBOX_IMAGE:-telemetry-agent-sandbox}"

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

"$DOCKER" build -t "$IMAGE" docker/sandbox
"$DOCKER" run --rm --network none "$IMAGE" pytest --version
echo "sandbox image '$IMAGE' ready"
