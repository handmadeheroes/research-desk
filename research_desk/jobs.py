import csv
import io
import json
import os
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import feedparser
import trafilatura

from .db import audit, connect, data_dir, get_setting, now, row_dict, set_setting
from .ingestion import import_upload, iso_time
from .library import safe_data_file, save_document
from .network import fetch_public


def queue_job(kind, payload, actor="Owner"):
    if kind == "quotes":
        with connect() as db:
            active = db.execute("SELECT id FROM jobs WHERE kind='quotes' AND status IN ('queued','running') LIMIT 1").fetchone()
        if active:
            return active[0]
    identity = uuid.uuid4().hex
    with connect() as db:
        db.execute("INSERT INTO jobs(id,kind,status,payload,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                   (identity, kind, "queued", json.dumps({**payload, "actor": actor}), now(), now()))
    audit(actor, "Queued " + kind, identity)
    return identity


def portfolio():
    with connect() as db:
        stocks = [dict(row) for row in db.execute("SELECT * FROM stocks ORDER BY category,symbol")]
        history = [dict(row) for row in db.execute("SELECT * FROM portfolio_history ORDER BY day")]
    totals, day_changes, costs, missing = {}, {}, {}, []
    for stock in stocks:
        if stock["category"] != "holding" or stock["shares"] <= 0:
            continue
        if stock["last_price"] is None:
            missing.append(stock["symbol"])
            continue
        currency = stock["currency"]
        totals[currency] = totals.get(currency, 0) + stock["shares"] * stock["last_price"]
        if stock["previous_price"] is not None:
            day_changes[currency] = day_changes.get(currency, 0) + stock["shares"] * (
                stock["last_price"] - stock["previous_price"])
        if stock["average_cost"] is not None:
            costs[currency] = costs.get(currency, 0) + stock["shares"] * stock["average_cost"]
    return {"stocks": stocks, "totals": totals, "day_changes": day_changes, "costs": costs,
            "missing": missing, "history": history}


def quote_key():
    path = data_dir() / "quote-key"
    return os.getenv("FINNHUB_API_KEY", "").strip() or (path.read_text().strip() if path.exists() else "")


def refresh_quotes(job):
    with connect() as db:
        stocks = [dict(row) for row in db.execute("SELECT * FROM stocks")]
    errors = []
    for index, stock in enumerate(stocks):
        started = time.monotonic()
        try:
            if not stock["quote_symbol"].lower().endswith(".us") or stock["currency"] != "USD":
                raise ValueError("Automatic quotes support USD-denominated US stocks (.us). Use a manual quote for this market.")
            key = quote_key()
            if key:
                raw, _, _ = fetch_public("https://finnhub.io/api/v1/quote?" + urlencode({"symbol": stock["symbol"]}),
                                         headers={"X-Finnhub-Token": key})
                quote = json.loads(raw)
                if quote.get("error"):
                    raise ValueError("Finnhub rejected the request. Check your key, symbol and plan limits.")
                price, previous = float(quote.get("c") or 0), float(quote.get("pc") or 0)
                as_of = iso_time(quote.get("t"))
                if not as_of:
                    raise ValueError("Finnhub returned no quote timestamp")
                provider = "Finnhub quote"
            else:
                end = datetime.now(ZoneInfo("America/New_York")).date()
                query = urlencode({"s": stock["quote_symbol"].lower(), "i": "d",
                                   "d1": (end - timedelta(days=16)).strftime("%Y%m%d"), "d2": end.strftime("%Y%m%d")})
                raw, _, _ = fetch_public("https://stooq.com/q/d/l/?" + query)
                rows = sorted(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))), key=lambda row: row.get("Date", ""))
                valid = [row for row in rows if row.get("Close") not in (None, "", "N/D") and row.get("Date")]
                if len(valid) < 2:
                    raise ValueError("Stooq supplied no usable history. Connect a free Finnhub key in Settings or use a manual quote.")
                price, previous = float(valid[-1]["Close"]), float(valid[-2]["Close"])
                as_of, provider = valid[-1]["Date"], "Stooq daily close"
            if not 0 < price < 10000000 or not 0 < previous < 10000000:
                raise ValueError("Source returned an invalid price")
            with connect() as db:
                db.execute("UPDATE stocks SET last_price=?,previous_price=?,price_at=?,provider=?,"
                           "quote_error=NULL,demo=0 WHERE id=?", (price, previous, as_of, provider, stock["id"]))
            audit("System", "Retrieved stock quote", stock["id"],
                  {"symbol": stock["symbol"], "price": price, "as_of": as_of, "source": provider})
        except Exception as exc:
            errors.append({"symbol": stock["symbol"], "error": str(exc)[:300]})
            with connect() as db:
                db.execute("UPDATE stocks SET quote_error=? WHERE id=?", (str(exc)[:300], stock["id"]))
        finally:
            if quote_key():
                time.sleep(max(0, 1.25 - (time.monotonic() - started)))
        with connect() as db:
            db.execute("UPDATE jobs SET total=?,processed=?,errors=?,updated_at=? WHERE id=?",
                       (len(stocks), index + 1, json.dumps(errors), now(), job["id"]))
    values = portfolio()
    for currency, value in values["totals"].items():
        if not values["missing"]:
            with connect() as db:
                db.execute("INSERT OR REPLACE INTO portfolio_history VALUES(?,?,?)",
                           (now()[:10], currency, value))


