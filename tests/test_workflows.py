import hashlib
import io
import json
import socket
import zipfile
from datetime import datetime, timezone

import pytest

from research_desk import agent
from research_desk.cli import backup, restore
from research_desk.db import connect, data_dir, get_setting, row_dict
from research_desk.ingestion import extract_file
from research_desk.jobs import Worker, portfolio, queue_job
from research_desk.library import get_document, save_document
from research_desk.network import public_target


def run_job(identity):
    with connect() as db:
        job = row_dict(db.execute("SELECT * FROM jobs WHERE id=?", (identity,)).fetchone())
    Worker().execute(job)
    with connect() as db:
        return row_dict(db.execute("SELECT * FROM jobs WHERE id=?", (identity,)).fetchone())


def conversation(identity, title, text, timestamp=1729000000):
    return {"id": identity, "title": title, "create_time": timestamp, "mapping": {
        "root": {"parent": None, "message": {"author": {"role": "user"}, "create_time": timestamp,
                                            "content": {"parts": ["Research " + title]}}},
        "a": {"parent": "root", "message": {"author": {"role": "assistant"}, "create_time": timestamp + 1,
                                           "content": {"parts": [text]}}},
        "branch": {"parent": "root", "message": {"author": {"role": "assistant"}, "create_time": timestamp + 2,
                                                "content": {"parts": ["Alternative branch retained."]}}},
    }}


def archive_bytes(conversations, extras=None):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("conversations.json", json.dumps(conversations))
        for name, data in (extras or {}).items():
            z.writestr(name, data)
    return out.getvalue()


def test_auth_csrf_validation_and_dot_attribution(workspace):
    client = workspace
    csrf = client.headers.pop("X-CSRF-Token")
    assert client.post("/api/stocks", json={}).status_code == 403
    client.headers["X-CSRF-Token"] = csrf
    assert client.post("/api/stocks", json={"symbol": "../escape"}).status_code == 422
    assert client.post("/api/tasks", json={"title": "Review", "due_at": "2026-01-01T10:00"}).status_code == 422
    assert client.put("/api/preferences", json={"timezone": "Not/AZone", "digest_time": "08:30",
                                               "profile": "", "dot_url": "https://chatgpt.com/"}).status_code == 422
    assert client.post("/api/documents", json={"title": "Bad", "content": "x", "url": "javascript:alert(1)"}).status_code == 422
    client.cookies.clear()
    assert client.get("/api/documents").status_code == 401
    client.headers["Authorization"] = "Bearer " + (data_dir() / "agent-token").read_text()
    response = client.post("/api/documents", json={"title": "Dot note", "content": "Cited analysis", "ai_generated": True})
    assert response.status_code == 200
    assert response.json()["document"]["ai_generated"] == 1
    assert client.get("/api/activity").json()[0]["actor"] == "Dot"


def test_portfolio_crud_currency_separation_and_quote_identity(workspace):
    client = workspace
    body = {"symbol": "AAPL", "quote_symbol": "aapl.us", "category": "holding", "shares": 2, "average_cost": 100}
    identity = client.post("/api/stocks", json=body).json()["id"]
    client.post("/api/stocks/" + identity + "/price", json={"price": 200, "previous_price": 190, "as_of": "2026-10-16"})
    jpy = client.post("/api/stocks", json={"symbol": "7203", "quote_symbol": "7203.jp", "currency": "JPY",
                                           "category": "holding", "shares": 1}).json()["id"]
    client.post("/api/stocks/" + jpy + "/price", json={"price": 3000, "as_of": "2026-10-16"})
    assert portfolio()["totals"] == {"USD": 400, "JPY": 3000}
    assert portfolio()["day_changes"]["USD"] == 20
    assert client.put("/api/stocks/" + identity, json={**body, "notes": "Updated"}).status_code == 200
    assert next(s for s in portfolio()["stocks"] if s["id"] == identity)["last_price"] == 200
    client.put("/api/stocks/" + identity, json={**body, "symbol": "MSFT", "quote_symbol": "msft.us"})
    assert next(s for s in portfolio()["stocks"] if s["id"] == identity)["last_price"] is None
    assert client.delete("/api/stocks/" + identity).status_code == 200
    actions = client.get("/api/activity").json()
    assert any(a["action"].startswith("Removed stock") and a["details"]["last_price"] is None for a in actions)


