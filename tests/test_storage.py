import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest

from ai_doctor.domain.models import (
    ClinicalDecision,
    PatientSnapshot,
    SafetyDecision,
    SafetyStatus,
    Symptom,
    TriageAssessment,
    UrgencyLevel,
)
from ai_doctor.storage.sqlite import (
    CaseNotFoundError,
    ConcurrentModificationError,
    SqliteRepository,
)


def build_case():
    case_id = uuid4()
    snapshot = PatientSnapshot(
        patient_ref="patient-test",
        age_years=42,
        symptoms=[Symptom(name="cough")],
    )
    triage = TriageAssessment(
        urgency=UrgencyLevel.ROUTINE,
        coverage_statement="Synthetic test coverage only.",
        rule_release="test-rules-1",
    )
    decision = ClinicalDecision(
        case_id=case_id,
        snapshot_id=snapshot.snapshot_id,
        triage=triage,
        safety=SafetyDecision(status=SafetyStatus.ALLOW_REVIEW),
    )
    return case_id, snapshot, decision


def test_case_round_trip_and_audit_chain(tmp_path: Path):
    repository = SqliteRepository(tmp_path / "test.db")
    case_id, snapshot, decision = build_case()
    repository.create_case(
        case_id=case_id,
        snapshot=snapshot,
        decision=decision,
        actor_id="tester",
        actor_role="physician",
    )

    stored_snapshot, stored_decision = repository.get_case(case_id)
    assert stored_snapshot.snapshot_id == snapshot.snapshot_id
    assert stored_decision.decision_id == decision.decision_id
    assert repository.has_access(case_id, "tester", "physician", write=True)
    assert not repository.has_access(case_id, "someone-else", "patient")

    repository.grant_access(
        case_id=case_id,
        principal_id="patient-1",
        access_level="read",
        granted_by="tester",
        granted_by_role="physician",
    )
    assert repository.has_access(case_id, "patient-1", "patient")
    assert not repository.has_access(case_id, "patient-1", "patient", write=True)

    repository.append_event(
        case_id=case_id,
        event_type="test.checked",
        actor_id="tester",
        actor_role="physician",
        payload={"result": "ok"},
    )
    verification = repository.verify_event_chain(case_id)
    assert verification["valid"] is True
    assert verification["event_count"] == 3
    assert repository.audit_delivery_status(case_id)["pending"] == 0

    with (
        sqlite3.connect(str(repository.database_path)) as connection,
        pytest.raises(sqlite3.IntegrityError, match="append-only"),
    ):
        connection.execute(
            "UPDATE case_versions SET created_at = created_at WHERE case_id = ?",
            (str(case_id),),
        )


def test_missing_case_raises(tmp_path: Path):
    repository = SqliteRepository(tmp_path / "test.db")
    with pytest.raises(CaseNotFoundError):
        repository.get_case(uuid4())


def test_stale_decision_write_is_rejected(tmp_path: Path):
    repository = SqliteRepository(tmp_path / "test.db")
    case_id, snapshot, decision = build_case()
    repository.create_case(
        case_id=case_id,
        snapshot=snapshot,
        decision=decision,
        actor_id="tester",
        actor_role="physician",
    )
    successor_snapshot = snapshot.model_copy(update={"snapshot_id": uuid4()})
    successor_decision = decision.model_copy(
        update={"decision_id": uuid4(), "snapshot_id": successor_snapshot.snapshot_id}
    )
    repository.replace_case_state(
        case_id=case_id,
        snapshot=successor_snapshot,
        decision=successor_decision,
        event_type="test.reassessed",
        actor_id="tester",
        actor_role="physician",
        event_payload={},
        expected_snapshot_id=snapshot.snapshot_id,
        expected_decision_id=decision.decision_id,
    )

    with pytest.raises(ConcurrentModificationError):
        repository.update_decision(
            case_id=case_id,
            decision=decision,
            event_type="test.stale_write",
            actor_id="tester",
            actor_role="physician",
            event_payload={},
            expected_snapshot_id=snapshot.snapshot_id,
            expected_decision_id=decision.decision_id,
        )


def test_safety_officer_role_is_read_only_without_case_acl(tmp_path: Path):
    repository = SqliteRepository(tmp_path / "test.db")
    case_id, snapshot, decision = build_case()
    repository.create_case(
        case_id=case_id,
        snapshot=snapshot,
        decision=decision,
        actor_id="tester",
        actor_role="physician",
    )

    assert repository.has_access(case_id, "safety-1", "clinical_safety_officer")
    assert not repository.has_access(case_id, "safety-1", "clinical_safety_officer", write=True)
