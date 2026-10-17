#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -x .venv/bin/research-desk-agent ]]; then
  exec .venv/bin/research-desk-agent "$@"
else
  exec docker compose exec -T app research-desk-agent "$@"
fi
