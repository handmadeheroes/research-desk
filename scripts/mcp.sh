#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -x .venv/bin/research-desk-mcp ]]; then
  exec .venv/bin/research-desk-mcp
else
  exec docker compose exec -T app research-desk-mcp
fi
