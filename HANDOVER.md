# Research Desk handover

## Architecture

- FastAPI serves the static app and validated authenticated APIs.
- SQLite in WAL mode stores records, sessions, settings, jobs and audit history. FTS5 indexes text and tags.
- Originals and revisioned Markdown are immutable local files referenced by database records.
- A single durable background worker handles imports, public article retrieval, RSS and prices; restart requeues running jobs. Stable IDs and hashes deduplicate import retries.
- The browser uses GridStack for dashboard movement/resizing; layouts are saved in the database.
- The actual ChatGPT dot operates via local CLI or stdio MCP. There is no model API, custom chatbot or fabricated personal-dot memory.
- Native data defaults to ./data. Docker uses /data in the named research-data volume.
- One app process owns a file lock for its data directory. Restore refuses to overwrite a running app.

## Source layout

- research_desk/app.py: authentication, browser/API routes, validation and security headers.
- research_desk/schema.sql and db.py: initial idempotent schema, persistent settings and audit.
- research_desk/library.py: library search, provenance, revisions and Markdown.
- research_desk/ingestion.py: archive/file extraction and ChatGPT conversation import.
- research_desk/jobs.py: durable queue, sources, prices, digest generation and schedules.
- research_desk/network.py: public-address validation and IP-pinned TLS fetches.
- research_desk/agent.py and mcp_server.py: local dot tools.
- research_desk/cli.py: install initialisation, status, password/token rotation, backup and restore.
- web/: UI source, locally bundled into research_desk/static by npm run build.
- tests/: backend and browser workflow checks.
- scripts/: native and Docker install/start, dot wrappers, optional macOS auto-start.

## Intentional limits and setup still needed on the owner's Mac

- Actual personal dot integration must be verified with that account and connected computer; local CLI and MCP protocol tests do not prove its account is configured.
- Finnhub needs the owner's key/account and coverage. Key-free Stooq was blocked by a browser-verification page during live validation. No successful live authenticated quote is claimed without a supplied account.
- US USD automated quotes; other markets use manual prices. No FX conversion, brokerage or trade execution.
- No automatic email OAuth/IMAP collector: the actual dot's authorised email connector or EML upload supplies emails.
- Source connections are configurable; there are no 40 preconfigured private source accounts.
- ChatGPT export support is tested with representative ZIP/JSON fixtures; the owner's actual archive still needs a pilot import. Private dot memory is not exported.
- Scanned PDF OCR and audio/video transcription are not included; upload text PDFs or transcripts.
- Search uses local full-text indexes and metadata; semantic embedding search is not included.
- Calendar supports in-app tasks and ICS export, not two-way Google/Apple Calendar account sync.
- Local daily digests are extractive, not AI-generated analysis. The actual dot can publish synthesis and can be assigned a separate ChatGPT schedule.
- Backups on the same Mac need an owner-chosen off-device copy workflow for hardware-loss recovery.
- Default service is localhost only. Remote access needs a properly authenticated private HTTPS deployment; the project does not open a public app port or create a public OAuth connector.

## Rebuild

Read README.md and INSTALL_WITH_CHATGPT.md. Install from the pinned Python/Node lockfiles, initialise only an empty workspace, start and check /health. Restore an existing backup before adding live research. Verify user login, dot access, imports, prices and backups.

Keep account-specific secrets and real research out of source. Add a new schema migration and test restored old databases before changing a future released schema.
