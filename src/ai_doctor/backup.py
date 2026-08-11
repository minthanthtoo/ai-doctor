from __future__ import annotations

import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from ai_doctor.settings import Settings


def create_consistent_backup(source: Path, destination_directory: Path) -> Path:
    """Create a transactionally consistent SQLite backup without copying a live DB file."""

    destination_directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = destination_directory / f"relay-{stamp}.db"
    with sqlite3.connect(source) as source_connection, sqlite3.connect(
        destination
    ) as destination_connection:
        source_connection.backup(destination_connection)
    return destination


def prune_backups(directory: Path, retention_days: int) -> None:
    cutoff = time.time() - retention_days * 86_400
    for candidate in directory.glob("relay-*.db"):
        if candidate.is_file() and candidate.stat().st_mtime < cutoff:
            candidate.unlink()


def run() -> None:
    settings = Settings.from_env()
    backup_directory = Path(os.environ.get("AI_DOCTOR_BACKUP_DIRECTORY", "/backups"))
    interval_seconds = max(300, int(os.environ.get("AI_DOCTOR_BACKUP_INTERVAL_SECONDS", "86400")))
    retention_days = max(1, int(os.environ.get("AI_DOCTOR_BACKUP_RETENTION_DAYS", "30")))
    while True:
        create_consistent_backup(settings.database_path, backup_directory)
        prune_backups(backup_directory, retention_days)
        time.sleep(interval_seconds)


if __name__ == "__main__":
    run()