def test_free_quotes_parse_actual_source_date_and_preserve_failures(workspace, monkeypatch):
    identity = workspace.post("/api/stocks", json={"symbol": "AAPL", "quote_symbol": "aapl.us"}).json()["id"]
    raw = b"Date,Open,High,Low,Close,Volume\n2026-10-15,1,2,1,100,123\n2026-10-16,1,2,1,105,456\n"
    monkeypatch.setattr("research_desk.jobs.fetch_public", lambda _: (raw, "text/csv", "https://stooq.com/"))
    result = run_job(queue_job("quotes", {}))
    assert result["status"] == "complete"
    with connect() as db:
        stock = dict(db.execute("SELECT * FROM stocks WHERE id=?", (identity,)).fetchone())
    assert stock["last_price"] == 105 and stock["price_at"] == "2026-10-16"
    monkeypatch.setattr("research_desk.jobs.fetch_public", lambda _: (b"No data", "text/plain", ""))
    result = run_job(queue_job("quotes", {}))
    assert result["status"] == "partial" and result["errors"]
    assert portfolio()["stocks"][0]["last_price"] == 105


def test_finnhub_key_is_private_and_quotes_use_authenticated_header(workspace, monkeypatch):
    key = "test-only-finnhub-key"
    assert workspace.post("/api/market-data/key", json={"key": key}).status_code == 200
    assert (data_dir() / "quote-key").stat().st_mode & 0o777 == 0o600
    assert key not in workspace.get("/api/bootstrap").text
    assert key not in workspace.get("/api/activity").text
    workspace.post("/api/stocks", json={"symbol": "AAPL", "quote_symbol": "aapl.us"})
    def fetch(url, headers):
        assert key not in url and headers == {"X-Finnhub-Token": key}
        return b'{"c":105,"pc":100,"t":1792152000}', "application/json", url
    monkeypatch.setattr("research_desk.jobs.fetch_public", fetch)
    monkeypatch.setattr("research_desk.jobs.time.sleep", lambda _: None)
    assert run_job(queue_job("quotes", {}))["status"] == "complete"
    stock = portfolio()["stocks"][0]
    assert stock["last_price"] == 105 and stock["previous_price"] == 100
    assert stock["provider"] == "Finnhub quote" and stock["price_at"].endswith("+00:00")
    assert workspace.delete("/api/market-data/key").status_code == 200
    assert not (data_dir() / "quote-key").exists()


def test_feed_retrieval_preserves_provenance_and_deduplicates(workspace, monkeypatch):
    source = workspace.post("/api/sources", json={"name": "Test publisher", "kind": "rss",
                                                  "url": "https://example.com/feed", "topics": ["Macro"]}).json()["id"]
    feed = b'<?xml version="1.0"?><rss version="2.0"><channel><title>Publisher</title><item><guid>entry-1</guid><title>Rate outlook</title><link>https://example.com/rates</link><pubDate>Fri, 16 Oct 2026 09:00:00 GMT</pubDate><description>Interest rate evidence.</description></item></channel></rss>'
    monkeypatch.setattr("research_desk.jobs.fetch_public", lambda _: (feed, "application/rss+xml", ""))
    assert run_job(queue_job("feed", {"source_id": source}))["imported"] == 1
    document = workspace.get("/api/documents").json()["items"][0]
    assert document["source_name"] == "Test publisher" and document["published_at"].startswith("2026-10-16")
    assert "Macro" in document["tags"]
    assert run_job(queue_job("feed", {"source_id": source}))["duplicates"] == 1


