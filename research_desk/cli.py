import argparse
import getpass
import hashlib
import json
import os
import secrets
import sqlite3
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from .db import audit, connect, data_dir, initialize, migrate, now, password_hash, set_setting


def backup(destination=None):
    root = data_dir()
    destination = Path(destination) if destination else root / "backups" / ("research-desk-" + now()[:19].replace(":", "") + ".zip")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        snapshot = Path(temporary) / "research.db"
        with connect() as source, sqlite3.connect(snapshot) as target:
            source.backup(target)
        files = [(snapshot, "research.db")]
        for folder in ("originals", "markdown", "uploads"):
            files.extend((file, str(file.relative_to(root))) for file in (root / folder).rglob("*") if file.is_file())
        if (root / "agent-token").exists():
            files.append((root / "agent-token", "agent-token"))
        if (root / "quote-key").exists():
            files.append((root / "quote-key", "quote-key"))
        manifest = {name: hashlib.sha256(file.read_bytes()).hexdigest() for file, name in files}
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for file, name in files:
                archive.write(file, name)
            archive.writestr("manifest.json", json.dumps({"version": 1, "created_at": now(), "sha256": manifest}, indent=2))
    destination.chmod(0o600)
    audit("System", "Created complete backup", details={"files": len(files)})
    return destination


def restore(archive_path, replace=False):
    import fcntl
    root = data_dir()
    with (root / ".app.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("Stop Research Desk before restoring its data.") from exc
        if (root / "research.db").exists() and not replace:
            raise ValueError("The target has a database. Restore into a new data directory or use --replace --confirm.")
        with zipfile.ZipFile(archive_path) as archive:
            entries = archive.infolist()
            if len(entries) > 100000 or sum(x.file_size for x in entries) > 50 * 1024**3:
                raise ValueError("Backup exceeds the restore safety limit")
            manifest = json.loads(archive.read("manifest.json"))
            expected = manifest["sha256"]
            if "research.db" not in expected:
                raise ValueError("Backup has no database")
            for name, digest in expected.items():
                path = PurePosixPath(name)
                if not path.parts or path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name:
                    raise ValueError("Unsafe path in backup")
                if name not in ("research.db", "agent-token", "quote-key") and path.parts[0] not in ("originals", "markdown", "uploads"):
                    raise ValueError("Unexpected file in backup")
                if not (root / name).resolve().is_relative_to(root):
                    raise ValueError("Backup target resolves outside the data directory")
                if hashlib.sha256(archive.read(name)).hexdigest() != digest:
                    raise ValueError("Backup integrity check failed: " + name)
            # Check the snapshot before touching an existing workspace.
            with tempfile.TemporaryDirectory() as temporary:
                snapshot = Path(temporary) / "research.db"
                snapshot.write_bytes(archive.read("research.db"))
                try:
                    with sqlite3.connect(snapshot) as check:
                        if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                            raise ValueError("Backup database failed its integrity check")
                        check.execute("SELECT id FROM documents LIMIT 1")
                        check.execute("SELECT version FROM schema_version")
                except sqlite3.DatabaseError as exc:
                    raise ValueError("Backup does not contain a valid Research Desk database") from exc
            # Validate all bytes and destination paths before writing target files.
            for name in expected:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                target.write_bytes(archive.read(name))
                target.chmod(0o600)
        for suffix in ("-wal", "-shm"):
            (root / ("research.db" + suffix)).unlink(missing_ok=True)
    migrate()
    with connect() as db:
        result = db.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise ValueError("Restored database failed its integrity check")
    audit("System", "Restored backup")
    return root


def main():
    parser = argparse.ArgumentParser(description="Research Desk local operations")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Create local credentials and database")
    init.add_argument("--demo", action="store_true")
    serve = commands.add_parser("serve", help="Start the local dashboard")
    serve.add_argument("--host", default=os.getenv("RD_HOST", "127.0.0.1"))
    serve.add_argument("--port", type=int, default=int(os.getenv("RD_PORT", "8401")))
    commands.add_parser("reset-password", help="Set a new workspace password on this Mac")
    commands.add_parser("rotate-agent-token", help="Revoke and replace the local dot credential")
    commands.add_parser("status", help="Check database integrity and counts")
    back = commands.add_parser("backup", help="Back up database, originals, Markdown, uploads and credentials")
    back.add_argument("--output")
    recover = commands.add_parser("restore", help="Restore an intact backup into this data directory")
    recover.add_argument("archive")
    recover.add_argument("--replace", action="store_true")
    recover.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    if args.command == "init":
        password = initialize()
        if password:
            print("Workspace created. Keep this password private:\n\n  " + password + "\n")
        else:
            print("Workspace already initialized. Existing data and credentials retained.")
        if args.demo:
            from .seed import seed_demo
            seed_demo()
        print("Start with: research-desk serve")
    elif args.command == "serve":
        import uvicorn
        uvicorn.run("research_desk.app:app", host=args.host, port=args.port, workers=1)
    elif args.command == "reset-password":
        password = getpass.getpass("New workspace password (12+ characters): ")
        if len(password) < 12 or password != getpass.getpass("Confirm password: "):
            parser.error("Passwords must match and contain at least 12 characters.")
        set_setting("password_hash", password_hash(password))
        with connect() as db:
            db.execute("DELETE FROM sessions")
        audit("Owner", "Reset workspace password; sessions revoked")
        print("Password changed. Sign in again.")
    elif args.command == "rotate-agent-token":
        token = secrets.token_urlsafe(48)
        (data_dir() / "agent-token").write_text(token)
        (data_dir() / "agent-token").chmod(0o600)
        set_setting("agent_token_hash", hashlib.sha256(token.encode()).hexdigest())
        audit("Owner", "Rotated dot access credential")
        print("Dot credential rotated. Existing callers must use the local updated credential.")
    elif args.command == "status":
        with connect() as db:
            print(json.dumps({"integrity": db.execute("PRAGMA integrity_check").fetchone()[0],
                              "documents": db.execute("SELECT count(*) FROM documents WHERE archived=0").fetchone()[0],
                              "data_directory": str(data_dir())}, indent=2))
    elif args.command == "backup":
        print(backup(args.output))
    elif args.command == "restore":
        if args.replace and not args.confirm:
            parser.error("Replacing existing data requires --replace --confirm. Stop the app first.")
        print(restore(args.archive, args.replace))


if __name__ == "__main__":
    main()
