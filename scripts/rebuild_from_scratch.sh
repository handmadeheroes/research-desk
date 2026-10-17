#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
./scripts/install.sh --docker
docker compose exec -T app research-desk status
