"""Versioned schema migrations for ai-doctor SQLite stores.

Every store applies an ordered list of migrations recorded in a
``schema_migrations`` table (one transaction per migration). Existing
databases created before this framework stamp forward to version 1
without modification because every v1 statement uses ``IF NOT EXISTS``
and matches the historical DDL byte-for-byte. A database whose recorded
version exceeds the newest known migration refuses to open (no silent
downgrades).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Callable, Sequence

MigrationFn = Callable[[sqlite3.Connection], None]


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cds_store_v1(connection: sqlite3.Connection) -> None:
    """Initial clinician-supervised store: cases, ACL, hash-chained audit."""
    statements = (
        """
        CREATE TABLE IF NOT EXISTS cases (
            case_id TEXT PRIMARY KEY,
            snapshot_json TEXT NOT NULL,
            decision_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS case_versions (
            case_id TEXT NOT NULL,
            version_number INTEGER NOT NULL,
            snapshot_json TEXT NOT NULL,
            decision_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(case_id, version_number),
            FOREIGN KEY(case_id) REFERENCES cases(case_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS case_acl (
            case_id TEXT NOT NULL,
            principal_id TEXT NOT NULL,
            access_level TEXT NOT NULL CHECK(access_level IN ('read', 'read_write')),
            granted_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(case_id, principal_id),
            FOREIGN KEY(case_id) REFERENCES cases(case_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS audit_events (
            event_id TEXT PRIMARY KEY,
            case_id TEXT NOT NULL,
            sequence_number INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            actor_id TEXT NOT NULL,
            actor_role TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            payload_hash TEXT NOT NULL,
            previous_event_hash TEXT NOT NULL,
            event_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(case_id, sequence_number),
            FOREIGN KEY(case_id) REFERENCES cases(case_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS audit_outbox (
            event_id TEXT PRIMARY KEY,
            case_id TEXT NOT NULL,
            event_json TEXT NOT NULL,
            delivered_at TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(event_id) REFERENCES audit_events(event_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS audit_sink (
            event_id TEXT PRIMARY KEY,
            case_id TEXT NOT NULL,
            event_json TEXT NOT NULL,
            received_at TEXT NOT NULL
        )
        """,
        """
        CREATE TRIGGER IF NOT EXISTS audit_events_no_update
        BEFORE UPDATE ON audit_events
        BEGIN
            SELECT RAISE(ABORT, 'audit events are append-only');
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS audit_events_no_delete
        BEFORE DELETE ON audit_events
        BEGIN
            SELECT RAISE(ABORT, 'audit events are append-only');
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS audit_sink_no_update
        BEFORE UPDATE ON audit_sink
        BEGIN
            SELECT RAISE(ABORT, 'audit sink is append-only');
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS audit_sink_no_delete
        BEFORE DELETE ON audit_sink
        BEGIN
            SELECT RAISE(ABORT, 'audit sink is append-only');
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS case_versions_no_update
        BEFORE UPDATE ON case_versions
        BEGIN
            SELECT RAISE(ABORT, 'case versions are append-only');
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS case_versions_no_delete
        BEFORE DELETE ON case_versions
        BEGIN
            SELECT RAISE(ABORT, 'case versions are append-only');
        END
        """,
    )
    for statement in statements:
        connection.execute(statement)


def _relay_store_v1(connection: sqlite3.Connection) -> None:
    """Initial opaque relay store: envelopes, owners, devices, push."""
    statements = (
        """
        CREATE TABLE IF NOT EXISTS relay_envelopes (
            opaque_object_id TEXT PRIMARY KEY,
            profile_pseudonym TEXT NOT NULL,
            device_id TEXT NOT NULL,
            client_sequence INTEGER NOT NULL,
            ciphertext TEXT NOT NULL,
            nonce TEXT NOT NULL,
            aad_hash TEXT NOT NULL,
            ciphertext_hash TEXT NOT NULL,
            signature TEXT NOT NULL,
            envelope_version TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            server_received_at TEXT NOT NULL
        )
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS relay_device_sequence
        ON relay_envelopes(profile_pseudonym, device_id, client_sequence)
        """,
        """
        CREATE TABLE IF NOT EXISTS relay_profile_owners (
            principal_id TEXT PRIMARY KEY,
            profile_pseudonym TEXT NOT NULL UNIQUE,
            bound_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS relay_devices (
            device_id TEXT PRIMARY KEY,
            profile_pseudonym TEXT NOT NULL,
            signing_public_jwk TEXT NOT NULL,
            enrolled_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS relay_tombstones (
            tombstone_id TEXT PRIMARY KEY,
            profile_pseudonym TEXT NOT NULL,
            opaque_object_id TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS push_subscriptions (
            subscription_id TEXT PRIMARY KEY,
            profile_pseudonym TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            p256dh TEXT NOT NULL,
            auth TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS push_schedules (
            opaque_schedule_id TEXT PRIMARY KEY,
            profile_pseudonym TEXT NOT NULL,
            subscription_id TEXT NOT NULL,
            due_at TEXT NOT NULL,
            repeat_after_seconds INTEGER,
            max_repeats INTEGER NOT NULL,
            repeats_sent INTEGER NOT NULL DEFAULT 0,
            expires_at TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'scheduled',
            generic_message TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(subscription_id) REFERENCES push_subscriptions(subscription_id)
        )
        """,
    )
    for statement in statements:
        connection.execute(statement)


# (version, label, function) — append only; never edit a shipped migration.
CDS_MIGRATIONS: Sequence[tuple[int, str, MigrationFn]] = (
    (1, "clinician-supervised store baseline", _cds_store_v1),
)

RELAY_MIGRATIONS: Sequence[tuple[int, str, MigrationFn]] = (
    (1, "opaque relay store baseline", _relay_store_v1),
)


def apply_migrations(
    connection: sqlite3.Connection,
    migrations: Sequence[tuple[int, str, MigrationFn]],
    *,
    store_label: str,
) -> int:
    """Bring ``connection`` up to the newest known version.

    Returns the number of migrations applied by this call. Raises
    ``RuntimeError`` when the database was written by a newer build.
    """
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            store TEXT NOT NULL,
            version INTEGER NOT NULL,
            label TEXT NOT NULL,
            applied_at TEXT NOT NULL,
            PRIMARY KEY (store, version)
        )
        """
    )
    known = {version for version, _, _ in migrations}
    recorded_rows = connection.execute(
        "SELECT version FROM schema_migrations WHERE store = ?", (store_label,)
    ).fetchall()
    recorded = {int(row[0]) for row in recorded_rows}
    unknown = sorted(recorded - known)
    if unknown:
        raise RuntimeError(
            f"{store_label}: schema version(s) {unknown} are newer than this "
            f"build supports (max {max(known)}); refusing to open or downgrade"
        )
    applied = 0
    for version, label, migrate in sorted(migrations, key=lambda item: item[0]):
        if version in recorded:
            continue
        try:
            with connection:
                migrate(connection)
                connection.execute(
                    "INSERT INTO schema_migrations (store, version, label, applied_at) VALUES (?, ?, ?, ?)",
                    (store_label, version, label, _utc_iso()),
                )
        except sqlite3.Error as error:
            raise RuntimeError(
                f"{store_label}: migration {version} ({label}) failed: {error}"
            ) from error
        applied += 1
    return applied
