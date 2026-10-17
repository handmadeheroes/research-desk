# Deterministic local background work

All work below is ordinary code; it does not call an AI model.

| Job | Trigger | Stored status |
|---|---|---|
| RSS/Atom retrieval | Enabled RSS sources, every 60 minutes by default | Jobs, connection last_fetched/last_error, activity |
| Quote refresh | Daily after 08:00 workspace time or manual action | Jobs, per-stock source/date/error, activity |
| Excerpt digest | Daily after configured digest time; default 08:30 | Saved digest with method=local excerpts |
| Complete local backup | Daily after 03:00 workspace time | Local backup ZIP and manifest, activity |
| Import / article retrieval | Owner/dot request | Durable queued/running/complete/partial/failed states |

The worker checks schedules once per minute while the app is running. An offline/sleeping Mac cannot run local jobs. On the next start, each daily job catches up once; it does not recreate every missed day.

Settings: workspace timezone and digest time in the UI; RD_FEED_INTERVAL_MINUTES and RD_BACKUP_RETENTION in .env (restart after environment changes). Set a connection's Enabled checkbox off to pause periodic retrieval.

Inspect Imports & Background Activity and the Activity Log. Retrying partial imports is safe because stable source IDs and content hashes deduplicate records.

The local worker is intentionally single-process and uses a durable SQLite queue. Do not launch multiple app workers against the same data directory. Public web fetches are restricted to public HTTP/HTTPS addresses and standard ports, with IP pinning and redirect validation.

To stop all local schedules, stop the app. To remove native auto-start:

    launchctl bootout "gui/$(id -u)/local.research-desk"
    rm "$HOME/Library/LaunchAgents/local.research-desk.plist"

For Docker, stop the app with docker compose stop app. Do not remove its volume.

An AI-synthesised recurring digest is a separate responsibility assigned to the owner's actual dot in ChatGPT. Confirm that schedule in ChatGPT; the app's local excerpt schedule does not create it.
