from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from ai_doctor.api import create_app
from ai_doctor.capabilities.prescribing import ProtocolRepository
from ai_doctor.settings import Settings

PHYSICIAN_HEADERS = {"Authorization": "Bearer physician-test-token"}
PATIENT_HEADERS = {"Authorization": "Bearer patient-test-token"}
SAFETY_HEADERS = {"Authorization": "Bearer safety-test-token"}


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="preclinical",
        database_path=tmp_path / "api.db",
        emergency_service_label="local emergency services",
        tokens={
            "physician-test-token": {
                "user_id": "doctor-1",
                "role": "physician",
            },
            "patient-test-token": {
                "user_id": "patient-user-1",
                "role": "patient",
            },
            "safety-test-token": {
                "user_id": "safety-officer-1",
                "role": "clinical_safety_officer",
            },
        },
    )


def _protocol_repository() -> ProtocolRepository:
    protocol = {
        "id": "fixture-protocol",
        "version": "1.0.0-test",
        "approval": {
            "state": "approved",
            "signer_id": "test-clinical-owner",
            "signature": "LOCAL_TEST_FIXTURE_ONLY",
        },
        "required_inputs": [
            "age_years",
            "allergy_status_confirmed",
            "pregnancy_status",
            "confirmed_by_clinician",
            "medication_list_confirmed",
            "condition:fixture indication",
        ],
        "contraindications": ["fixture-contraindication"],
        "medication": {
            "name": "Fixture medicine",
            "dose": "fixture dose",
            "route": "fixture route",
            "frequency": "fixture frequency",
            "duration": "fixture duration",
            "indication": "fixture indication",
            "monitoring": ["Fixture monitoring instruction"],
            "warnings": ["Fixture warning"],
        },
    }
    return ProtocolRepository(records={protocol["id"]: protocol}, allow_test_fixtures=True)


def _routine_case_payload():
    return {
        "snapshot": {
            "patient_ref": "patient-001",
            "encounter_ref": "encounter-001",
            "age_years": 45,
            "sex_at_birth": "male",
            "pregnancy_status": "not_applicable",
            "allergy_status_confirmed": True,
            "medication_list_confirmed": True,
            "confirmed_by_clinician": True,
            "conditions": [
                {
                    "name": "fixture indication",
                    "verification_status": "clinician_verified",
                }
            ],
            "symptoms": [{"name": "headache", "severity_0_to_10": 3}],
            "vitals": {
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "heart_rate_bpm": 72,
                "respiratory_rate_bpm": 14,
                "systolic_bp_mmhg": 120,
                "diastolic_bp_mmhg": 75,
                "oxygen_saturation_percent": 98,
                "temperature_c": 36.8,
            },
        },
        "requested_capabilities": [
            "emergency_triage",
            "diagnosis_support",
            "patient_advice",
        ],
    }


def test_full_clinician_supervised_flow(tmp_path: Path):
    app = create_app(_settings(tmp_path), _protocol_repository())
    client = TestClient(app)

    capabilities = client.get("/v1/capabilities", headers=PHYSICIAN_HEADERS)
    assert capabilities.status_code == 200
    assert len(capabilities.json()["provenance"]["emergency_triage"]["sha256"]) == 64

    created = client.post("/v1/cases", headers=PHYSICIAN_HEADERS, json=_routine_case_payload())
    assert created.status_code == 201, created.text
    case_id = created.json()["case_id"]
    decision = created.json()["decision"]
    created_decision_id = decision["decision_id"]
    assert decision["triage"]["urgency"] == "routine"
    assert decision["diagnosis"]["authoritative"] is False
    assert decision["review_status"] == "pending"

    unauthorized = client.get(f"/v1/cases/{case_id}", headers=PATIENT_HEADERS)
    assert unauthorized.status_code == 404

    drafted = client.post(
        f"/v1/cases/{case_id}/prescription-drafts",
        headers=PHYSICIAN_HEADERS,
        json={"protocol_id": "fixture-protocol"},
    )
    assert drafted.status_code == 200, drafted.text
    assert drafted.json()["prescription_draft"]["status"] == "pending_clinician_review"
    assert drafted.json()["prescription_draft"]["executable"] is False
    drafted_decision_id = drafted.json()["decision_id"]
    assert drafted_decision_id != created_decision_id

    reviewed = client.post(
        f"/v1/cases/{case_id}/review",
        headers=PHYSICIAN_HEADERS,
        json={
            "disposition": "approve_draft",
            "rationale": "Synthetic preclinical test approval only",
        },
    )
    assert reviewed.status_code == 200, reviewed.text
    body = reviewed.json()
    assert body["decision_id"] != drafted_decision_id
    assert body["prescription_draft"]["status"] == "clinician_approved_draft"
    assert body["prescription_draft"]["executable"] is False
    assert body["patient_advice"]["status"] == "clinician_approved_prescription_advice"

    grant = client.post(
        f"/v1/cases/{case_id}/access",
        headers=PHYSICIAN_HEADERS,
        json={"principal_id": "patient-user-1", "access_level": "read"},
    )
    assert grant.status_code == 204

    advice = client.get(f"/v1/cases/{case_id}/advice", headers=PATIENT_HEADERS)
    assert advice.status_code == 200
    assert "Fixture medicine" in advice.json()["actions"][0]

    audit = client.get(f"/v1/cases/{case_id}/audit/verify", headers=PHYSICIAN_HEADERS)
    assert audit.status_code == 200
    assert audit.json()["valid"] is True
    assert audit.json()["event_count"] >= 4


