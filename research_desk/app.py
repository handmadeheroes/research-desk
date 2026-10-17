import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import __version__
from .db import (
    DEFAULT_LAYOUT,
    audit,
    connect,
    data_dir,
    get_setting,
    migrate,
    now,
    password_hash,
    row_dict,
    set_setting,
)
from .ingestion import SUPPORTED, preview_archive
from .jobs import Worker, generate_digest, portfolio, publish_digest, queue_job, quote_key
from .library import get_document, save_document, search_documents, update_document
from .models import (
    Digest,
    DocumentInput,
    DocumentPatch,
    ImportRequest,
    LayoutItem,
    Login,
    ManualPrice,
    Preferences,
    QuoteKey,
    Source,
    Stock,
    Task,
    UrlImport,
)

STATIC = Path(__file__).with_name("static")
MAX_UPLOAD = 512 * 1024 * 1024


def actor(request: Request):
    return request.state.actor


def create_app(start_worker=True):
    @asynccontextmanager
    async def lifespan(app):
        import fcntl
        migrate()
        if not get_setting("password_hash"):
            raise RuntimeError("Workspace not initialized. Run: research-desk init")
        lock = (data_dir() / ".app.lock").open("a")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            lock.close()
            raise RuntimeError("Another Research Desk process is already using this data directory.") from exc
        worker = Worker() if start_worker else None
        if worker:
            worker.start()
        yield
        if worker:
            worker.stop()
        lock.close()

    app = FastAPI(title="Research Desk API", version=__version__, lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[
        "localhost", "127.0.0.1", "[::1]", "testserver",
        *[x.strip() for x in os.getenv("RD_ALLOWED_HOSTS", "").split(",") if x.strip()],
    ])
    attempts = defaultdict(list)
    traffic = defaultdict(list)

    @app.middleware("http")
    async def security(request, call_next):
        path = request.url.path
        if path.startswith("/api/") and path != "/api/login":
            identity = request.headers.get("Authorization", "")
            is_agent = False
            session = None
            if identity.startswith("Bearer "):
                digest = hashlib.sha256(identity[7:].encode()).hexdigest()
                expected = get_setting("agent_token_hash", "")
                is_agent = bool(expected) and hmac.compare_digest(digest, expected)
            if not is_agent:
                token = request.cookies.get("rd_session", "")
                with connect() as db:
                    session = db.execute("SELECT * FROM sessions WHERE token_hash=? AND expires_at>?",
                                         (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone()
                if session is None:
                    return Response('{"detail":"Sign in required"}', status_code=401, media_type="application/json")
                if request.method not in ("GET", "HEAD", "OPTIONS"):
                    if not hmac.compare_digest(request.headers.get("X-CSRF-Token", ""), session["csrf"]):
                        return Response('{"detail":"Session verification failed"}', status_code=403,
                                        media_type="application/json")
                    origin = request.headers.get("Origin")
                    if origin and origin != str(request.base_url).rstrip("/"):
                        return Response('{"detail":"Cross-origin request rejected"}', status_code=403,
                                        media_type="application/json")
            request.state.actor = "Dot" if is_agent else "Owner"
            request.state.csrf = session["csrf"] if session else ""
            ip = request.client.host if request.client else "local"
            traffic[ip] = [stamp for stamp in traffic[ip] if stamp > time.time() - 60]
            if len(traffic[ip]) > 600:
                return Response('{"detail":"Please slow down"}', status_code=429, media_type="application/json")
            traffic[ip].append(time.time())
        if path.startswith("/api/"):
            try:
                if int(request.headers.get("Content-Length", "0")) > MAX_UPLOAD + 1024 * 1024:
                    return Response('{"detail":"Upload exceeds 512 MB"}', status_code=413, media_type="application/json")
            except ValueError:
                return Response(status_code=400)
        response = await call_next(request)
        response.headers.update({
            "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                                       "img-src 'self' data: blob:; connect-src 'self'; font-src 'self'; "
                                       "object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
            "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer", "Cache-Control": "no-store" if path.startswith("/api/") else "no-cache",
        })
        return response

    @app.exception_handler(ValueError)
    async def bad_input(request, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": str(exc)[:500]}, status_code=400)

    @app.exception_handler(sqlite3.IntegrityError)
    async def conflict(request, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": "This record conflicts with an existing record or linked item."}, status_code=409)

    @app.get("/health")
    def health():
        with connect() as db:
            db.execute("SELECT 1").fetchone()
        return {"status": "ok", "version": __version__}

    @app.post("/api/login")
    def login(body: Login, request: Request, response: Response):
        ip = request.client.host if request.client else "local"
        attempts[ip] = [stamp for stamp in attempts[ip] if stamp > time.time() - 900]
        if len(attempts[ip]) >= 10:
            raise HTTPException(429, "Too many sign-in attempts. Try again in 15 minutes.")
        attempts[ip].append(time.time())
        stored = get_setting("password_hash", "")
        if not stored or not hmac.compare_digest(password_hash(body.password, stored.split(":")[0]), stored):
            raise HTTPException(401, "Incorrect workspace password")
        attempts.pop(ip, None)
        token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
        with connect() as db:
            db.execute("DELETE FROM sessions WHERE expires_at<?", (time.time(),))
            db.execute("INSERT INTO sessions VALUES(?,?,?)",
                       (hashlib.sha256(token.encode()).hexdigest(), csrf, time.time() + 43200))
        response.set_cookie("rd_session", token, httponly=True, samesite="strict", max_age=43200,
                            secure=os.getenv("RD_SECURE_COOKIE", "false").lower() == "true")
        audit("Owner", "Signed in")
        return {"csrf": csrf}

    @app.post("/api/logout")
    def logout(request: Request, response: Response):
        with connect() as db:
            db.execute("DELETE FROM sessions WHERE token_hash=?",
                       (hashlib.sha256(request.cookies.get("rd_session", "").encode()).hexdigest(),))
        response.delete_cookie("rd_session")
        return {"ok": True}

    @app.get("/api/bootstrap")
    def bootstrap(request: Request):
        zone = ZoneInfo(get_setting("timezone", "Asia/Kuala_Lumpur"))
        today = datetime.now(zone).date()
        midnight = datetime.combine(today, datetime.min.time(), zone).astimezone(timezone.utc).isoformat()
        tomorrow = datetime.combine(today + timedelta(days=1), datetime.min.time(), zone).astimezone(timezone.utc).isoformat()
        with connect() as db:
            counts = {
                "documents": db.execute("SELECT count(*) FROM documents WHERE archived=0").fetchone()[0],
                "sources": db.execute("SELECT count(*) FROM sources").fetchone()[0],
                "new_today": db.execute("SELECT count(*) FROM documents WHERE archived=0 AND retrieved_at>=?",
                                        (midnight,)).fetchone()[0],
                "tasks": db.execute("SELECT count(*) FROM tasks WHERE done=0 AND julianday(due_at)<julianday(?)", (tomorrow,)).fetchone()[0],
            }
            digest = row_dict(db.execute("SELECT * FROM digests ORDER BY day DESC,created_at DESC LIMIT 1").fetchone())
            tasks = [dict(row) for row in db.execute("SELECT * FROM tasks ORDER BY done,due_at LIMIT 500")]
            activities = [row_dict(row) for row in db.execute("SELECT * FROM activity ORDER BY id DESC LIMIT 8")]
            active_jobs = db.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]
        return {
            "csrf": request.state.csrf, "version": __version__, "stats": counts, "digest": digest,
            "tasks": tasks, "activity": activities, "portfolio": portfolio(),
            "library": search_documents(limit=5)["items"],
            "layout": get_setting("layout", DEFAULT_LAYOUT),
            "preferences": {key: get_setting(key, default) for key, default in (
                ("timezone", "Asia/Kuala_Lumpur"), ("digest_time", "08:30"), ("profile", ""),
                ("dot_url", os.getenv("RD_DOT_URL", "https://chatgpt.com/")))},
            "demo": get_setting("demo", False), "active_jobs": active_jobs,
            "market_data": {"provider": "Finnhub" if quote_key() else "Stooq (best effort)",
                            "configured": bool(quote_key()), "key_from_env": bool(os.getenv("FINNHUB_API_KEY"))},
        }

    @app.get("/api/documents")
    def documents(q="", kind="", topic="", ticker="", source="", date_from="", date_to="",
                  limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                  archived: bool = False, who=Depends(actor)):
        result = search_documents(q, kind, topic, ticker, source, date_from, date_to, limit, offset, archived)
        if who == "Dot":
            audit(who, "Searched research library", details={"query": q, "topic": topic, "ticker": ticker,
                                                          "results": result["total"]})
        return result

    @app.post("/api/documents")
    def add_document(body: DocumentInput, who=Depends(actor)):
        fields = body.model_dump()
        if fields["tags"] == []:
            fields["tags"] = None
        if fields["tickers"] == []:
            fields["tickers"] = None
        item, action = save_document(**fields, actor=who)
        return {"document": item, "action": action}

    @app.get("/api/documents/{identity}")
    def document(identity, who=Depends(actor)):
        item = get_document(identity)
        if not item:
            raise HTTPException(404, "Source not found")
        if who == "Dot":
            audit(who, "Read saved source", identity, {"title": item["title"]})
        return item

    @app.patch("/api/documents/{identity}")
    def patch_document(identity: str, body: DocumentPatch, who=Depends(actor)):
        return update_document(identity, body.model_dump(exclude_none=True), who)

    @app.get("/api/documents/{identity}/versions")
    def versions(identity: str):
        with connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT id,created_at,snapshot FROM document_versions WHERE document_id=? ORDER BY id DESC", (identity,))]

    @app.get("/api/documents/{identity}/file/{format}")
    def document_file(identity: str, format: str):
        from .library import safe_data_file
        item = get_document(identity)
        if not item or format not in ("markdown", "original"):
            raise HTTPException(404, "File not found")
        path = safe_data_file(item["md_path"] if format == "markdown" else item["raw_path"])
        name = "".join(c if c.isalnum() or c in " -_" else "_" for c in item["title"])[:100] or "source"
        return FileResponse(path, filename=name + path.suffix, media_type="application/octet-stream")

    @app.post("/api/imports/preview")
    async def preview(file: UploadFile = File(...), who=Depends(actor)):
        identity = uuid.uuid4().hex
        filename = Path((file.filename or "upload.txt").replace("\\", "/")).name
        if Path(filename).suffix.lower() not in SUPPORTED | {".zip"}:
            raise ValueError("Supported files: ZIP, JSON, PDF, Markdown, text, HTML, EML, CSV, VTT and SRT.")
        relative = "uploads/" + identity
        destination, size = data_dir() / relative, 0
        try:
            with destination.open("wb") as stream:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_UPLOAD:
                        raise HTTPException(413, "Upload exceeds 512 MB")
                    stream.write(chunk)
            result = await run_in_threadpool(preview_archive, destination, filename)
        except BaseException as exc:
            destination.unlink(missing_ok=True)
            if isinstance(exc, (HTTPException, KeyboardInterrupt, SystemExit)):
                raise
            raise ValueError("Cannot read this upload: " + str(exc)[:300]) from exc
        finally:
            await file.close()
        with connect() as db:
            db.execute("INSERT INTO uploads VALUES(?,?,?,?,?)", (identity, filename, relative, size, now()))
        audit(who, "Uploaded research for review", identity, {"filename": filename, "bytes": size})
        return {"upload_id": identity, "filename": filename, "size": size, **result}

    @app.post("/api/imports")
    def start_import(body: ImportRequest, who=Depends(actor)):
        with connect() as db:
            if not db.execute("SELECT 1 FROM uploads WHERE id=?", (body.upload_id,)).fetchone():
                raise HTTPException(404, "Upload not found")
        if body.selected_ids == [] and not body.include_files:
            raise ValueError("Select at least one conversation or choose Import all")
        return {"job_id": queue_job("import", body.model_dump(), who)}

    @app.post("/api/import-url")
    def import_url(body: UrlImport, who=Depends(actor)):
        from .network import public_target
        public_target(body.url)
        return {"job_id": queue_job("url", body.model_dump(), who)}

    @app.get("/api/jobs")
    def jobs():
        with connect() as db:
            return [row_dict(row) for row in db.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT 100")]

    @app.post("/api/jobs/{identity}/retry")
    def retry(identity: str, who=Depends(actor)):
        with connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (identity,)).fetchone()
            if not row or row["status"] not in ("failed", "partial"):
                raise ValueError("Only failed or partial jobs can be retried")
            db.execute("UPDATE jobs SET status='queued',errors='[]',processed=0,updated_at=? WHERE id=?", (now(), identity))
        audit(who, "Retried background job", identity)
        return {"ok": True}

    @app.post("/api/jobs/{identity}/undo")
    def undo(identity: str, who=Depends(actor)):
        with connect() as db:
            job = db.execute("SELECT * FROM jobs WHERE id=?", (identity,)).fetchone()
            if not job or job["kind"] not in ("import", "url") or job["status"] not in ("complete", "partial"):
                raise ValueError("Only completed imports can be undone")
            rows = db.execute("SELECT d.id FROM documents d JOIN job_items j ON d.id=j.document_id "
                              "WHERE j.job_id=? AND j.action='created' AND d.updated_at<=? AND d.archived=0",
                              (identity, job["updated_at"])).fetchall()
            for row in rows:
                db.execute("UPDATE documents SET archived=1,updated_at=? WHERE id=?", (now(), row["id"]))
            db.execute("UPDATE jobs SET status='undone',updated_at=? WHERE id=?", (now(), identity))
        audit(who, "Undid import; archived new unchanged records", identity, {"archived": len(rows)})
        return {"archived": len(rows), "note": "Updated existing records and later edits were preserved."}

    @app.get("/api/stocks")
    def stocks():
        return portfolio()

    @app.post("/api/stocks")
    def add_stock(body: Stock, who=Depends(actor)):
        identity, fields = uuid.uuid4().hex, body.model_dump()
        fields["symbol"] = fields["symbol"].upper()
        fields["quote_symbol"] = fields["quote_symbol"].lower()
        with connect() as db:
            db.execute("INSERT INTO stocks(id," + ",".join(fields) + ") VALUES(" + ",".join("?" for _ in range(len(fields) + 1)) + ")",
                       (identity, *fields.values()))
        audit(who, "Added stock", identity, fields)
        return {"id": identity}

    @app.put("/api/stocks/{identity}")
    def edit_stock(identity: str, body: Stock, who=Depends(actor)):
        fields = body.model_dump()
        fields["symbol"] = fields["symbol"].upper()
        fields["quote_symbol"] = fields["quote_symbol"].lower()
        with connect() as db:
            old = db.execute("SELECT * FROM stocks WHERE id=?", (identity,)).fetchone()
            if not old:
                raise HTTPException(404, "Stock not found")
            db.execute("UPDATE stocks SET " + ",".join(k + "=?" for k in fields) + " WHERE id=?",
                       (*fields.values(), identity))
            if any(old[k] != fields[k] for k in ("symbol", "quote_symbol", "currency")):
                db.execute("UPDATE stocks SET last_price=NULL,previous_price=NULL,price_at=NULL,provider=NULL,quote_error=NULL WHERE id=?",
                           (identity,))
        audit(who, "Edited stock", identity, {"before": dict(old), "after": fields})
        return {"ok": True}

    @app.delete("/api/stocks/{identity}")
    def remove_stock(identity: str, who=Depends(actor)):
        with connect() as db:
            old = db.execute("SELECT * FROM stocks WHERE id=?", (identity,)).fetchone()
            if not old:
                raise HTTPException(404, "Stock not found")
            db.execute("DELETE FROM stocks WHERE id=?", (identity,))
        audit(who, "Removed stock from portfolio/watchlist", identity, dict(old))
        return {"ok": True}

    @app.post("/api/stocks/{identity}/price")
    def manual_price(identity: str, body: ManualPrice, who=Depends(actor)):
        with connect() as db:
            old = db.execute("SELECT * FROM stocks WHERE id=?", (identity,)).fetchone()
            if not old:
                raise HTTPException(404, "Stock not found")
            db.execute("UPDATE stocks SET last_price=?,previous_price=?,price_at=?,provider='Manual',quote_error=NULL,demo=0 WHERE id=?",
                       (body.price, body.previous_price, body.as_of, identity))
        audit(who, "Saved manual stock quote", identity, body.model_dump())
        return {"ok": True}

    @app.post("/api/quotes/refresh")
    def quotes(who=Depends(actor)):
        return {"job_id": queue_job("quotes", {}, who)}

    @app.post("/api/market-data/key")
    def save_quote_key(body: QuoteKey, who=Depends(actor)):
        path = data_dir() / "quote-key"
        path.write_text(body.key)
        path.chmod(0o600)
        audit(who, "Configured Finnhub quote connection")
        return {"ok": True}

    @app.delete("/api/market-data/key")
    def remove_quote_key(who=Depends(actor)):
        (data_dir() / "quote-key").unlink(missing_ok=True)
        audit(who, "Removed locally saved quote credential")
        return {"ok": True}

    @app.get("/api/tasks")
    def tasks():
        with connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM tasks ORDER BY due_at")]

    @app.post("/api/tasks")
    def add_task(body: Task, who=Depends(actor)):
        identity, fields = uuid.uuid4().hex, body.model_dump()
        with connect() as db:
            db.execute("INSERT INTO tasks(id," + ",".join(fields) + ",created_at) VALUES(" + ",".join("?" for _ in range(len(fields) + 2)) + ")",
                       (identity, *fields.values(), now()))
        audit(who, "Created calendar task", identity, fields)
        return {"id": identity}

    @app.put("/api/tasks/{identity}")
    def edit_task(identity: str, body: Task, who=Depends(actor)):
        fields = body.model_dump()
        with connect() as db:
            if not db.execute("SELECT 1 FROM tasks WHERE id=?", (identity,)).fetchone():
                raise HTTPException(404, "Task not found")
            db.execute("UPDATE tasks SET " + ",".join(k + "=?" for k in fields) + " WHERE id=?",
                       (*fields.values(), identity))
        audit(who, "Updated calendar task", identity, fields)
        return {"ok": True}

    @app.delete("/api/tasks/{identity}")
    def delete_task(identity: str, who=Depends(actor)):
        with connect() as db:
            db.execute("DELETE FROM tasks WHERE id=?", (identity,))
        audit(who, "Removed calendar task", identity)
        return {"ok": True}

    @app.get("/api/calendar.ics")
    def calendar_ics():
        def escaped(text):
            return text.replace("\\", "\\\\").replace("\r", "").replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;")
        with connect() as db:
            rows = db.execute("SELECT * FROM tasks WHERE done=0 ORDER BY due_at").fetchall()
        lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Research Desk//Calendar//EN"]
        for row in rows:
            due = datetime.fromisoformat(row["due_at"]).astimezone(ZoneInfo("UTC"))
            lines.extend(["BEGIN:VEVENT", "UID:" + row["id"] + "@research-desk",
                          "DTSTAMP:" + datetime.now(ZoneInfo("UTC")).strftime("%Y%m%dT%H%M%SZ"),
                          "DTSTART:" + due.strftime("%Y%m%dT%H%M%SZ"),
                          "DTEND:" + (due + timedelta(minutes=30)).strftime("%Y%m%dT%H%M%SZ"),
                          "SUMMARY:" + escaped(row["title"]), "DESCRIPTION:" + escaped(row["notes"]), "END:VEVENT"])
        lines.append("END:VCALENDAR")
        return Response("\r\n".join(lines) + "\r\n", media_type="text/calendar",
                        headers={"Content-Disposition": 'attachment; filename="research-desk.ics"'})

    @app.get("/api/sources")
    def sources():
        with connect() as db:
            return [row_dict(row) for row in db.execute("SELECT * FROM sources ORDER BY name")]

    @app.post("/api/sources")
    def add_source(body: Source, who=Depends(actor)):
        if body.kind == "rss" and not body.url:
            raise ValueError("An RSS connection needs its feed URL")
        identity, fields = uuid.uuid4().hex, body.model_dump()
        fields["topics"] = json.dumps(fields["topics"])
        with connect() as db:
            db.execute("INSERT INTO sources(id," + ",".join(fields) + ",created_at) VALUES(" + ",".join("?" for _ in range(len(fields) + 2)) + ")",
                       (identity, *fields.values(), now()))
        audit(who, "Connected research source", identity, body.model_dump())
        return {"id": identity}

    @app.put("/api/sources/{identity}")
    def edit_source(identity: str, body: Source, who=Depends(actor)):
        fields = body.model_dump()
        fields["topics"] = json.dumps(fields["topics"])
        with connect() as db:
            if not db.execute("SELECT 1 FROM sources WHERE id=?", (identity,)).fetchone():
                raise HTTPException(404, "Connection not found")
            db.execute("UPDATE sources SET " + ",".join(k + "=?" for k in fields) + " WHERE id=?",
                       (*fields.values(), identity))
        audit(who, "Updated research connection", identity)
        return {"ok": True}

    @app.delete("/api/sources/{identity}")
    def delete_source(identity: str, who=Depends(actor)):
        with connect() as db:
            db.execute("DELETE FROM sources WHERE id=?", (identity,))
        audit(who, "Removed connection; saved research retained", identity)
        return {"ok": True}

    @app.post("/api/sources/{identity}/refresh")
    def source_refresh(identity: str, who=Depends(actor)):
        return {"job_id": queue_job("feed", {"source_id": identity}, who)}

    @app.get("/api/digests")
    def digests():
        with connect() as db:
            return [row_dict(row) for row in db.execute("SELECT * FROM digests ORDER BY day DESC,created_at DESC LIMIT 100")]

    @app.post("/api/digests")
    def digest_publish(body: Digest, who=Depends(actor)):
        identity = publish_digest(body.day, body.title, body.content, body.document_ids,
                                  "Dot research" if who == "Dot" else "Owner research", who)
        return {"id": identity}

    @app.post("/api/digests/generate")
    def digest_generate(who=Depends(actor)):
        return {"id": generate_digest(who)}

    @app.get("/api/activity")
    def activity(q="", actor_filter="", limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
        clauses, args = ["1=1"], []
        if q:
            clauses.append("(action LIKE ? OR details LIKE ?)")
            args += ["%" + q + "%", "%" + q + "%"]
        if actor_filter:
            clauses.append("actor=?")
            args.append(actor_filter)
        with connect() as db:
            rows = db.execute("SELECT * FROM activity WHERE " + " AND ".join(clauses)
                              + " ORDER BY id DESC LIMIT ? OFFSET ?", args + [limit, offset]).fetchall()
        return [row_dict(row) for row in rows]

    @app.put("/api/layout")
    def layout(body: list[LayoutItem], who=Depends(actor)):
        if len(body) != 6 or len({x.id for x in body}) != 6:
            raise ValueError("The layout must contain all six distinct dashboard cards")
        result = []
        for item in body:
            if item.x + item.w > 12:
                raise ValueError("A card is outside the dashboard grid")
            result.append(item.model_dump())
        set_setting("layout", result)
        audit(who, "Saved dashboard layout")
        return {"layout": result}

    @app.post("/api/layout/reset")
    def reset_layout(who=Depends(actor)):
        set_setting("layout", DEFAULT_LAYOUT)
        audit(who, "Restored original dashboard layout")
        return {"layout": DEFAULT_LAYOUT}

    @app.put("/api/preferences")
    def preferences(body: Preferences, who=Depends(actor)):
        for key, value in body.model_dump().items():
            set_setting(key, value)
        audit(who, "Updated investor profile and research instructions")
        return {"ok": True}

    @app.post("/api/demo")
    def demo(who=Depends(actor)):
        from .seed import seed_demo
        seed_demo()
        audit(who, "Loaded labelled demonstration data")
        return {"ok": True}

    @app.delete("/api/demo")
    def clear_demo(who=Depends(actor)):
        with connect() as db:
            db.execute("UPDATE documents SET archived=1 WHERE demo=1")
            db.execute("DELETE FROM stocks WHERE demo=1")
            for identity in get_setting("demo_tasks", []):
                db.execute("DELETE FROM tasks WHERE id=?", (identity,))
            for identity in get_setting("demo_digests", []):
                db.execute("DELETE FROM digests WHERE id=?", (identity,))
        set_setting("demo", False)
        audit(who, "Removed demonstration data")
        return {"ok": True}

    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    return app


app = create_app()
