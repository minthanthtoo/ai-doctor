from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple
from uuid import UUID, uuid4

from ai_doctor.domain.models import ClinicalDecision, PatientSnapshot


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class CaseNotFoundError(KeyError):
    pass


class ConcurrentModificationError(RuntimeError):
    """The case changed after a workflow read it and before it could commit."""


class SqliteRepository:
    """Preclinical repository with transactional audit outbox and hash chaining."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterable[sqlite3.Connection]:
        connection = sqlite3.connect(str(self.database_path), timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._lock, self._connection() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;

                CREATE TABLE IF NOT EXISTS cases (
                    case_id TEXT PRIMARY KEY,
                    snapshot_json TEXT NOT NULL,
                    decision_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS case_versions (
                    case_id TEXT NOT NULL,
                    version_number INTEGER NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    decision_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(case_id, version_number),
                    FOREIGN KEY(case_id) REFERENCES cases(case_id)
                );

                CREATE TABLE IF NOT EXISTS case_acl (
                    case_id TEXT NOT NULL,
                    principal_id TEXT NOT NULL,
                    access_level TEXT NOT NULL CHECK(access_level IN ('read', 'read_write')),
                    granted_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(case_id, principal_id),
                    FOREIGN KEY(case_id) REFERENCES cases(case_id)
                );

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
                );

                CREATE TABLE IF NOT EXISTS audit_outbox (
                    event_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    event_json TEXT NOT NULL,
                    delivered_at TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(event_id) REFERENCES audit_events(event_id)
                );

                CREATE TABLE IF NOT EXISTS audit_sink (
                    event_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    event_json TEXT NOT NULL,
                    received_at TEXT NOT NULL
                );

                CREATE TRIGGER IF NOT EXISTS audit_events_no_update
                BEFORE UPDATE ON audit_events
                BEGIN
                    SELECT RAISE(ABORT, 'audit events are append-only');
                END;

                CREATE TRIGGER IF NOT EXISTS audit_events_no_delete
                BEFORE DELETE ON audit_events
                BEGIN
                    SELECT RAISE(ABORT, 'audit events are append-only');
                END;

                CREATE TRIGGER IF NOT EXISTS audit_sink_no_update
                BEFORE UPDATE ON audit_sink
                BEGIN
                    SELECT RAISE(ABORT, 'audit sink is append-only');
                END;

                CREATE TRIGGER IF NOT EXISTS audit_sink_no_delete
                BEFORE DELETE ON audit_sink
                BEGIN
                    SELECT RAISE(ABORT, 'audit sink is append-only');
                END;

                CREATE TRIGGER IF NOT EXISTS case_versions_no_update
                BEFORE UPDATE ON case_versions
                BEGIN
                    SELECT RAISE(ABORT, 'case versions are append-only');
                END;

                CREATE TRIGGER IF NOT EXISTS case_versions_no_delete
                BEFORE DELETE ON case_versions
                BEGIN
                    SELECT RAISE(ABORT, 'case versions are append-only');
                END;
                """
            )
            connection.commit()

    def _append_event_tx(
        self,
        connection: sqlite3.Connection,
        *,
        case_id: UUID,
        event_type: str,
        actor_id: str,
        actor_role: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        latest = connection.execute(
            """
            SELECT sequence_number, event_hash
            FROM audit_events
            WHERE case_id = ?
            ORDER BY sequence_number DESC
            LIMIT 1
            """,
            (str(case_id),),
        ).fetchone()
        sequence_number = 1 if latest is None else int(latest["sequence_number"]) + 1
        previous_event_hash = "GENESIS" if latest is None else str(latest["event_hash"])
        payload_json = _canonical_json(payload)
        payload_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        event_id = str(uuid4())
        created_at = _utc_iso()
        hash_material = "|".join(
            [
                str(case_id),
                str(sequence_number),
                event_type,
                actor_id,
                actor_role,
                payload_hash,
                previous_event_hash,
                created_at,
            ]
        )
        event_hash = hashlib.sha256(hash_material.encode("utf-8")).hexdigest()
        event = {
            "event_id": event_id,
            "case_id": str(case_id),
            "sequence_number": sequence_number,
            "event_type": event_type,
            "actor_id": actor_id,
            "actor_role": actor_role,
            "payload": payload,
            "payload_hash": payload_hash,
            "previous_event_hash": previous_event_hash,
            "event_hash": event_hash,
            "created_at": created_at,
        }
        connection.execute(
            """
            INSERT INTO audit_events (
                event_id, case_id, sequence_number, event_type,
                actor_id, actor_role, payload_json, payload_hash,
                previous_event_hash, event_hash, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                str(case_id),
                sequence_number,
                event_type,
                actor_id,
                actor_role,
                payload_json,
                payload_hash,
                previous_event_hash,
                event_hash,
                created_at,
            ),
        )
        connection.execute(
            """
            INSERT INTO audit_outbox (event_id, case_id, event_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (event_id, str(case_id), _canonical_json(event), created_at),
        )
        return event

    def create_case(
        self,
        *,
        case_id: UUID,
        snapshot: PatientSnapshot,
        decision: ClinicalDecision,
        actor_id: str,
        actor_role: str,
    ) -> None:
        now = _utc_iso()
        snapshot_json = snapshot.model_dump_json()
        decision_json = decision.model_dump_json()
        with self._lock, self._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    INSERT INTO cases (
                        case_id, snapshot_json, decision_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (str(case_id), snapshot_json, decision_json, now, now),
                )
                connection.execute(
                    """
                    INSERT INTO case_versions (
                        case_id, version_number, snapshot_json, decision_json, created_at
                    ) VALUES (?, 1, ?, ?, ?)
                    """,
                    (str(case_id), snapshot_json, decision_json, now),
                )
                connection.execute(
                    """
                    INSERT INTO case_acl (
                        case_id, principal_id, access_level, granted_by, created_at
                    ) VALUES (?, ?, 'read_write', ?, ?)
                    """,
                    (str(case_id), actor_id, actor_id, now),
                )
                self._append_event_tx(
                    connection,
                    case_id=case_id,
                    event_type="case.created",
                    actor_id=actor_id,
                    actor_role=actor_role,
                    payload={
                        "snapshot_id": str(snapshot.snapshot_id),
                        "decision_id": str(decision.decision_id),
                        "safety_status": decision.safety.status.value,
                        "capability_releases": decision.capability_releases,
                        "capability_provenance": decision.capability_provenance,
                    },
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        self.flush_audit_outbox()

    def has_access(
        self,
        case_id: UUID,
        principal_id: str,
        principal_role: str,
        *,
        write: bool = False,
    ) -> bool:
        # Clinical-safety officers may inspect any case for safety oversight, but
        # the role alone never grants write authority.  A write requires the same
        # explicit case ACL as every other principal.
        if principal_role == "clinical_safety_officer" and not write:
            with self._connection() as connection:
                return (
                    connection.execute(
                        "SELECT 1 FROM cases WHERE case_id = ?", (str(case_id),)
                    ).fetchone()
                    is not None
                )
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT access_level FROM case_acl
                WHERE case_id = ? AND principal_id = ?
                """,
                (str(case_id), principal_id),
            ).fetchone()
        if row is None:
            return False
        return not write or row["access_level"] == "read_write"

    def grant_access(
        self,
        *,
        case_id: UUID,
        principal_id: str,
        access_level: str,
        granted_by: str,
        granted_by_role: str,
    ) -> None:
        if access_level not in {"read", "read_write"}:
            raise ValueError("access_level must be read or read_write")
        with self._lock, self._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                if (
                    connection.execute(
                        "SELECT 1 FROM cases WHERE case_id = ?", (str(case_id),)
                    ).fetchone()
                    is None
                ):
                    raise CaseNotFoundError(str(case_id))
                connection.execute(
                    """
                    INSERT INTO case_acl (
                        case_id, principal_id, access_level, granted_by, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(case_id, principal_id)
                    DO UPDATE SET access_level = excluded.access_level,
                                  granted_by = excluded.granted_by
                    """,
                    (
                        str(case_id),
                        principal_id,
                        access_level,
                        granted_by,
                        _utc_iso(),
                    ),
                )
                self._append_event_tx(
                    connection,
                    case_id=case_id,
                    event_type="access.granted",
                    actor_id=granted_by,
                    actor_role=granted_by_role,
                    payload={
                        "principal_id": principal_id,
                        "access_level": access_level,
                    },
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        self.flush_audit_outbox()

    def get_case(self, case_id: UUID) -> Tuple[PatientSnapshot, ClinicalDecision]:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT snapshot_json, decision_json FROM cases WHERE case_id = ?",
                (str(case_id),),
            ).fetchone()
        if row is None:
            raise CaseNotFoundError(str(case_id))
        return (
            PatientSnapshot.model_validate_json(row["snapshot_json"]),
            ClinicalDecision.model_validate_json(row["decision_json"]),
        )

    def update_decision(
        self,
        *,
        case_id: UUID,
        decision: ClinicalDecision,
        event_type: str,
        actor_id: str,
        actor_role: str,
        event_payload: Dict[str, Any],
        expected_snapshot_id: UUID,
        expected_decision_id: UUID,
    ) -> None:
        with self._lock, self._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                current = connection.execute(
                    "SELECT snapshot_json, decision_json FROM cases WHERE case_id = ?",
                    (str(case_id),),
                ).fetchone()
                if current is None:
                    raise CaseNotFoundError(str(case_id))
                self._assert_expected_state(
                    current,
                    expected_snapshot_id=expected_snapshot_id,
                    expected_decision_id=expected_decision_id,
                )
                cursor = connection.execute(
                    "UPDATE cases SET decision_json = ?, updated_at = ? WHERE case_id = ?",
                    (decision.model_dump_json(), _utc_iso(), str(case_id)),
                )
                if cursor.rowcount != 1:
                    raise CaseNotFoundError(str(case_id))
                next_version = int(
                    connection.execute(
                        "SELECT COALESCE(MAX(version_number), 0) + 1 FROM case_versions WHERE case_id = ?",
                        (str(case_id),),
                    ).fetchone()[0]
                )
                connection.execute(
                    """
                    INSERT INTO case_versions (
                        case_id, version_number, snapshot_json, decision_json, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        str(case_id),
                        next_version,
                        current["snapshot_json"],
                        decision.model_dump_json(),
                        _utc_iso(),
                    ),
                )
                self._append_event_tx(
                    connection,
                    case_id=case_id,
                    event_type=event_type,
                    actor_id=actor_id,
                    actor_role=actor_role,
                    payload=event_payload,
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        self.flush_audit_outbox()

    def replace_case_state(
        self,
        *,
        case_id: UUID,
        snapshot: PatientSnapshot,
        decision: ClinicalDecision,
        event_type: str,
        actor_id: str,
        actor_role: str,
        event_payload: Dict[str, Any],
        expected_snapshot_id: UUID,
        expected_decision_id: UUID,
    ) -> None:
        """Atomically install a successor snapshot and decision.

        Prior state remains reconstructable through the append-only audit payload;
        callers must include the predecessor and successor identifiers.
        """

        with self._lock, self._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                current = connection.execute(
                    "SELECT snapshot_json, decision_json FROM cases WHERE case_id = ?",
                    (str(case_id),),
                ).fetchone()
                if current is None:
                    raise CaseNotFoundError(str(case_id))
                self._assert_expected_state(
                    current,
                    expected_snapshot_id=expected_snapshot_id,
                    expected_decision_id=expected_decision_id,
                )
                cursor = connection.execute(
                    """
                    UPDATE cases
                    SET snapshot_json = ?, decision_json = ?, updated_at = ?
                    WHERE case_id = ?
                    """,
                    (
                        snapshot.model_dump_json(),
                        decision.model_dump_json(),
                        _utc_iso(),
                        str(case_id),
                    ),
                )
                if cursor.rowcount != 1:
                    raise CaseNotFoundError(str(case_id))
                next_version = int(
                    connection.execute(
                        "SELECT COALESCE(MAX(version_number), 0) + 1 FROM case_versions WHERE case_id = ?",
                        (str(case_id),),
                    ).fetchone()[0]
                )
                connection.execute(
                    """
                    INSERT INTO case_versions (
                        case_id, version_number, snapshot_json, decision_json, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        str(case_id),
                        next_version,
                        snapshot.model_dump_json(),
                        decision.model_dump_json(),
                        _utc_iso(),
                    ),
                )
                self._append_event_tx(
                    connection,
                    case_id=case_id,
                    event_type=event_type,
                    actor_id=actor_id,
                    actor_role=actor_role,
                    payload=event_payload,
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        self.flush_audit_outbox()

    @staticmethod
    def _assert_expected_state(
        row: sqlite3.Row,
        *,
        expected_snapshot_id: UUID,
        expected_decision_id: UUID,
    ) -> None:
        """Reject stale workflow output instead of overwriting newer clinical state."""
        current_snapshot = PatientSnapshot.model_validate_json(row["snapshot_json"])
        current_decision = ClinicalDecision.model_validate_json(row["decision_json"])
        if (
            current_snapshot.snapshot_id != expected_snapshot_id
            or current_decision.decision_id != expected_decision_id
        ):
            raise ConcurrentModificationError(
                "case state changed; reload and reassess before submitting an update"
            )

    def list_case_versions(self, case_id: UUID) -> List[Dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT version_number, snapshot_json, decision_json, created_at
                FROM case_versions
                WHERE case_id = ?
                ORDER BY version_number
                """,
                (str(case_id),),
            ).fetchall()
        if not rows:
            raise CaseNotFoundError(str(case_id))
        return [
            {
                "version_number": int(row["version_number"]),
                "snapshot": json.loads(row["snapshot_json"]),
                "decision": json.loads(row["decision_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def append_event(
        self,
        *,
        case_id: UUID,
        event_type: str,
        actor_id: str,
        actor_role: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        with self._lock, self._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                if (
                    connection.execute(
                        "SELECT 1 FROM cases WHERE case_id = ?", (str(case_id),)
                    ).fetchone()
                    is None
                ):
                    raise CaseNotFoundError(str(case_id))
                event = self._append_event_tx(
                    connection,
                    case_id=case_id,
                    event_type=event_type,
                    actor_id=actor_id,
                    actor_role=actor_role,
                    payload=payload,
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        self.flush_audit_outbox()
        return event

    def list_events(self, case_id: UUID) -> List[Dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM audit_events
                WHERE case_id = ?
                ORDER BY sequence_number
                """,
                (str(case_id),),
            ).fetchall()
        if not rows:
            with self._connection() as connection:
                exists = connection.execute(
                    "SELECT 1 FROM cases WHERE case_id = ?", (str(case_id),)
                ).fetchone()
            if exists is None:
                raise CaseNotFoundError(str(case_id))
        return [
            {
                "event_id": row["event_id"],
                "case_id": row["case_id"],
                "sequence_number": row["sequence_number"],
                "event_type": row["event_type"],
                "actor_id": row["actor_id"],
                "actor_role": row["actor_role"],
                "payload": json.loads(row["payload_json"]),
                "payload_hash": row["payload_hash"],
                "previous_event_hash": row["previous_event_hash"],
                "event_hash": row["event_hash"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def verify_event_chain(self, case_id: UUID) -> Dict[str, Any]:
        events = self.list_events(case_id)
        expected_previous = "GENESIS"
        errors: List[str] = []
        for index, event in enumerate(events, start=1):
            payload_json = _canonical_json(event["payload"])
            payload_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
            if event["sequence_number"] != index:
                errors.append(f"sequence mismatch at event {event['event_id']}")
            if event["previous_event_hash"] != expected_previous:
                errors.append(f"previous hash mismatch at event {event['event_id']}")
            if event["payload_hash"] != payload_hash:
                errors.append(f"payload hash mismatch at event {event['event_id']}")
            hash_material = "|".join(
                [
                    event["case_id"],
                    str(event["sequence_number"]),
                    event["event_type"],
                    event["actor_id"],
                    event["actor_role"],
                    event["payload_hash"],
                    event["previous_event_hash"],
                    event["created_at"],
                ]
            )
            expected_event_hash = hashlib.sha256(hash_material.encode("utf-8")).hexdigest()
            if event["event_hash"] != expected_event_hash:
                errors.append(f"event hash mismatch at event {event['event_id']}")
            expected_previous = event["event_hash"]
        return {
            "case_id": str(case_id),
            "valid": not errors,
            "event_count": len(events),
            "errors": errors,
            "head_hash": expected_previous,
        }

    def flush_audit_outbox(self) -> int:
        delivered = 0
        with self._lock, self._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                rows = connection.execute(
                    """
                    SELECT event_id, case_id, event_json
                    FROM audit_outbox
                    WHERE delivered_at IS NULL
                    ORDER BY created_at
                    """
                ).fetchall()
                for row in rows:
                    received_at = _utc_iso()
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO audit_sink (
                            event_id, case_id, event_json, received_at
                        ) VALUES (?, ?, ?, ?)
                        """,
                        (
                            row["event_id"],
                            row["case_id"],
                            row["event_json"],
                            received_at,
                        ),
                    )
                    connection.execute(
                        "UPDATE audit_outbox SET delivered_at = ? WHERE event_id = ?",
                        (received_at, row["event_id"]),
                    )
                    delivered += 1
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return delivered

    def audit_delivery_status(self, case_id: UUID) -> Dict[str, int]:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN delivered_at IS NULL THEN 1 ELSE 0 END) AS pending
                FROM audit_outbox
                WHERE case_id = ?
                """,
                (str(case_id),),
            ).fetchone()
        return {"total": int(row["total"] or 0), "pending": int(row["pending"] or 0)}