def test_clinician_authored_general_advice_is_structured_reviewed_and_retrievable(
    tmp_path: Path,
):
    app = create_app(_settings(tmp_path), _protocol_repository())
    client = TestClient(app)
    created = client.post("/v1/cases", headers=PHYSICIAN_HEADERS, json=_routine_case_payload())
    case_id = created.json()["case_id"]

    reviewed = client.post(
        f"/v1/cases/{case_id}/review",
        headers=PHYSICIAN_HEADERS,
        json={
            "disposition": "acknowledge",
            "rationale": "Synthetic clinician review of the structured care plan",
            "advice_plan": {
                "summary": "Use the reviewed care plan below.",
                "actions": ["Keep a symptom diary."],
                "avoid": ["Do not exceed the clinician-reviewed activity limit."],
                "warning_signs": ["Seek reassessment if symptoms become severe."],
                "follow_up": ["Arrange the documented follow-up visit."],
            },
        },
    )
    assert reviewed.status_code == 200, reviewed.text
    advice_body = reviewed.json()["patient_advice"]
    assert advice_body["status"] == "clinician_authored_advice"
    assert advice_body["clinician_approval_required"] is False
    assert advice_body["actions"] == ["Keep a symptom diary."]

    grant = client.post(
        f"/v1/cases/{case_id}/access",
        headers=PHYSICIAN_HEADERS,
        json={"principal_id": "patient-user-1", "access_level": "read"},
    )
    assert grant.status_code == 204
    advice = client.get(f"/v1/cases/{case_id}/advice", headers=PATIENT_HEADERS)
    assert advice.status_code == 200
    assert advice.json()["advice_id"] == advice_body["advice_id"]
    assert advice.json()["summary"] == "Use the reviewed care plan below."


def test_emergency_red_flag_preempts_diagnosis_and_returns_immediate_instruction(
    tmp_path: Path,
):
    app = create_app(_settings(tmp_path), _protocol_repository())
    client = TestClient(app)
    payload = _routine_case_payload()
    payload["snapshot"]["symptoms"] = [{"name": "chest pressure"}]

    response = client.post("/v1/cases", headers=PHYSICIAN_HEADERS, json=payload)
    assert response.status_code == 201, response.text
    decision = response.json()["decision"]
    assert decision["triage"]["urgency"] == "emergency_now"
    assert decision["safety"]["status"] == "escalate"
    assert decision["diagnosis"] is None
    assert decision["patient_advice"]["status"] == "emergency_preapproved"
    assert decision["patient_advice"]["emergency_instruction"]


def test_patient_can_run_triage_without_age_but_cannot_get_diagnosis(tmp_path: Path):
    app = create_app(_settings(tmp_path), _protocol_repository())
    client = TestClient(app)
    payload = {
        "snapshot": {
            "patient_ref": "patient-self",
            "symptoms": [{"name": "cough"}],
        },
        "requested_capabilities": ["emergency_triage", "diagnosis_support"],
    }
    response = client.post("/v1/cases", headers=PATIENT_HEADERS, json=payload)
    assert response.status_code == 201
    decision = response.json()["decision"]
    assert decision["triage"]["urgency"] == "insufficient_data"
    assert decision["diagnosis"] is None
    assert decision["capability_safety"]["diagnosis_support"]["status"] == "block"


def test_safety_officer_cannot_write_without_explicit_case_acl(tmp_path: Path):
    app = create_app(_settings(tmp_path), _protocol_repository())
    client = TestClient(app)
    created = client.post("/v1/cases", headers=PHYSICIAN_HEADERS, json=_routine_case_payload())
    case_id = created.json()["case_id"]

    response = client.post(
        f"/v1/cases/{case_id}/review",
        headers=SAFETY_HEADERS,
        json={"disposition": "acknowledge", "rationale": "Attempted unauthorized review"},
    )

    assert response.status_code == 404


def test_amendment_creates_successor_snapshot_and_reassessment(tmp_path: Path):
    app = create_app(_settings(tmp_path), _protocol_repository())
    client = TestClient(app)
    created = client.post("/v1/cases", headers=PHYSICIAN_HEADERS, json=_routine_case_payload())
    case_id = created.json()["case_id"]
    predecessor = created.json()["decision"]["snapshot_id"]

    amended = client.post(
        f"/v1/cases/{case_id}/review",
        headers=PHYSICIAN_HEADERS,
        json={
            "disposition": "amend",
            "rationale": "New symptom information entered in synthetic test",
            "amendments": {"symptoms": [{"name": "chest pain"}]},
        },
    )
    assert amended.status_code == 200, amended.text
    assert amended.json()["snapshot_id"] != predecessor
    assert amended.json()["triage"]["urgency"] == "emergency_now"
    assert amended.json()["review_status"] == "pending"

    versions = client.get(f"/v1/cases/{case_id}/versions", headers=PHYSICIAN_HEADERS)
    assert versions.status_code == 200
    assert len(versions.json()) == 2
