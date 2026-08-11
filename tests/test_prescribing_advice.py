import base64
import json
import subprocess
import sys
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ai_doctor.capabilities.advice import (
    render_approved_prescription_advice,
    render_patient_advice,
)
from ai_doctor.capabilities.prescribing import (
    Ed25519ProtocolVerifier,
    ProtocolRepository,
    approve_prescription_draft,
    build_prescription_draft,
    canonical_protocol_bytes,
)
from ai_doctor.domain.models import (
    ClinicalDecision,
    Condition,
    PatientSnapshot,
    ReviewDisposition,
    SafetyDecision,
    SafetyStatus,
    Severity,
    TriageAssessment,
    TriageFinding,
    UrgencyLevel,
    UserRole,
)


def _protocol(**changes):
    value = {
        "id": "local-fixture",
        "version": "1",
        "approval": {
            "state": "approved",
            "signer_id": "clinical-owner",
            "signature": "LOCAL_TEST_FIXTURE_ONLY",
        },
        "required_inputs": [
            "age_years",
            "allergy_status_confirmed",
            "pregnancy_status",
            "confirmed_by_clinician",
            "medication_list_confirmed",
            "condition:fixture condition",
        ],
        "contraindications": ["fixture-contraindication"],
        "medication": {
            "name": "Fixture medicine",
            "dose": "fixture dose",
            "route": "fixture route",
            "frequency": "fixture frequency",
            "indication": "fixture indication",
        },
    }
    value.update(changes)
    return value


def _snapshot(**changes):
    value = {
        "patient_ref": "patient-1",
        "age_years": 42,
        "pregnancy_status": "not_applicable",
        "allergy_status_confirmed": True,
        "medication_list_confirmed": True,
        "conditions": [
            Condition(name="fixture condition", verification_status="clinician_verified")
        ],
        "confirmed_by_clinician": True,
    }
    value.update(changes)
    return PatientSnapshot(**value)


def _repo(protocol=None):
    protocol = protocol or _protocol()
    return ProtocolRepository(records={protocol["id"]: protocol}, allow_test_fixtures=True)


def test_draft_is_protocol_bounded_non_executable_and_needs_clinician_approval():
    draft = build_prescription_draft(_snapshot(), "local-fixture", _repo())

    assert draft.status == "pending_clinician_review"
    assert draft.executable is False
    assert draft.clinician_approval_required is True
    assert draft.items[0].protocol_id == "local-fixture"

    approved = approve_prescription_draft(draft, "clinician-1", UserRole.PHYSICIAN)
    assert approved.status == "clinician_approved_draft"
    assert approved.executable is False
    assert approved.approved_by == "clinician-1"


@pytest.mark.parametrize(
    "snapshot, expected",
    [
        (_snapshot(allergy_status_confirmed=False), "allergy_status_confirmed"),
        (_snapshot(medication_list_confirmed=False), "medication_list_confirmed"),
        (_snapshot(pregnancy_status="unknown"), "pregnancy_status"),
        (
            _snapshot(
                conditions=[
                    Condition(name="fixture condition", verification_status="patient_reported")
                ]
            ),
            "condition:fixture condition",
        ),
        (
            _snapshot(conditions=[Condition(name="fixture-contraindication")]),
            "protocol contraindication present",
        ),
    ],
)
def test_draft_blocks_missing_or_contraindicated_inputs(snapshot, expected):
    draft = build_prescription_draft(snapshot, "local-fixture", _repo())
    assert draft.status == "blocked"
    assert not draft.items
    assert expected in " ".join([*draft.hard_blocks, *draft.missing_inputs])


def test_unknown_or_unsigned_protocol_is_blocked():
    draft = build_prescription_draft(_snapshot(), "not-here", _repo())
    assert draft.status == "blocked"


def test_protocol_without_clinician_verified_indication_is_rejected():
    protocol = _protocol(required_inputs=["age_years"])
    draft = build_prescription_draft(_snapshot(), "local-fixture", _repo(protocol))

    assert draft.status == "blocked"
    assert "indication condition" in " ".join(draft.hard_blocks)