def test_import_selection_branches_dedupe_resume_and_undo(workspace):
    raw = archive_bytes([
        conversation("research-1", "Cloud earnings", "Microsoft cloud revenue and earnings analysis."),
        conversation("personal-2", "Private unrelated chat", "Personal material not selected."),
    ], {"attachment.txt": "Do not index unless requested", "missing.png": b"\x89PNG"})
    preview = workspace.post("/api/imports/preview", files={"file": ("export.zip", raw)}).json()
    assert preview["conversation_count"] == 2
    result = workspace.post("/api/imports", json={"upload_id": preview["upload_id"],
                                                 "selected_ids": ["research-1"], "include_files": False})
    job_id = result.json()["job_id"]
    job = run_job(job_id)
    assert job["status"] == "complete" and job["imported"] == 1
    documents = workspace.get("/api/documents").json()
    assert documents["total"] == 1
    item = workspace.get("/api/documents/" + documents["items"][0]["id"]).json()
    assert "Alternative branch retained" in item["content"] and "Parent: root" in item["content"]
    assert item["ai_generated"] == 1 and item["published_at"] is None
    assert item["created_at"].startswith("2024")
    assert (data_dir() / item["md_path"]).exists() and (data_dir() / item["raw_path"]).exists()
    assert workspace.get("/api/documents?q=cloud&ticker=MSFT").json()["total"] == 1
    # Re-running a previously interrupted job is safe and its saved-item count remains accurate.
    job = run_job(job_id)
    assert job["imported"] == 1 and job["duplicates"] == 0
    second = workspace.post("/api/imports", json={"upload_id": preview["upload_id"],
                                                 "selected_ids": ["research-1"], "include_files": False}).json()["job_id"]
    assert run_job(second)["duplicates"] == 1
    assert workspace.post("/api/jobs/" + job_id + "/undo").json()["archived"] == 1
    assert workspace.get("/api/documents").json()["total"] == 0
    assert (data_dir() / item["raw_path"]).exists()


def test_versioning_and_import_undo_preserves_later_edits(workspace):
    first, _ = save_document(title="Original", content="Old analysis", external_id="stable:1")
    changed, action = save_document(title="Updated", content="New analysis", external_id="stable:1")
    assert action == "updated" and changed["id"] == first["id"]
    assert (data_dir() / first["md_path"]).exists()
    assert workspace.patch("/api/documents/" + first["id"], json={"tags": ["Cloud"], "summary": "Reviewed"}).status_code == 200
    assert len(workspace.get("/api/documents/" + first["id"] + "/versions").json()) == 2
    assert workspace.get("/api/documents/" + first["id"] + "/file/markdown").status_code == 200


@pytest.mark.parametrize("name", ["../escape.txt", "/absolute.txt", "nested/../../escape.txt", "C:/escape.txt"])
def test_archive_traversal_is_rejected_before_writing(workspace, name):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as z:
        z.writestr(name, "untrusted")
    response = workspace.post("/api/imports/preview", files={"file": ("unsafe.zip", output.getvalue())})
    assert response.status_code == 400
    assert "Cannot read" in response.json()["detail"]


def test_invalid_archive_and_unsupported_file_reports(workspace):
    assert workspace.post("/api/imports/preview", files={"file": ("not.zip", b"not a zip")}).status_code == 400
    assert workspace.post("/api/imports/preview", files={"file": ("run.sh", b"echo danger")}).status_code == 400
    raw = archive_bytes([], {"a.txt": "Useful source material", "picture.png": b"PNG"})
    upload = workspace.post("/api/imports/preview", files={"file": ("files.zip", raw)}).json()["upload_id"]
    job = run_job(workspace.post("/api/imports", json={"upload_id": upload}).json()["job_id"])
    assert job["status"] == "partial" and job["imported"] == 1 and job["errors"]


@pytest.mark.parametrize("url", ["http://127.0.0.1", "http://169.254.169.254", "http://[::1]", "file:///etc/passwd",
                               "https://user:pass@example.com", "https://example.com:8443"])
