import json
from pathlib import Path

import pytest

from ai_doctor.api import create_app
from ai_doctor.auth import Principal
from ai_doctor.capabilities.diagnosis import generate_diagnosis_support
from ai_doctor.capabilities.triage import assess_triage
from ai_doctor.domain.models import (
    CapabilityName,
    CaseCreate,
    PatientSnapshot,
    Symptom,
    UserRole,
    VitalSigns,
)
from ai_doctor.models.gateway import DiagnosisModelGateway
from ai_doctor.orchestrator import ClinicalOrchestrator
from ai_doctor.settings import Settings
from ai_doctor.storage.sqlite import SqliteRepository


def _snapshot():
    return PatientSnapshot(
        patient_ref="patient-direct-identifier",
        encounter_ref="encounter-direct-identifier",
        age_years=42,
        symptoms=[Symptom(name="headache")],
        vitals=VitalSigns(
            heart_rate_bpm=70,
            respiratory_rate_bpm=14,
            systolic_bp_mmhg=120,
            oxygen_saturation_percent=98,
            temperature_c=37,
        ),
    )


def _baseline(snapshot):
    return generate_diagnosis_support(snapshot, assess_triage(snapshot))


def test_request_excludes_direct_patient_and_encounter_identifiers():
    snapshot = _snapshot()
    request = DiagnosisModelGateway._request(snapshot, assess_triage(snapshot), _baseline(snapshot))
    serialized = json.dumps(request)
    assert snapshot.patient_ref not in serialized
    assert snapshot.encounter_ref not in serialized
    assert "patient_ref" not in serialized
    assert "encounter_ref" not in serialized


def test_request_excludes_arbitrary_symptom_attribute_payloads():
    snapshot = _snapshot().model_copy(
        update={"symptoms": [Symptom(name="headache", attributes={"note": "private-token"})]}
    )
    serialized = json.dumps(
        DiagnosisModelGateway._request(snapshot, assess_triage(snapshot), _baseline(snapshot))
    )
    assert "private-token" not in serialized


def test_valid_strict_model_augmentation_retains_baseline_and_non_authority():
    snapshot = _snapshot()
    baseline = _baseline(snapshot)
    gateway = DiagnosisModelGateway(
        transport=lambda _: {
            "problem_representation": "Headache reported",
            "hypotheses": [{"name": "Medication-related headache", "likelihood": "low"}],
            "dangerous_alternatives": [],
            "next_information": ["Review medication timing."],
            "limitations": ["Synthetic model candidate."],
        },
        model_release="test-gateway-1",
    )
    augmented = gateway.augment(snapshot, assess_triage(snapshot), baseline)
    assert [item.name for item in baseline.hypotheses] == [
        item.name for item in augmented.hypotheses[: len(baseline.hypotheses)]
    ]
    assert "Medication-related headache" in [item.name for item in augmented.hypotheses]
    assert augmented.authoritative is False
    assert augmented.model_release == "test-gateway-1"


def test_malformed_or_erroring_transport_fails_closed_to_baseline():
    snapshot = _snapshot()
    baseline = _baseline(snapshot)
    malformed = DiagnosisModelGateway(
        transport=lambda _: {"unexpected": "field"}, model_release="test"
    ).augment(snapshot, assess_triage(snapshot), baseline)
    failed = DiagnosisModelGateway(
        transport=lambda _: (_ for _ in ()).throw(RuntimeError("unavailable")),
        model_release="test",
    ).augment(snapshot, assess_triage(snapshot), baseline)
    assert malformed.hypotheses == baseline.hypotheses
    assert failed.hypotheses == baseline.hypotheses
    assert malformed.authoritative is False
    assert "deterministic output was retained" in malformed.limitations[-1]


def test_gateway_is_off_by_default_and_only_augments_diagnosis(tmp_path: Path):
    settings = Settings(
        environment="preclinical",
        database_path=tmp_path / "default-off.db",
        emergency_service_label="local emergency services",
        tokens={},
    )
    app = create_app(settings)
    assert app.state.orchestrator.diagnosis_model_gateway is None

    gateway = DiagnosisModelGateway(
        transport=lambda _: {
            "problem_representation": "Headache reported",
            "hypotheses": [],
            "dangerous_alternatives": [],
            "next_information": [],
            "limitations": [],
        },
        model_release="test",
    )
    orchestrator = ClinicalOrchestrator(
        repository=SqliteRepository(tmp_path / "gateway.db"),
        diagnosis_model_gateway=gateway,
    )
    result = orchestrator.create_case(
        CaseCreate(snapshot=_snapshot(), requested_capabilities=[CapabilityName.DIAGNOSIS_SUPPORT]),
        Principal(user_id="doctor", role=UserRole.PHYSICIAN),
    ).decision
    assert result.diagnosis is not None
    assert result.triage.rule_release == "triage-rules-0.1.0-preclinical"
    assert result.prescription_draft is None
    assert result.patient_advice is None


def test_enabled_gateway_requires_https_except_preclinical_localhost(tmp_path: Path):
    common = {
        "database_path": tmp_path / "settings.db",
        "emergency_service_label": "local emergency services",
        "tokens": {},
        "model_gateway_enabled": True,
        "model_gateway_model": "test-model",
    }
    with pytest.raises(RuntimeError, match="HTTPS"):
        Settings(
            environment="production",
            model_gateway_endpoint="http://models.example.test/v1",
            **common,
        )
    settings = Settings(
        environment="preclinical",
        model_gateway_endpoint="http://localhost:8000/v1",
        **common,
    )
    assert settings.model_gateway_endpoint == "http://localhost:8000/v1"

    with pytest.raises(RuntimeError, match="ALLOWED_HOSTS"):
        Settings(
            environment="production",
            model_gateway_endpoint="https://models.example.test/v1",
            **common,
        )


def test_gateway_allowlist_and_timeout_are_validated(tmp_path: Path):
    common = {
        "environment": "preclinical",
        "database_path": tmp_path / "settings.db",
        "emergency_service_label": "local emergency services",
        "tokens": {},
        "model_gateway_enabled": True,
        "model_gateway_model": "test-model",
    }
    with pytest.raises(RuntimeError, match="allowlist"):
        Settings(
            model_gateway_endpoint="https://models.example.test/v1",
            model_gateway_allowed_hosts=("approved.example.test",),
            **common,
        )
    with pytest.raises(RuntimeError, match="between 1 and 60"):
        Settings(
            model_gateway_endpoint="https://models.example.test/v1",
            model_gateway_timeout_seconds=0,
            **common,
        )
