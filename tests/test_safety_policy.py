import json
from pathlib import Path

import pytest

from ai_doctor.domain.models import (
    CapabilityName,
    PatientSnapshot,
    PregnancyStatus,
    SafetyStatus,
    Symptom,
    UrgencyLevel,
    UserRole,
)
from ai_doctor.safety.policy import SafetyGate
from ai_doctor.safety.registry import CapabilityRegistry


def snapshot(**overrides):
    values = {
        "patient_ref": "patient-1",
        "age_years": 42,
        "pregnancy_status": PregnancyStatus.NOT_APPLICABLE,
        "symptoms": [Symptom(name="headache")],
    }
    values.update(overrides)
    return PatientSnapshot(**values)


def test_registry_exposes_release_versions():
    registry = CapabilityRegistry.default()

    assert (
        registry.require(CapabilityName.DIAGNOSIS_SUPPORT).release_version
        == "diagnosis-patterns-0.1.0-preclinical"
    )
    assert registry.release_versions([CapabilityName.EMERGENCY_TRIAGE]) == {
        "emergency_triage": "triage-rules-0.1.0-preclinical"
    }
    provenance = registry.knowledge_provenance(CapabilityName.EMERGENCY_TRIAGE)
    assert provenance["release_version"] == "triage-rules-0.1.0-preclinical"
    assert len(provenance["sha256"]) == 64


def test_registry_rejects_policy_release_that_differs_from_executed_rules(tmp_path: Path):
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "ai_doctor"
        / "config"
        / "capability_registry.json"
    )
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["capabilities"][0]["release_version"] = "wrong-release"
    candidate = tmp_path / "registry.json"
    candidate.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="does not match executed knowledge"):
        CapabilityRegistry.from_file(candidate)


def test_diagnosis_requires_authorized_role_and_review():
    decision = SafetyGate().evaluate(
        CapabilityName.DIAGNOSIS_SUPPORT,
        snapshot(),
        UserRole.PHYSICIAN,
        "diagnostic_assessment",
        "display_for_review",
    )

    assert decision.status == SafetyStatus.ALLOW_REVIEW
    assert any("Clinician review" in action for action in decision.required_actions)


def test_patient_cannot_request_clinical_diagnosis():
    decision = SafetyGate().evaluate(
        CapabilityName.DIAGNOSIS_SUPPORT, snapshot(), UserRole.PATIENT, "diagnostic_assessment"
    )

    assert decision.status == SafetyStatus.BLOCK
    assert "role" in " ".join(decision.hard_blocks).lower()


def test_prescribing_fails_closed_for_unknown_pregnancy_and_execution():
    decision = SafetyGate().evaluate(
        CapabilityName.PRESCRIPTION_DRAFT,
        snapshot(pregnancy_status=PregnancyStatus.UNKNOWN),
        UserRole.PHYSICIAN,
        "prescription_draft",
        "order_placement",
    )

    assert decision.status == SafetyStatus.BLOCK
    assert len(decision.hard_blocks) == 2
    assert "pregnancy" in " ".join(decision.hard_blocks).lower()
    assert "prohibited" in " ".join(decision.hard_blocks).lower()


def test_emergency_priority_escalates_and_suspends_non_triage():
    gate = SafetyGate()
    emergency = gate.evaluate(
        CapabilityName.EMERGENCY_TRIAGE,
        snapshot(age_years=12),
        UserRole.PATIENT,
        "emergency_instruction",
        "display_triage",
        UrgencyLevel.EMERGENCY_NOW,
    )
    diagnosis = gate.evaluate(
        CapabilityName.DIAGNOSIS_SUPPORT,
        snapshot(),
        UserRole.PHYSICIAN,
        "diagnostic_assessment",
        emergency_priority=UrgencyLevel.EMERGENCY_NOW,
    )

    assert emergency.status == SafetyStatus.ESCALATE
    assert diagnosis.status == SafetyStatus.ESCALATE
    assert diagnosis.hard_blocks


def test_emergency_triage_never_blocks_only_because_age_is_missing():
    decision = SafetyGate().evaluate(
        CapabilityName.EMERGENCY_TRIAGE,
        snapshot(age_years=None),
        UserRole.PATIENT,
        "triage_assessment",
        "display_triage",
    )

    assert decision.status == SafetyStatus.ALLOW_REVIEW


def test_unknown_output_or_action_is_blocked():
    decision = SafetyGate().evaluate(
        CapabilityName.PATIENT_ADVICE,
        snapshot(),
        UserRole.PATIENT,
        "anything_else",
        "send_sms",
    )

    assert decision.status == SafetyStatus.BLOCK
    assert len(decision.hard_blocks) == 2