def test_private_network_and_credential_urls_blocked(url, monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, port, **kwargs: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", (host if host in ("127.0.0.1", "169.254.169.254") else "::1", port))])
    with pytest.raises(ValueError):
        public_target(url)


def test_digest_citations_calendar_layout_and_profile(workspace):
    document = workspace.post("/api/documents", json={"title": "Evidence", "content": "Source-backed cloud research."}).json()["document"]
    assert workspace.post("/api/digests", json={"day": "2026-10-17", "content": "Unsupported", "document_ids": ["missing"]}).status_code == 400
    assert workspace.post("/api/digests", json={"day": "2026-10-17", "content": "See the saved source.",
                                               "document_ids": [document["id"]]}).status_code == 200
    assert workspace.post("/api/digests/generate").status_code == 200
    task = workspace.post("/api/tasks", json={"title": "Review, cloud; earnings", "due_at": "2026-10-17T10:00:00+08:00",
                                              "document_id": document["id"]})
    assert task.status_code == 200
    ics = workspace.get("/api/calendar.ics").text
    assert "20261017T020000Z" in ics and "Review\\, cloud\\; earnings" in ics
    layout = workspace.get("/api/bootstrap").json()["layout"]
    layout[0]["x"], layout[0]["w"] = 1, 7
    fields = [{k: value[k] for k in ("id", "x", "y", "w", "h")} for value in layout]
    assert workspace.put("/api/layout", json=fields).status_code == 200
    assert workspace.get("/api/bootstrap").json()["layout"][0]["x"] == 1
    assert workspace.put("/api/layout", json=fields[:1]).status_code == 400
    assert workspace.post("/api/layout/reset").status_code == 200
    assert workspace.get("/api/bootstrap").json()["layout"][0]["x"] == 0


def test_backup_restore_integrity_and_original_files(workspace, monkeypatch, tmp_path):
    document, _ = save_document(title="Restorable", content="Original source text", tags=["Macro"])
    archive = backup(tmp_path / "backup.zip")
    with monkeypatch.context() as context:
        context.setenv("RD_DATA_DIR", str(tmp_path / "restored"))
        restored = restore(archive)
        assert get_document(document["id"])["content"] == "Original source text"
        assert (restored / document["raw_path"]).read_text() == "Original source text"
        assert (restored / "agent-token").exists()
        assert get_setting("password_hash")
        with pytest.raises(ValueError):
            restore(archive)
    # Restore into the live app's directory must refuse even when replace is explicit.
    with pytest.raises(ValueError, match="Stop"):
        restore(archive, replace=True)


def test_restore_rejects_invalid_database_before_replacement(workspace, monkeypatch, tmp_path):
    broken = b"not a sqlite database"
    archive = tmp_path / "broken.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("research.db", broken)
        output.writestr("manifest.json", json.dumps({"sha256": {"research.db": hashlib.sha256(broken).hexdigest()}}))
    target = tmp_path / "target"
    target.mkdir()
    (target / "research.db").write_bytes(b"keep existing bytes")
    monkeypatch.setenv("RD_DATA_DIR", str(target))
    with pytest.raises(ValueError, match="valid Research Desk"):
        restore(archive, replace=True)
    assert (target / "research.db").read_bytes() == b"keep existing bytes"


def test_email_transcript_and_csv_extraction():
    eml = b"Subject: Weekly briefing\nFrom: Analyst <analyst@example.com>\nDate: Fri, 16 Oct 2026 09:00:00 +0000\nContent-Type: text/plain; charset=utf-8\n\nMacro and interest rate research."
    result = extract_file("mail.eml", eml)
    assert result["kind"] == "email" and "Macro" in result["content"]
    assert result["published_at"].startswith("2026-10-16")
    assert extract_file("video.vtt", b"WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nCloud earnings.")["kind"] == "transcript"
    assert "AAPL | 10" in extract_file("positions.csv", b"Symbol,Shares\nAAPL,10\n")["content"]


def test_collected_metadata_cannot_create_an_executable_source_link(workspace):
    document, _ = save_document(title="Untrusted metadata", content="An external feed entry.",
                                 url="javascript:alert(1)")
    assert get_document(document["id"])["url"] == ""


def test_agent_search_read_and_publish_have_explicit_provenance(dot, monkeypatch):
    def send(method, route, body=None, params=None, **kwargs):
        result = dot.request(method, "/api" + route, json=body, params=params)
        assert result.status_code == 200, result.text
        return result.json()
    monkeypatch.setattr(agent, "request", send)
    item = agent.call_tool("save_research", {"title": "AI thesis", "content": "Long evidence " * 100, "tags": ["AI"]})["document"]
    assert agent.call_tool("search_library", {"query": "evidence"})["total"] == 1
    read = agent.call_tool("read_source", {"id": item["id"], "length": 100})
    assert read["next_offset"] == 100 and read["citation"]["id"] == item["id"]
    result = agent.call_tool("publish_digest", {"day": datetime.now(timezone.utc).date().isoformat(),
                                               "title": "Dot brief", "content": "Analysis with linked evidence.",
                                               "document_ids": [item["id"]]})
    assert result["id"]
    logs = dot.get("/api/activity").json()
    assert any(a["actor"] == "Dot" and a["action"] == "Read saved source" for a in logs)
    assert any(a["actor"] == "Dot" and a["action"] == "Searched research library" for a in logs)