def ingest_url(job):
    payload = job["payload"]
    raw, mime, final_url = fetch_public(payload["url"])
    if "text/html" not in mime and "application/xhtml" not in mime:
        raise ValueError("This URL is not an HTML article. Download and upload the document instead.")
    article = trafilatura.bare_extraction(raw.decode("utf-8", errors="replace"), with_metadata=True)
    if not article or not article.text:
        raise ValueError("No article text found; the page may require a login or a different source.")
    item, action = save_document(
        title=payload.get("title") or article.title or final_url,
        content=article.text, raw=raw, extension=".html", kind="article",
        source_name=payload.get("source_name") or article.sitename or "Web article",
        url=final_url, published_at=article.date or None, external_id="url:" + final_url,
        actor=payload.get("actor", "Owner"),
    )
    with connect() as db:
        db.execute("UPDATE jobs SET total=1,processed=1,imported=?,duplicates=? WHERE id=?",
                   (int(action != "duplicate"), int(action == "duplicate"), job["id"]))
        if action != "duplicate":
            db.execute("INSERT OR IGNORE INTO job_items VALUES(?,?,?)", (job["id"], item["id"], action))


def refresh_source(job):
    identity = job["payload"]["source_id"]
    with connect() as db:
        source = row_dict(db.execute("SELECT * FROM sources WHERE id=?", (identity,)).fetchone())
    if not source or source["kind"] != "rss":
        raise ValueError("Choose an RSS or Atom connection to refresh")
    try:
        raw, _, _ = fetch_public(source["url"])
        feed = feedparser.parse(raw)
        if not feed.entries:
            raise ValueError("No feed entries found at this URL")
        imported, duplicates = 0, 0
        entries = feed.entries[:100]
        for index, entry in enumerate(entries):
            content = (entry.get("content") or [{}])[0].get("value") or entry.get("summary", "")
            text = trafilatura.extract(content) or re_strip(content)
            if not text:
                text = entry.get("title", "Untitled feed entry")
            text = "> Saved feed content; the linked original may contain additional material.\n\n" + text
            published = entry.get("published_parsed") or entry.get("updated_parsed")
            published_at = iso_time(__import__("calendar").timegm(published)) if published else None
            _, action = save_document(
                title=entry.get("title", "Untitled feed entry"), content=text,
                raw=json.dumps(dict(entry), default=str, sort_keys=True).encode(), extension=".json",
                kind="article", source_name=source["name"], url=entry.get("link", ""),
                published_at=published_at, tags=source["topics"] or None,
                external_id="feed:" + identity + ":" + (entry.get("id") or entry.get("link") or entry.get("title", "")),
                actor="System",
            )
            imported += action != "duplicate"
            duplicates += action == "duplicate"
            with connect() as db:
                db.execute("UPDATE jobs SET total=?,processed=?,imported=?,duplicates=?,updated_at=? WHERE id=?",
                           (len(entries), index + 1, imported, duplicates, now(), job["id"]))
        with connect() as db:
            db.execute("UPDATE sources SET last_fetched=?,last_error=NULL WHERE id=?", (now(), identity))
        audit("System", "Retrieved feed", identity, {"source": source["name"], "imported": imported})
    except Exception as exc:
        with connect() as db:
            db.execute("UPDATE sources SET last_error=? WHERE id=?", (str(exc)[:300], identity))
        raise


def re_strip(value):
    import re
    from html import unescape
    return unescape(re.sub("<[^>]+>", " ", value)).strip()


def publish_digest(day, title, content, document_ids, method, actor):
    identity = uuid.uuid4().hex
    with connect() as db:
        for document_id in document_ids:
            if not db.execute("SELECT 1 FROM documents WHERE id=? AND archived=0", (document_id,)).fetchone():
                raise ValueError("A cited library source is unavailable")
        db.execute("INSERT INTO digests VALUES(?,?,?,?,?,?,?)",
                   (identity, day, title, content, json.dumps(document_ids), method, now()))
    audit(actor, "Published daily digest", identity, {"sources": len(document_ids), "method": method})
    return identity


