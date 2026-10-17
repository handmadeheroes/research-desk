import hashlib
import json
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DEFAULT_LAYOUT = [
    {"id": "digest", "x": 0, "y": 0, "w": 8, "h": 9, "minW": 4, "minH": 5},
    {"id": "portfolio", "x": 8, "y": 0, "w": 4, "h": 6, "minW": 3, "minH": 5},
    {"id": "calendar", "x": 8, "y": 6, "w": 4, "h": 7, "minW": 3, "minH": 5},
    {"id": "library", "x": 0, "y": 9, "w": 8, "h": 7, "minW": 4, "minH": 4},
    {"id": "activity", "x": 8, "y": 13, "w": 4, "h": 5, "minW": 3, "minH": 3},
    {"id": "upload", "x": 0, "y": 16, "w": 8, "h": 2, "minW": 3, "minH": 2},
]


def now():
    return datetime.now(timezone.utc).isoformat()


def data_dir():
    p = Path(os.environ.get("RD_DATA_DIR", "./data")).expanduser().resolve()
    p.mkdir(parents=True, exist_ok=True, mode=0o700)
    return p


@contextmanager
def connect():
    db = sqlite3.connect(data_dir() / "research.db", timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=30000")
    try:
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def migrate():
    with connect() as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript(Path(__file__).with_name("schema.sql").read_text())
    for name in ("originals", "markdown", "uploads", "backups"):
        (data_dir() / name).mkdir(exist_ok=True, mode=0o700)


def get_setting(key, default=None):
    with connect() as db:
        row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else default


def set_setting(key, value):
    with connect() as db:
        db.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (key, json.dumps(value)))


def audit(actor, action, resource_id=None, details=None):
    with connect() as db:
        db.execute(
            "INSERT INTO activity(at,actor,action,resource_id,details) VALUES(?,?,?,?,?)",
            (now(), actor, action, resource_id, json.dumps(details or {})),
        )


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    value = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return salt + ":" + value


def initialize(password=None):
    migrate()
    if get_setting("password_hash"):
        return None
    password = password or secrets.token_urlsafe(18)
    set_setting("password_hash", password_hash(password))
    set_setting("timezone", os.getenv("RD_TIMEZONE", "Asia/Kuala_Lumpur"))
    set_setting("digest_time", os.getenv("RD_DIGEST_TIME", "08:30"))
    set_setting("profile", "")
    set_setting("layout", DEFAULT_LAYOUT)
    token = secrets.token_urlsafe(48)
    token_file = data_dir() / "agent-token"
    token_file.write_text(token)
    token_file.chmod(0o600)
    set_setting("agent_token_hash", hashlib.sha256(token.encode()).hexdigest())
    audit("System", "Initialized local workspace")
    return password


def row_dict(row):
    if row is None:
        return None
    item = dict(row)
    for key in ("tags", "tickers", "topics", "document_ids", "errors", "details", "payload"):
        if key in item:
            item[key] = json.loads(item[key])
    return item
