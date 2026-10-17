# Handover validation

Validated on 17 October 2026 on an Apple Silicon Mac.

| Check | Result |
| --- | --- |
| Python 3.12 backend tests | 24 passed |
| Ruff lint | Passed |
| Browser workflows in installed Google Chrome | 5 passed |
| Actual mouse drag and resize, save, reload and reset | Passed |
| Stock add, edit, manual price and removal | Passed |
| File import, search, safe rendering, Markdown download | Passed |
| Selective ChatGPT conversation import and AI labels | Passed |
| Linked task, calendar export and narrow viewport | Passed |
| Dot CLI search and audit attribution | Passed |
| Stdio MCP discovery and authenticated reads | 19 tools; search and dashboard passed |
| Fresh native install from handover source, without existing dependencies/data | Passed; empty database integrity OK |
| Docker image build, bundled UI, non-root UID 10001 and HTTP health | Passed |
| Docker Compose configuration | Passed |
| Complete backup and restore to a separate directory | Passed; original content and credentials retained |
| Refuse restore over a running app or corrupt database | Passed |
| NPM production dependency audit | No known vulnerabilities reported |
| Pinned Python dependency audit | No known vulnerabilities reported |

The five browser tests cover multiple sequential user actions and saved state. Backend tests also cover authentication, CSRF, invalid input, multiple currencies, quote parsing/failure preservation, RSS provenance/deduplication, ChatGPT branch retention, retries, import undo, immutable revisions, ZIP traversal, private-network URL rejection and safe external metadata.

The screenshot in docs/design/dashboard.png shows the running application with labelled sample data. It is separate from the original approved mockup.

## Checks still specific to the recipient

- His actual ChatGPT/dot account, computer connection and local tool registration.
- His market-data account/key and a successful live authenticated quote. Provider responses are tested with fixtures; no private account was available. The key-free Stooq endpoint returned a browser-verification challenge during live validation.
- His real ChatGPT export, private source accounts and email connectors. Test a representative import batch first.
- macOS login auto-start after the owner chooses to enable it.
- Owner-managed off-device backup storage.

GitHub Actions repeats lint, backend tests, bundled browser workflows and a Docker build on pushes. Dependency audits describe the databases available at validation time and do not guarantee that future vulnerabilities will never be found.
