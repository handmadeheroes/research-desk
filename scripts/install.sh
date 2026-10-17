#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ "${1:-}" == "--docker" ]]; then
  command -v docker >/dev/null || { echo "Install and open Docker Desktop first."; exit 1; }
  docker info >/dev/null
  docker compose up -d --build
  echo "Open http://127.0.0.1:8401"
  echo "First-install password is shown in: docker compose logs app"
  exit 0
fi

task_python=""
for candidate in python3.12 python3.13 python3.14 python3.11 python3; do
  if command -v "$candidate" >/dev/null && "$candidate" -c 'import sys; assert sys.version_info >= (3,11)' 2>/dev/null; then
    task_python="$candidate"; break
  fi
done
if [[ -z "$task_python" ]]; then
  echo "Python 3.11+ is required. Install Python 3.12, or use: ./scripts/install.sh --docker"
  exit 1
fi
if ! command -v node >/dev/null || ! node -e 'if(Number(process.versions.node.split(".")[0])<22)process.exit(1)'; then
  echo "Node.js 22+ is required to build the interface. Install it, or use Docker."
  exit 1
fi
"$task_python" -m venv .venv
if command -v uv >/dev/null; then
  uv pip install --python .venv/bin/python -r requirements.lock
  uv pip install --python .venv/bin/python --no-deps -e .
else
  .venv/bin/python -m pip install -r requirements.lock
  .venv/bin/python -m pip install --no-deps -e .
fi
npm ci --no-fund
npm run build
if [[ ! -f .env ]]; then cp .env.example .env; chmod 600 .env; fi
.venv/bin/research-desk init
echo ""
echo "Installation complete. Save the workspace password above."
echo "Start: ./scripts/start.sh"
echo "Then open http://127.0.0.1:8401"
