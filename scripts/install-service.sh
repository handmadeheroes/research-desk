#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
[[ "$(uname -s)" == Darwin ]] || { echo "This launchd installer is for macOS."; exit 1; }
.venv/bin/python - <<'PY'
import os
import plistlib
from pathlib import Path
from research_desk.db import data_dir
root = Path.cwd()
logs = data_dir() / "logs"
logs.mkdir(exist_ok=True, mode=0o700)
destination = Path.home() / "Library/LaunchAgents/local.research-desk.plist"
destination.parent.mkdir(parents=True, exist_ok=True)
config = {
    "Label": "local.research-desk",
    "ProgramArguments": [str(root / ".venv/bin/research-desk"), "serve"],
    "WorkingDirectory": str(root),
    "RunAtLoad": True,
    "KeepAlive": True,
    "ThrottleInterval": 10,
    "StandardOutPath": str(logs / "app.log"),
    "StandardErrorPath": str(logs / "error.log"),
    "EnvironmentVariables": {"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
}
destination.write_bytes(plistlib.dumps(config))
destination.chmod(0o600)
print(destination)
PY
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/local.research-desk.plist"
echo "Research Desk will start at login. Open http://127.0.0.1:8401"
