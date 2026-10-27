# Sandbox image for local verification: pytest baked in so containers
# run with --network none. Rebuild after changing this file:
#   ./scripts/build-sandbox-image.sh
FROM python:3.11-slim
RUN pip install --no-cache-dir "pytest>=8,<9"
WORKDIR /work