def generate_digest(actor="System"):
    zone = ZoneInfo(get_setting("timezone", "Asia/Kuala_Lumpur"))
    day = datetime.now(zone).date().isoformat()
    cutoff = (datetime.now(zone) - timedelta(days=1)).astimezone(timezone.utc).isoformat()
    with connect() as db:
        rows = db.execute("SELECT id,title,summary,source_name,kind FROM documents WHERE archived=0 AND retrieved_at>=? "
                          "ORDER BY retrieved_at DESC LIMIT 20", (cutoff,)).fetchall()
    if not rows:
        raise ValueError("No new research in the last 24 hours. Add sources or ask your dot to publish a digest.")
    sections = ["# Morning brief\n\n"
                "Local excerpt digest. These are saved-source excerpts, not an AI investment analysis.\n"]
    for row in rows:
        sections.append("## " + row["title"] + "\n\n" + row["summary"] + "\n\n"
                        + "[Read saved source](#document/" + row["id"] + ") · " + row["source_name"])
    return publish_digest(day, "Morning brief", "\n\n".join(sections), [row["id"] for row in rows],
                          "local excerpts", actor)


class Worker:
    def __init__(self):
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self.loop, daemon=True, name="research-desk-worker")
        self.next_schedule = 0.0

    def start(self):
        with connect() as db:
            db.execute("UPDATE jobs SET status='queued' WHERE status='running'")
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=3)

    def tick_schedule(self):
        current = datetime.now(ZoneInfo(get_setting("timezone", "Asia/Kuala_Lumpur")))
        if current.strftime("%H:%M") >= "03:00" and get_setting("last_daily_backup") != current.date().isoformat():
            from .cli import backup
            path = backup()
            retention = max(2, int(os.getenv("RD_BACKUP_RETENTION", "7")))
            for old in sorted(path.parent.glob("research-desk-*.zip"), reverse=True)[retention:]:
                old.unlink()
            set_setting("last_daily_backup", current.date().isoformat())
        if current.strftime("%H:%M") >= "08:00" and get_setting("last_daily_quotes") != current.date().isoformat():
            with connect() as db:
                has_stocks = db.execute("SELECT 1 FROM stocks WHERE demo=0 LIMIT 1").fetchone()
            if has_stocks:
                queue_job("quotes", {}, "System")
            set_setting("last_daily_quotes", current.date().isoformat())
        last = get_setting("last_scheduled_digest", "")
        if current.strftime("%H:%M") >= get_setting("digest_time", "08:30") and last != current.date().isoformat():
            try:
                generate_digest()
            except ValueError:
                pass
            set_setting("last_scheduled_digest", current.date().isoformat())
        last_feed = get_setting("last_feed_check", 0)
        interval = max(15, int(os.getenv("RD_FEED_INTERVAL_MINUTES", "60"))) * 60
        if time.time() - last_feed > interval:
            with connect() as db:
                ids = [row[0] for row in db.execute("SELECT id FROM sources WHERE enabled=1 AND kind='rss'")]
            for identity in ids:
                queue_job("feed", {"source_id": identity}, "System")
            set_setting("last_feed_check", time.time())

    def loop(self):
        while not self.stop_event.is_set():
            try:
                if time.time() >= self.next_schedule:
                    self.tick_schedule()
                    self.next_schedule = time.time() + 60
                with connect() as db:
                    row = db.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created_at LIMIT 1").fetchone()
                    if row:
                        db.execute("UPDATE jobs SET status='running',updated_at=? WHERE id=?", (now(), row["id"]))
                if row:
                    self.execute(row_dict(row))
                else:
                    self.stop_event.wait(1)
            except Exception as exc:
                audit("System", "Background worker error", details={"error": str(exc)[:300]})
                self.stop_event.wait(3)

    def execute(self, job):
        try:
            if job["kind"] == "import":
                with connect() as db:
                    upload = db.execute("SELECT * FROM uploads WHERE id=?", (job["payload"]["upload_id"],)).fetchone()
                if not upload:
                    raise ValueError("Uploaded archive unavailable")
                import_upload(job, safe_data_file(upload["path"]), upload["filename"],
                              job["payload"].get("selected_ids"), job["payload"].get("include_files", True))
            elif job["kind"] == "quotes":
                refresh_quotes(job)
            elif job["kind"] == "feed":
                refresh_source(job)
            elif job["kind"] == "url":
                ingest_url(job)
            else:
                raise ValueError("Unknown background job")
            with connect() as db:
                errors = json.loads(db.execute("SELECT errors FROM jobs WHERE id=?", (job["id"],)).fetchone()[0])
                db.execute("UPDATE jobs SET status=?,updated_at=? WHERE id=?",
                           ("partial" if errors else "complete", now(), job["id"]))
        except Exception as exc:
            with connect() as db:
                db.execute("UPDATE jobs SET status='failed',errors=?,updated_at=? WHERE id=?",
                           (json.dumps([{"error": str(exc)[:500]}]), now(), job["id"]))
            audit("System", "Job failed", job["id"], {"error": str(exc)[:300]})
