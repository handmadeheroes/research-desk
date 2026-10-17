CREATE TABLE IF NOT EXISTS schema_version(version INTEGER PRIMARY KEY);
INSERT OR IGNORE INTO schema_version VALUES(1);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS documents(
 id TEXT PRIMARY KEY, title TEXT NOT NULL, kind TEXT NOT NULL, source_name TEXT NOT NULL DEFAULT '',
 url TEXT NOT NULL DEFAULT '', published_at TEXT, created_at TEXT NOT NULL, retrieved_at TEXT NOT NULL,
 updated_at TEXT NOT NULL, tags TEXT NOT NULL DEFAULT '[]', tickers TEXT NOT NULL DEFAULT '[]',
 summary TEXT NOT NULL DEFAULT '', content TEXT NOT NULL, raw_path TEXT NOT NULL, md_path TEXT NOT NULL,
 sha256 TEXT NOT NULL, external_id TEXT UNIQUE, ai_generated INTEGER NOT NULL DEFAULT 0,
 archived INTEGER NOT NULL DEFAULT 0, demo INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS documents_date ON documents(created_at);
CREATE INDEX IF NOT EXISTS documents_hash ON documents(sha256);
CREATE TABLE IF NOT EXISTS document_versions(
 id INTEGER PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id),
 snapshot TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
 title, content, summary, tags, tickers, content='documents', content_rowid='rowid', tokenize='unicode61'
);
CREATE TRIGGER IF NOT EXISTS docs_ai AFTER INSERT ON documents BEGIN
 INSERT INTO documents_fts(rowid,title,content,summary,tags,tickers)
 VALUES(new.rowid,new.title,new.content,new.summary,new.tags,new.tickers);
END;
CREATE TRIGGER IF NOT EXISTS docs_ad AFTER DELETE ON documents BEGIN
 INSERT INTO documents_fts(documents_fts,rowid,title,content,summary,tags,tickers)
 VALUES('delete',old.rowid,old.title,old.content,old.summary,old.tags,old.tickers);
END;
CREATE TRIGGER IF NOT EXISTS docs_au AFTER UPDATE ON documents BEGIN
 INSERT INTO documents_fts(documents_fts,rowid,title,content,summary,tags,tickers)
 VALUES('delete',old.rowid,old.title,old.content,old.summary,old.tags,old.tickers);
 INSERT INTO documents_fts(rowid,title,content,summary,tags,tickers)
 VALUES(new.rowid,new.title,new.content,new.summary,new.tags,new.tickers);
END;
CREATE TABLE IF NOT EXISTS sources(
 id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL, url TEXT NOT NULL DEFAULT '',
 topics TEXT NOT NULL DEFAULT '[]', enabled INTEGER NOT NULL DEFAULT 1,
 last_fetched TEXT, last_error TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS stocks(
 id TEXT PRIMARY KEY, symbol TEXT NOT NULL, quote_symbol TEXT NOT NULL, exchange TEXT NOT NULL DEFAULT '',
 currency TEXT NOT NULL DEFAULT 'USD', category TEXT NOT NULL, shares REAL NOT NULL DEFAULT 0,
 average_cost REAL, notes TEXT NOT NULL DEFAULT '', last_price REAL, previous_price REAL,
 price_at TEXT, provider TEXT, quote_error TEXT, demo INTEGER NOT NULL DEFAULT 0,
 UNIQUE(symbol,exchange,category)
);
CREATE TABLE IF NOT EXISTS portfolio_history(
 day TEXT NOT NULL, currency TEXT NOT NULL, value REAL NOT NULL, PRIMARY KEY(day,currency)
);
CREATE TABLE IF NOT EXISTS tasks(
 id TEXT PRIMARY KEY, title TEXT NOT NULL, due_at TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0,
 notes TEXT NOT NULL DEFAULT '', document_id TEXT REFERENCES documents(id), created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS digests(
 id TEXT PRIMARY KEY, day TEXT NOT NULL, title TEXT NOT NULL, content TEXT NOT NULL,
 document_ids TEXT NOT NULL, method TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS digests_day ON digests(day);
CREATE TABLE IF NOT EXISTS jobs(
 id TEXT PRIMARY KEY, kind TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL,
 total INTEGER NOT NULL DEFAULT 0, processed INTEGER NOT NULL DEFAULT 0,
 imported INTEGER NOT NULL DEFAULT 0, duplicates INTEGER NOT NULL DEFAULT 0,
 errors TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS uploads(
 id TEXT PRIMARY KEY, filename TEXT NOT NULL, path TEXT NOT NULL, size INTEGER NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS job_items(
 job_id TEXT NOT NULL REFERENCES jobs(id), document_id TEXT NOT NULL REFERENCES documents(id),
 action TEXT NOT NULL, PRIMARY KEY(job_id,document_id)
);
CREATE TABLE IF NOT EXISTS activity(
 id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, actor TEXT NOT NULL,
 action TEXT NOT NULL, resource_id TEXT, details TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS activity_date ON activity(at);
CREATE TABLE IF NOT EXISTS sessions(
 token_hash TEXT PRIMARY KEY, csrf TEXT NOT NULL, expires_at REAL NOT NULL
);
