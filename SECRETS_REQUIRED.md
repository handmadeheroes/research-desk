# Credentials and account connections

| Item | Purpose | Where it lives | Verify / rotate |
|---|---|---|---|
| Workspace password | Owner dashboard login | Salted scrypt hash in local database; generated password shown once during init | Sign in locally; research-desk reset-password |
| Agent token | Local dot CLI/MCP app authentication | data/agent-token, mode 0600; hash in database | Call dashboard; research-desk rotate-agent-token |
| Finnhub API key (optional) | US stock quotes using owner's account | Local Settings writes data/quote-key, mode 0600; or FINNHUB_API_KEY in local .env | Refresh quotes and inspect returned source/date and job status; rotate at Finnhub |
| Research source logins | Email, paywalled sites and other connected sources | Owner's authorised ChatGPT plugins/browser sessions | Verify each source in the owner's ChatGPT account |
| Dot account and connected Mac | Let the actual personal dot operate the app | Owner's ChatGPT account/device grant | Test an actual app write/read and inspect Dot audit entries |
| Off-device backup destination (optional) | Protect against Mac loss | Owner-managed storage connection | Copy a backup, verify its checksum and perform a restore trial |

No GitHub account is required to download public source. No OpenAI API key is required by the app.

Never commit .env, data folders, database files, local tokens, credentials, research exports or backups. Backups include app credentials and personal research; store and share them as private data.
