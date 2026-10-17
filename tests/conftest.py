import pytest
from fastapi.testclient import TestClient

from research_desk.app import create_app
from research_desk.db import data_dir, initialize

PASSWORD = "test-only-workspace-password"


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("RD_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    initialize(PASSWORD)
    with TestClient(create_app(start_worker=False)) as client:
        result = client.post("/api/login", json={"password": PASSWORD})
        client.headers["X-CSRF-Token"] = result.json()["csrf"]
        yield client


@pytest.fixture
def dot(workspace):
    workspace.cookies.clear()
    workspace.headers["Authorization"] = "Bearer " + (data_dir() / "agent-token").read_text()
    return workspace
