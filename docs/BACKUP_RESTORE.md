# Backup and restore

## Native installation

Create a complete backup:

    .venv/bin/research-desk backup
    .venv/bin/research-desk backup --output /private/external/location/research-desk.zip

The snapshot includes a SQLite online backup, originals, all retained Markdown revisions, uploaded archives, agent credential and saved quote credential. It excludes dependency directories and older backups. A manifest verifies every file checksum.

Backups contain private research and credentials. They are stored with mode 0600, but ZIP encryption is not provided. Use encrypted owner-managed storage when copying off-device. Local .env configuration is separate: preserve it privately if it contains your deployment or provider configuration.

Restore into a fresh directory:

    RD_DATA_DIR=/absolute/path/to/restored-data .venv/bin/research-desk restore /absolute/path/to/backup.zip
    RD_DATA_DIR=/absolute/path/to/restored-data .venv/bin/research-desk status

Stop the existing server or launchd service before replacing its data:

    launchctl bootout "gui/$(id -u)/local.research-desk"
    .venv/bin/research-desk restore /absolute/path/to/backup.zip --replace --confirm
    ./scripts/start.sh

For a separately restored trial directory, choose another port if the original app is running:

    RD_DATA_DIR=/absolute/path/to/restored-data .venv/bin/research-desk serve --port 8411

Verify login, source counts, a Markdown download, original file contents, holdings and an agent read/write. Do not change the live app to use a trial restore until verification passes.

## Docker installation

    docker compose exec -T app research-desk backup

The command prints /data/backups/NAME.zip. Copy it out:

    docker compose cp app:/data/backups/NAME.zip ./NAME.zip

Restore only while the app is stopped:

    docker compose stop app
    docker compose run --rm --no-deps app research-desk restore /data/backups/NAME.zip --replace --confirm
    docker compose up -d

For an external backup, first copy it into the stopped container's data volume using an owner-controlled bind mount or temporary compose run. Do not remove the named volume.

Native and Docker stores are separate. To switch modes, make a complete backup in the source mode and restore it into the destination mode before using it.

## Schedule and retention

The worker makes one local full backup per workspace day after 03:00, with catch-up after a restart, and retains seven automatically named backups by default. Configure RD_BACKUP_RETENTION locally. Manual custom-named/off-device copies are not automatically removed.

This protects against many software mistakes. It does not protect against loss of the same Mac or Docker disk. Configure an off-device copy and test its restore.