def test_ed25519_signed_protocol_is_verified_and_tampering_is_blocked():
    private_key = Ed25519PrivateKey.generate()
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    protocol = _protocol()
    protocol["approval"]["key_id"] = "clinical-release-key"
    protocol["approval"]["signature"] = ""
    protocol["approval"]["signature"] = base64.b64encode(
        private_key.sign(canonical_protocol_bytes(protocol))
    ).decode("ascii")
    verifier = Ed25519ProtocolVerifier(
        {"clinical-release-key": base64.b64encode(public_bytes).decode("ascii")}
    )
    repository = ProtocolRepository(records={protocol["id"]: protocol}, signature_verifier=verifier)

    draft = build_prescription_draft(_snapshot(), protocol["id"], repository)
    assert draft.status == "pending_clinician_review"

    tampered = _protocol()
    tampered.update(protocol)
    tampered["medication"] = dict(protocol["medication"], dose="tampered dose")
    tampered_repository = ProtocolRepository(
        records={tampered["id"]: tampered}, signature_verifier=verifier
    )
    blocked = build_prescription_draft(_snapshot(), tampered["id"], tampered_repository)
    assert blocked.status == "blocked"
    assert "signature" in " ".join(blocked.hard_blocks)
    assert draft.executable is False

    unsigned = _protocol(approval={"state": "approved", "signer_id": "owner"})
    draft = build_prescription_draft(_snapshot(), "local-fixture", _repo(unsigned))
    assert draft.status == "blocked"


def test_sign_protocol_cli_outputs_verifiable_signed_record(tmp_path):
    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    unsigned_path = tmp_path / "unsigned.json"
    private_path = tmp_path / "release-key.pem"
    output_path = tmp_path / "signed.json"
    unsigned_path.write_text(
        json.dumps(_protocol(approval={"state": "approved"})), encoding="utf-8"
    )
    private_path.write_bytes(private_pem)

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/sign_protocol.py",
            "--input",
            str(unsigned_path),
            "--output",
            str(output_path),
            "--private-key",
            str(private_path),
            "--key-id",
            "rotation-key-1",
            "--signer-id",
            "clinical-owner",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    signed = json.loads(output_path.read_text(encoding="utf-8"))
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    verifier = Ed25519ProtocolVerifier(
        {"rotation-key-1": base64.b64encode(public_bytes).decode("ascii")}
    )
    assert signed["approval"]["key_id"] == "rotation-key-1"
    assert verifier(signed) is True
    assert private_pem.decode("ascii") not in completed.stdout + completed.stderr


def _decision(urgency=UrgencyLevel.URGENT_SAME_DAY, reviewed=False):
    triage = TriageAssessment(
        urgency=urgency,
        findings=[
            TriageFinding(
                rule_id="triage-rule",
                urgency=urgency,
                severity=Severity.HIGH,
                title="Approved warning sign",
                rationale="approved rationale",
                recommended_response="Approved next action",
            )
        ],
        emergency_instruction="Approved emergency instruction"
        if urgency == UrgencyLevel.EMERGENCY_NOW
        else None,
        coverage_statement="Approved coverage statement",
        rule_release="r1",
    )
    return ClinicalDecision(
        case_id=uuid4(),
        snapshot_id=uuid4(),
        triage=triage,
        safety=SafetyDecision(status=SafetyStatus.ALLOW_REVIEW),
        reviewed_by="clinician" if reviewed else None,
        reviewed_at=datetime.now(timezone.utc) if reviewed else None,
        review_disposition=ReviewDisposition.ACKNOWLEDGE if reviewed else None,
    )


def test_patient_advice_needs_clinician_review_except_emergency():
    blocked = render_patient_advice(_decision())
    assert blocked.status == "blocked_pending_clinician_review"

    reviewed = render_patient_advice(_decision(reviewed=True))
    assert reviewed.status == "clinician_reviewed"
    assert reviewed.actions == ["Approved next action"]
    assert reviewed.clinician_approval_required is False

    emergency = render_patient_advice(_decision(UrgencyLevel.EMERGENCY_NOW))
    assert emergency.status == "emergency_preapproved"
    assert emergency.emergency_instruction == "Approved emergency instruction"


def test_prescription_advice_copies_only_an_approved_structured_draft():
    decision = _decision(reviewed=True)
    blocked = render_approved_prescription_advice(decision)
    assert blocked.status == "blocked_pending_prescriber_approval"

    draft = build_prescription_draft(_snapshot(), "local-fixture", _repo())
    approved = approve_prescription_draft(draft, "clinician-1", UserRole.PHYSICIAN)
    decision = decision.model_copy(update={"prescription_draft": approved})
    advice = render_approved_prescription_advice(decision)

    assert advice.status == "clinician_approved_prescription_advice"
    assert "Fixture medicine" in advice.actions[0]
    assert advice.clinician_approval_required is False
