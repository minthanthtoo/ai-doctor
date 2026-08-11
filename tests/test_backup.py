import sqlite3

from ai_doctor.backup import create_consistent_backup, prune_backups


def test_backup_is_consistent_and_readable(tmp_path):
    source = tmp_path / "source.db"
    backups = tmp_path / "backups"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE events (value TEXT NOT NULL)")
        connection.execute("INSERT INTO events VALUES ('ciphertext-only')")

    destination = create_consistent_backup(source, backups)

    with sqlite3.connect(destination) as connection:
        assert connection.execute("SELECT value FROM events").fetchone() == (
            "ciphertext-only",
        )


def test_backup_pruning_ignores_unrelated_files(tmp_path):
    unrelated = tmp_path / "operator-note.txt"
    unrelated.write_text("keep", encoding="utf-8")

    prune_backups(tmp_path, retention_days=1)

    assert unrelated.exists()
