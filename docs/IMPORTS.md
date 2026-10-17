# One-off migration of existing ChatGPT research

1. Obtain a data export using the controls available in the owner's ChatGPT account, or download selected conversations and source files. Export availability/content depends on account and workspace.
2. Keep the untouched export on the owner's Mac. Do not upload personal exports to GitHub.
3. In Uploads & Imports, drop the ZIP or JSON. Review conversation titles. Filter the list; selections persist while filtering.
4. Select research conversations and exclude unrelated private chats. Choose explicitly whether to index additional supported archive files. Archive files are not automatically matched to selected conversations.
5. The unchanged whole original upload is retained locally even when only selected conversations are indexed. If that retention is inappropriate, prepare a scoped export locally before uploading.
6. Run a small pilot. Confirm original chat titles, dates, message roles, alternate branches, citations and Markdown downloads.
7. Run the full selection. Monitor saved counts, duplicate counts and issues. A partial import can be retried; restarting the app requeues an interrupted running job.
8. The first 100 matching conversations are displayed at a time; search filters across the complete preview and all selections are retained. Select all covers the entire preview, not just visible rows.
9. Unsupported attachments remain in the preserved original archive and appear as issues when file indexing is requested. Referenced remote URLs do not imply saved article bodies. Scanned PDFs need an OCR pass outside this release.
10. Undo archives newly created, unchanged records from that batch. Existing records that received revisions, later edits and original uploads are retained. Original conversation data and old Markdown versions remain recoverable.

The parser recognises a conversations.json list, a top-level conversations list, or a single conversation object with a mapping tree. It preserves available mapping branches with message/parent IDs. ChatGPT-generated statements are AI research, not independently verified original articles.

Automatic initial topic tags use transparent keyword rules plus recognised companies/tickers. The dot or owner can review and edit tags, summaries and titles. No bulk model API requests are made.

Upload limit: 512 MB compressed. ZIP limit: 20,000 entries and 768 MB total uncompressed. Encrypted archives, traversal paths and symlinks are rejected. Split larger exports into scoped batches.
