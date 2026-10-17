import csv
import email
import io
import json
import stat
import zipfile
from datetime import datetime, timezone
from email import policy
from pathlib import PurePosixPath

import trafilatura
from pypdf import PdfReader

from .db import audit, connect, now
from .library import save_document

SUPPORTED = {".txt", ".md", ".markdown", ".html", ".htm", ".pdf", ".eml", ".vtt", ".srt", ".csv", ".json"}
MAX_UNCOMPRESSED = 768 * 1024 * 1024


def iso_time(value):
    try:
        return datetime.fromtimestamp(float(value), timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def conversations_from_json(data):
    parsed = json.loads(data)
    if isinstance(parsed, dict) and "conversations" in parsed:
        parsed = parsed["conversations"]
    if isinstance(parsed, dict) and "mapping" in parsed:
        parsed = [parsed]
    if isinstance(parsed, list) and all(isinstance(x, dict) and "mapping" in x for x in parsed):
        return parsed
    return None


def archive_entries(path):
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) > 20000 or sum(x.file_size for x in entries) > MAX_UNCOMPRESSED:
            raise ValueError("Archive exceeds the file-count or uncompressed-size limit")
        for entry in entries:
            name = PurePosixPath(entry.filename.replace("\\", "/"))
            mode = entry.external_attr >> 16
            if name.is_absolute() or ".." in name.parts or ":" in name.parts[0] or stat.S_ISLNK(mode):
                raise ValueError("Unsafe archive path or symbolic link")
            if entry.flag_bits & 1:
                raise ValueError("Encrypted archives are not supported")
        for entry in entries:
            if not entry.is_dir():
                yield entry.filename, archive.read(entry)


def preview_archive(path, filename):
    entries = archive_entries(path) if filename.lower().endswith(".zip") else [(filename, path.read_bytes())]
    conversations, files = [], []
    for name, data in entries:
        if PurePosixPath(name).name == "conversations.json" or filename.lower().endswith(".json"):
            try:
                found = conversations_from_json(data)
            except (ValueError, UnicodeError):
                found = None
            if found is not None:
                conversations.extend({"id": str(c.get("id") or c.get("conversation_id") or i),
                                      "title": c.get("title") or "Untitled conversation",
                                      "created_at": iso_time(c.get("create_time"))}
                                     for i, c in enumerate(found))
                continue
        files.append({"name": name, "supported": PurePosixPath(name).suffix.lower() in SUPPORTED})
    return {"conversations": conversations, "files": files, "conversation_count": len(conversations)}


def conversation_document(conversation, fallback_id):
    messages = []
    mapping = conversation.get("mapping", {})
    ordered = sorted(mapping.items(), key=lambda pair: (
        (pair[1].get("message") or {}).get("create_time") or 0, pair[0]))
    for node_id, node in ordered:
        message = node.get("message")
        if not message:
            continue
        role = (message.get("author") or {}).get("role", "unknown")
        content = message.get("content") or {}
        parts = content.get("parts") or [content.get("text", "")]
        text = "\n".join(part if isinstance(part, str) else json.dumps(part, ensure_ascii=False) for part in parts)
        if not text.strip():
            continue
        stamp = iso_time(message.get("create_time")) or "Date unknown"
        messages.append("## " + role.title() + " · " + stamp + "\n\n"
                        + "Message ID: " + str(node_id) + " · Parent: " + str(node.get("parent") or "root")
                        + "\n\n" + text)
    if not messages:
        raise ValueError("Conversation contains no readable messages")
    title = conversation.get("title") or "Untitled conversation"
    identity = str(conversation.get("id") or conversation.get("conversation_id") or fallback_id)
    notice = (
        "> Imported AI conversation. Statements may be interpretations or unverified claims. "
        "All available message branches are preserved below; parent IDs identify their relationships. "
        "Referenced files and web pages are not guaranteed to be included.\n\n"
    )
    return dict(
        title=title, content=notice + "\n\n".join(messages),
        raw=json.dumps(conversation, ensure_ascii=False, sort_keys=True).encode(),
        extension=".json", kind="chatgpt", source_name="ChatGPT research",
        external_id="chatgpt:" + identity, ai_generated=True,
        created_at=iso_time(conversation.get("create_time")),
        published_at=None,
    )


