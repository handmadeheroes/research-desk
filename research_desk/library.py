import hashlib
import json
import re
import uuid
from urllib.parse import urlsplit

from .db import audit, connect, data_dir, now, row_dict

KINDS = {"article", "email", "transcript", "document", "chatgpt", "note"}
TOPICS = {
    "AI": r"\b(ai|artificial intelligence|machine learning|data cent[er]+)\b",
    "Semiconductors": r"\b(semiconductor|chip|gpu|nvidia)\b",
    "Macro": r"\b(inflation|interest rate|central bank|gdp|macro)\b",
    "Earnings": r"\b(earnings|revenue|quarterly|margin)\b",
    "Cloud": r"\b(cloud|azure|aws)\b",
    "Portfolio": r"\b(portfolio|allocation|position sizing)\b",
    "Energy": r"\b(oil|energy|natural gas)\b",
}
COMPANIES = {"microsoft": "MSFT", "nvidia": "NVDA", "apple": "AAPL", "amazon": "AMZN",
             "alphabet": "GOOGL", "tesla": "TSLA", "meta platforms": "META"}


def classify(text):
    sample = text[:100000]
    tags = [name for name, pattern in TOPICS.items() if re.search(pattern, sample, re.I)]
    tickers = set(re.findall(r"\$([A-Z]{1,6})\b", sample))
    tickers.update(symbol for name, symbol in COMPANIES.items() if name in sample.lower())
    with connect() as db:
        for row in db.execute("SELECT symbol FROM stocks"):
            if re.search(r"\b" + re.escape(row[0]) + r"\b", sample):
                tickers.add(row[0])
    return tags or ["Unsorted"], sorted(tickers)


