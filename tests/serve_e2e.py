import os
import shutil
from pathlib import Path

import uvicorn

from research_desk.db import initialize

root = Path(__file__).resolve().parent.parent
test_data = root / ".test-data/e2e-run"
# This directory is created exclusively by the browser suite, never the owner app.
shutil.rmtree(test_data, ignore_errors=True)
os.environ["RD_DATA_DIR"] = str(test_data)
os.environ["RD_PORT"] = "8407"
password = initialize()
if password:
    path = root / ".test-data/.test-password"
    path.write_text(password)
    path.chmod(0o600)
uvicorn.run("research_desk.app:app", host="127.0.0.1", port=8407)