def extract_file(name, data):
    extension = PurePosixPath(name).suffix.lower()
    title = PurePosixPath(name).stem.replace("_", " ")
    metadata = {"kind": "document", "source_name": "Manual upload"}
    if extension == ".pdf":
        reader = PdfReader(io.BytesIO(data))
        text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
        if not text.strip():
            raise ValueError("PDF has no text layer; OCR is required before import")
    elif extension in (".html", ".htm"):
        extracted = trafilatura.bare_extraction(data.decode("utf-8", errors="replace"), with_metadata=True)
        if extracted:
            title = extracted.title or title
            text = extracted.text or ""
        else:
            text = ""
        metadata["kind"] = "article"
    elif extension == ".eml":
        message = email.message_from_bytes(data, policy=policy.default)
        title = str(message.get("Subject") or title)
        body = message.get_body(preferencelist=("plain", "html"))
        text = body.get_content() if body else ""
        if body and body.get_content_type() == "text/html":
            text = trafilatura.extract(text) or ""
        metadata.update(kind="email", source_name=str(message.get("From") or "Email"))
        try:
            from email.utils import parsedate_to_datetime
            metadata["published_at"] = parsedate_to_datetime(str(message["Date"])).isoformat()
        except (ValueError, TypeError):
            pass
        text = "From: " + str(message.get("From") or "") + "\nDate: " + str(message.get("Date") or "") + "\n\n" + text
    elif extension == ".csv":
        rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))
        text = "\n".join(" | ".join(row) for row in rows)
    else:
        text = data.decode("utf-8-sig")
        if extension in (".vtt", ".srt"):
            metadata["kind"] = "transcript"
        if extension == ".json":
            text = json.dumps(json.loads(text), indent=2, ensure_ascii=False)
    return dict(title=title, content=text, raw=data, extension=extension, **metadata)


def import_upload(job, path, filename, selected_ids=None, include_files=True):
    entries = archive_entries(path) if filename.lower().endswith(".zip") else [(filename, path.read_bytes())]
    with connect() as db:
        existing_items = {row[0] for row in db.execute("SELECT document_id FROM job_items WHERE job_id=?", (job["id"],))}
    processed, imported, duplicates, total, errors = 0, len(existing_items), 0, 0, []
    selected = set(selected_ids) if selected_ids is not None else None

    def progress():
        with connect() as db:
            db.execute("UPDATE jobs SET total=?,processed=?,imported=?,duplicates=?,errors=?,updated_at=? WHERE id=?",
                       (total, processed, imported, duplicates, json.dumps(errors), now(), job["id"]))

    def save_one(fields):
        nonlocal processed, imported, duplicates
        item, action = save_document(**fields, actor=job["payload"].get("actor", "Owner"))
        processed += 1
        if action == "duplicate":
            duplicates += item["id"] not in existing_items
        else:
            imported += 1
            with connect() as db:
                db.execute("INSERT OR IGNORE INTO job_items VALUES(?,?,?)", (job["id"], item["id"], action))
        progress()

    for name, data in entries:
        if name.startswith("__MACOSX/") or PurePosixPath(name).name.startswith("."):
            continue
        extension = PurePosixPath(name).suffix.lower()
        try:
            found = None
            if extension == ".json":
                try:
                    found = conversations_from_json(data)
                except (ValueError, UnicodeError):
                    pass
            if found is not None:
                chosen = [(i, c) for i, c in enumerate(found) if selected is None or
                          str(c.get("id") or c.get("conversation_id") or i) in selected]
                total += len(chosen)
                progress()
                for i, conversation in chosen:
                    try:
                        save_one(conversation_document(conversation, i))
                    except Exception as exc:
                        processed += 1
                        errors.append({"file": conversation.get("title", name), "error": str(exc)[:300]})
                        progress()
            elif extension in SUPPORTED:
                if include_files:
                    total += 1
                    save_one(extract_file(name, data))
            else:
                if include_files:
                    errors.append({"file": name, "error": "Original preserved in archive; extraction is unsupported"})
                    progress()
        except Exception as exc:
            processed += 1
            errors.append({"file": name, "error": str(exc)[:300]})
            progress()
    audit("System", "Completed research import", job["id"],
          {"imported": imported, "duplicates": duplicates, "issues": len(errors)})