def excerpt(content, length=300):
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", content)
    text = re.sub(r"[#>*_\n]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()[:length]


def write_markdown(item):
    relative = "markdown/" + item["id"] + "-" + uuid.uuid4().hex[:10] + ".md"
    fields = {k: item.get(k) for k in (
        "id", "title", "kind", "source_name", "url", "published_at", "created_at",
        "retrieved_at", "tags", "tickers", "ai_generated",
    )}
    text = "---\n" + json.dumps(fields, ensure_ascii=False, indent=2) + "\n---\n\n"
    text += "# " + item["title"] + "\n\n" + item["content"]
    (data_dir() / relative).write_text(text, encoding="utf-8")
    return relative


def save_document(*, title, content, raw=None, extension=".txt", kind="document", source_name="Manual upload",
                  url="", published_at=None, created_at=None, tags=None, tickers=None, summary=None,
                  external_id=None, ai_generated=False, actor="Owner", demo=False):
    if kind not in KINDS:
        raise ValueError("Unsupported document type")
    if not content.strip():
        raise ValueError("No readable text found")
    # Feed/HTML metadata bypasses API models. Never turn untrusted schemes into links.
    try:
        parsed_url = urlsplit(url)
        if parsed_url.scheme not in ("http", "https") or not parsed_url.hostname or parsed_url.username or parsed_url.password:
            url = ""
    except ValueError:
        url = ""
    raw = raw if raw is not None else content.encode()
    digest = hashlib.sha256(raw).hexdigest()
    with connect() as db:
        old = db.execute("SELECT * FROM documents WHERE external_id=?", (external_id,)).fetchone() if external_id else None
        if old is None:
            old = db.execute("SELECT * FROM documents WHERE sha256=? AND archived=0", (digest,)).fetchone()
        old = row_dict(old)
    if old and old["sha256"] == digest and not old["archived"]:
        return old, "duplicate"
    auto_tags, auto_tickers = classify(title + "\n" + content)
    identity = old["id"] if old else uuid.uuid4().hex
    safe_ext = extension if re.fullmatch(r"\.[a-zA-Z0-9]{1,10}", extension) else ".bin"
    raw_path = "originals/" + identity + "-" + uuid.uuid4().hex[:10] + safe_ext
    (data_dir() / raw_path).write_bytes(raw)
    item = {
        "id": identity, "title": title[:300], "content": content, "kind": kind,
        "source_name": source_name[:200], "url": url, "published_at": published_at,
        "created_at": created_at or now(), "retrieved_at": now(), "updated_at": now(),
        "tags": tags if tags is not None else auto_tags, "tickers": tickers if tickers is not None else auto_tickers,
        "summary": summary if summary is not None else excerpt(content), "raw_path": raw_path, "md_path": "",
        "sha256": digest, "external_id": external_id, "ai_generated": int(ai_generated),
        "archived": 0, "demo": int(demo),
    }
    item["md_path"] = write_markdown(item)
    with connect() as db:
        if old:
            db.execute("INSERT INTO document_versions(document_id,snapshot,created_at) VALUES(?,?,?)",
                       (identity, json.dumps(old), now()))
            fields = [k for k in item if k != "id"]
            db.execute("UPDATE documents SET " + ",".join(k + "=?" for k in fields) + " WHERE id=?",
                       tuple(json.dumps(item[k]) if k in ("tags", "tickers") else item[k] for k in fields) + (identity,))
        else:
            fields = list(item)
            db.execute("INSERT INTO documents(" + ",".join(fields) + ") VALUES(" + ",".join("?" for _ in fields) + ")",
                       tuple(json.dumps(item[k]) if k in ("tags", "tickers") else item[k] for k in fields))
    audit(actor, "Updated research" if old else "Saved research", identity, {"title": title, "source": source_name})
    return item, "updated" if old else "created"


def search_documents(query="", kind="", topic="", ticker="", source="", date_from="", date_to="",
                     limit=50, offset=0, archived=False):
    where, args, join = ["d.archived=?"], [int(archived)], ""
    if query.strip():
        words = re.findall(r"\w+", query, re.UNICODE)[:20]
        if words:
            join = " JOIN documents_fts f ON d.rowid=f.rowid"
            where.append("documents_fts MATCH ?")
            args.append(" AND ".join('"' + word.replace('"', '""') + '"*' for word in words))
    for key, value in (("kind", kind), ("source_name", source)):
        if value:
            where.append("d." + key + "=?")
            args.append(value)
    for key, value in (("tags", topic), ("tickers", ticker)):
        if value:
            where.append("EXISTS (SELECT 1 FROM json_each(d." + key + ") WHERE value=?)")
            args.append(value)
    if date_from:
        where.append("d.created_at>=?")
        args.append(date_from)
    if date_to:
        where.append("d.created_at<?")
        args.append(date_to + "T23:59:59.999999Z")
    clause = " FROM documents d" + join + " WHERE " + " AND ".join(where)
    columns = "d.id,d.title,d.kind,d.source_name,d.url,d.published_at,d.created_at,d.retrieved_at,d.updated_at,"
    columns += "d.tags,d.tickers,d.summary,d.ai_generated,d.archived,d.demo"
    with connect() as db:
        count = db.execute("SELECT count(*)" + clause, args).fetchone()[0]
        rows = db.execute("SELECT " + columns + clause + " ORDER BY d.created_at DESC LIMIT ? OFFSET ?",
                          args + [min(max(limit, 1), 200), max(offset, 0)]).fetchall()
    return {"items": [row_dict(row) for row in rows], "total": count}


def get_document(identity):
    with connect() as db:
        return row_dict(db.execute("SELECT * FROM documents WHERE id=?", (identity,)).fetchone())


def update_document(identity, changes, actor):
    old = get_document(identity)
    if not old:
        raise ValueError("Document not found")
    item = {**old, **changes, "updated_at": now()}
    item["md_path"] = write_markdown(item)
    with connect() as db:
        db.execute("INSERT INTO document_versions(document_id,snapshot,created_at) VALUES(?,?,?)",
                   (identity, json.dumps(old), now()))
        fields = ("title", "summary", "tags", "tickers", "archived", "updated_at", "md_path")
        db.execute("UPDATE documents SET " + ",".join(k + "=?" for k in fields) + " WHERE id=?",
                   tuple(json.dumps(item[k]) if k in ("tags", "tickers") else item[k] for k in fields) + (identity,))
    audit(actor, "Changed research metadata", identity, {"before": {k: old[k] for k in changes}, "after": changes})
    return item


def safe_data_file(relative):
    root = data_dir()
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError("File unavailable")
    return path
