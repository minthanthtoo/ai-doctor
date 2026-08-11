from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from ai_doctor.api import create_app
from ai_doctor.domain.longitudinal import ClinicalFactRevision
from ai_doctor.settings import Settings

PATIENT_HEADERS = {"Authorization": "Bearer patient-test-token"}
PHYSICIAN_HEADERS = {"Authorization": "Bearer physician-test-token"}


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="preclinical",
        database_path=tmp_path / "relay.db",
        emergency_service_label="local emergency services",
        tokens={
            "patient-test-token": {"user_id": "patient-1", "role": "patient"},
            "physician-test-token": {"user_id": "doctor-1", "role": "physician"},
        },
    )


def _envelope(object_id: str = "opaque_object_123456789", sequence: int = 1):
    return {
        "opaque_object_id": object_id,
        "profile_pseudonym": "profile_pseudonym_123456789",
        "device_id": "device_123456789",
        "client_sequence": sequence,
        "ciphertext": "opaque_ciphertext_123456789",
        "nonce": "opaque_nonce_1234",
        "aad_hash": "a" * 64,
        "ciphertext_hash": "b" * 64,
        "signature": "opaque_signature_123456789",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "ttl_seconds": 3600,
        "envelope_version": "1",
    }


def test_opaque_sync_is_idempotent_and_rejects_replayed_sequence(tmp_path: Path):
    client = TestClient(create_app(_settings(tmp_path)))
    payload = _envelope()
    first = client.put(
        "/v1/sync/envelopes/opaque_object_123456789",
        headers=PATIENT_HEADERS,
        json=payload,
    )
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "accepted"

    duplicate = client.put(
        "/v1/sync/envelopes/opaque_object_123456789",
        headers=PATIENT_HEADERS,
        json=payload,
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["status"] == "unchanged"

    replay = _envelope("different_object_123456789", sequence=1)
    replay["ciphertext_hash"] = "c" * 64
    response = client.put(
        "/v1/sync/envelopes/different_object_123456789",
        headers=PATIENT_HEADERS,
        json=replay,
    )
    assert response.status_code == 409


def test_relay_returns_ciphertext_only_and_is_patient_owned(tmp_path: Path):
    client = TestClient(create_app(_settings(tmp_path)))
    client.put(
        "/v1/sync/envelopes/opaque_object_123456789",
        headers=PATIENT_HEADERS,
        json=_envelope(),
    )
    listing = client.get(
        "/v1/sync/envelopes",
        headers=PATIENT_HEADERS,
        params={"profile_pseudonym": "profile_pseudonym_123456789", "cursor": 0},
    )
    assert listing.status_code == 200
    item = listing.json()["items"][0]
    assert "ciphertext" in item
    assert "symptoms" not in item
    assert "diagnosis" not in item
    assert "medications" not in item

    physician = client.get(
        "/v1/sync/envelopes",
        headers=PHYSICIAN_HEADERS,
        params={"profile_pseudonym": "profile_pseudonym_123456789", "cursor": 0},
    )
    assert physician.status_code == 403


def test_push_schedule_forces_generic_message(tmp_path: Path):
    client = TestClient(create_app(_settings(tmp_path)))
    subscription_id = str(uuid4())
    subscription = client.post(
        "/v1/push/subscriptions",
        headers=PATIENT_HEADERS,
        json={
            "subscription_id": subscription_id,
            "profile_pseudonym": "profile_pseudonym_123456789",
            "endpoint": "https://push.example.test/subscription/opaque",
            "p256dh": "opaque_public_key_123456789",
            "auth": "opaque_auth_12345",
        },
    )
    assert subscription.status_code == 201, subscription.text
    due = datetime.now(timezone.utc) + timedelta(minutes=10)
    scheduled = client.put(
        "/v1/push/schedules/opaque_schedule_123456789",
        headers=PATIENT_HEADERS,
        json={
            "opaque_schedule_id": "opaque_schedule_123456789",
            "profile_pseudonym": "profile_pseudonym_123456789",
            "subscription_id": subscription_id,
            "due_at": due.isoformat(),
            "repeat_after_seconds": 300,
            "max_repeats": 2,
            "expires_at": (due + timedelta(hours=2)).isoformat(),
        },
    )
    assert scheduled.status_code == 200, scheduled.text
    assert scheduled.json()["message"] == "You have a health reminder."


def test_model_broker_fails_closed_when_disabled(tmp_path: Path):
    client = TestClient(create_app(_settings(tmp_path)))
    now = datetime.now(timezone.utc)
    snapshot_hash = "a" * 64
    response = client.post(
        "/v1/model/runs",
        headers=PATIENT_HEADERS,
        json={
            "run_id": str(uuid4()),
            "task": "possibility_generation",
            "consent": {
                "consent_receipt_id": str(uuid4()),
                "purpose": "symptom_reasoning",
                "provider": "test-provider",
                "model": "test-model",
                "disclosed_field_classes": ["coded_symptoms"],
                "snapshot_hash": snapshot_hash,
                "issued_at": now.isoformat(),
                "expires_at": (now + timedelta(minutes=30)).isoformat(),
            },
            "snapshot_hash": snapshot_hash,
            "prompt_release": "test-prompt",
            "schema_release": "test-schema",
            "evidence_release": "test-evidence",
            "facts": [
                {
                    "fact_id": str(uuid4()),
                    "terminology_id": "symptom",
                    "value_text": "headache",
                    "verification": "user_reported",
                }
            ],
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["validation_status"] == "disabled"
    assert response.json()["hypotheses"] == []


def test_release_manifest_and_artifact_integrity(tmp_path: Path):
    client = TestClient(create_app(_settings(tmp_path)))
    manifest = client.get("/v1/releases/preclinical/manifest", headers=PATIENT_HEADERS)
    assert manifest.status_code == 200, manifest.text
    body = manifest.json()
    assert body["approved_for_clinical_use"] is False
    digest = next(iter(body["artifacts"]))
    artifact = client.get(f"/v1/releases/artifacts/{digest}", headers=PATIENT_HEADERS)
    assert artifact.status_code == 200, artifact.text
    assert artifact.json()["pack_id"] == "cardiometabolic-v0-preclinical"


def test_model_cannot_create_verified_fact():
    with pytest.raises(ValidationError):
        ClinicalFactRevision(
            profile_id=uuid4(),
            kind="symptom",
            display="model assertion",
            source_type="system",
            verification="user_confirmed",
            created_by="local_model",
        )
