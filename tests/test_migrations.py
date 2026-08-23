"""Migration framework drills: fresh apply, idempotence, legacy stamp, downgrade refusal."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ai_doctor.storage.migrations import (
    CDS_MIGRATIONS,
    RELAY_MIGRATIONS,
    apply_migrations,
)


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    return connection


def test_fresh_cds_database_reaches_latest(tmp_path: Path):
    connection = _connect(tmp_path / "cds.db")
    applied = apply_migrations(connection, CDS_MIGRATIONS, store_label="cds-test")
    assert applied == 1
    tables = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert {"cases", "case_versions", "case_acl", "audit_events", "audit_outbox", "audit_sink", "schema_migrations"} <= tables
    triggers = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'"
        )
    }
    assert {"audit_events_no_update", "case_versions_no_delete"} <= triggers
    version = connection.execute("SELECT MAX(version) AS v FROM schema_migrations").fetchone()["v"]
    assert version == 1


def test_fresh_relay_database_reaches_latest(tmp_path: Path):
    connection = _connect(tmp_path / "relay.db")
    applied = apply_migrations(connection, RELAY_MIGRATIONS, store_label="relay-test")
    assert applied == 1
    tables = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert {"relay_envelopes", "relay_profile_owners", "relay_devices", "relay_tombstones", "push_subscriptions", "push_schedules", "schema_migrations"} <= tables


def test_reapply_is_idempotent(tmp_path: Path):
    path = tmp_path / "store.db"
    first = _connect(path)
    assert apply_migrations(first, RELAY_MIGRATIONS, store_label="relay-test") == 1
    first.close()
    second = _connect(path)
    assert apply_migrations(second, RELAY_MIGRATIONS, store_label="relay-test") == 0
    rows = second.execute("SELECT COUNT(*) AS n FROM schema_migrations").fetchone()
    assert rows["n"] == 1


def test_legacy_database_without_migration_table_stamps_forward_intact(tmp_path: Path):
    """A real pre-framework database has the full v1 DDL but no version row."""
    from ai_doctor.storage.migrations import _relay_store_v1

    path = tmp_path / "legacy.db"
    legacy = _connect(path)
    _relay_store_v1(legacy)  # exact historical schema, no schema_migrations row
    legacy.execute(
        """
        INSERT INTO relay_envelopes (
            opaque_object_id, profile_pseudonym, device_id, client_sequence,
            ciphertext, nonce, aad_hash, ciphertext_hash, signature,
            envelope_version, created_at, expires_at, server_received_at
        ) VALUES ('legacy-row', 'p', 'd', 1, 'c', 'n', 'a', 'h', 's', 'v1', 't0', 't1', 't2')
        """
    )
    legacy.commit()
    legacy.close()

    connection = _connect(path)
    applied = apply_migrations(connection, RELAY_MIGRATIONS, store_label="relay-test")
    assert applied == 1
    # Pre-existing data survives; IF NOT EXISTS statements were no-ops.
    count = connection.execute("SELECT COUNT(*) AS n FROM relay_envelopes").fetchone()
    assert count["n"] == 1
    version = connection.execute(
        "SELECT MAX(version) AS v FROM schema_migrations"
    ).fetchone()["v"]
    assert version == 1


def test_two_stores_share_one_database_file_independently(tmp_path: Path):
    """CDS and relay stores live in one file; each tracks its own versions."""
    path = tmp_path / "shared.db"
    connection = _connect(path)
    assert apply_migrations(connection, CDS_MIGRATIONS, store_label="cds-store") == 1
    assert apply_migrations(connection, RELAY_MIGRATIONS, store_label="relay-store") == 1
    rows = connection.execute(
        "SELECT store, COUNT(*) AS n FROM schema_migrations GROUP BY store"
    ).fetchall()
    tracked = {row["store"]: row["n"] for row in rows}
    assert tracked == {"cds-store": 1, "relay-store": 1}
    # Re-opening both is fully idempotent.
    assert apply_migrations(connection, CDS_MIGRATIONS, store_label="cds-store") == 0
    assert apply_migrations(connection, RELAY_MIGRATIONS, store_label="relay-store") == 0


def test_future_version_refuses_to_open(tmp_path: Path):
    path = tmp_path / "future.db"
    connection = _connect(path)
    connection.execute(
        """
        CREATE TABLE schema_migrations (
            store TEXT NOT NULL,
            version INTEGER NOT NULL,
            label TEXT NOT NULL,
            applied_at TEXT NOT NULL,
            PRIMARY KEY (store, version)
        )
        """
    )
    connection.execute(
        "INSERT INTO schema_migrations (store, version, label, applied_at) VALUES ('relay-test', 99, 'from the future', '2027-01-01')"
    )
    connection.commit()
    with pytest.raises(RuntimeError, match="newer than this build"):
        apply_migrations(connection, RELAY_MIGRATIONS, store_label="relay-test")


def test_failed_migration_leaves_no_partial_state(tmp_path: Path):
    """A migration that raises mid-flight must not record its version."""
    def broken(_connection: sqlite3.Connection) -> None:
        raise sqlite3.OperationalError("simulated failure")

    migrations = ((1, "broken step", broken),)
    connection = _connect(tmp_path / "fail.db")
    with pytest.raises(RuntimeError, match="migration 1"):
        apply_migrations(connection, migrations, store_label="fail-store")
    recorded = connection.execute("SELECT COUNT(*) AS n FROM schema_migrations").fetchone()
    assert recorded["n"] == 0
