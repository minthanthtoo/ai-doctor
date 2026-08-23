import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from fastapi.testclient import TestClient
from pydantic import ValidationError

from ai_doctor.api import create_app
from ai_doctor.domain.longitudinal import ClinicalFactRevision
from ai_doctor.settings import Settings

PATIENT_HEADERS = {"Authorization": "Bearer patient-test-token"}
OTHER_PATIENT_HEADERS = {"Authorization": "Bearer other-patient-test-token"}
PHYSICIAN_HEADERS = {"Authorization": "Bearer physician-test-token"}
SAFETY_HEADERS = {"Authorization": "Bearer safety-test-token"}
TEST_SIGNING_KEY = ec.generate_private_key(ec.SECP256R1())


def _resign(payload, signing_key=TEST_SIGNING_KEY):
    unsigned = {key: value for key, value in payload.items() if key != "signature"}
    der_signature = signing_key.sign(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode(),
        ec.ECDSA(hashes.SHA256()),
    )
    r, s = decode_dss_signature(der_signature)
    raw_signature = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    payload["signature"] = base64.urlsafe_b64encode(raw_signature).rstrip(b"=").decode()
    return payload


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="preclinical",
        database_path=tmp_path / "relay.db",
        emergency_service_label="local emergency services",
        tokens={
            "patient-test-token": {"user_id": "patient-1", "role": "patient"},
            "other-patient-test-token": {"user_id": "patient-2", "role": "patient"},
            "physician-test-token": {"user_id": "doctor-1", "role": "physician"},
            "safety-test-token": {
                "user_id": "safety-1",
                "role": "clinical_safety_officer",
            },
        },
    )


def _envelope(
    object_id: str = "opaque_object_123456789",
    sequence: int = 1,
    signing_key=TEST_SIGNING_KEY,
):
    numbers = signing_key.public_key().public_numbers()

    def encoded_coordinate(value: int) -> str:
        return base64.urlsafe_b64encode(value.to_bytes(32, "big")).rstrip(b"=").decode()

    payload = {
        "opaque_object_id": object_id,
        "profile_pseudonym": "profile_pseudonym_123456789",
        "device_id": "device_123456789",
        "client_sequence": sequence,
        "ciphertext": "opaque_ciphertext_123456789",
        "nonce": "opaque_nonce_1234",
        "aad_hash": "a" * 64,
        "ciphertext_hash": hashlib.sha256(b"opaque_ciphertext_123456789").hexdigest(),
        "device_signing_public_jwk": {
            "kty": "EC",
            "crv": "P-256",
            "x": encoded_coordinate(numbers.x),
            "y": encoded_coordinate(numbers.y),
            "ext": True,
            "key_ops": ["verify"],
        },
        "created_at": datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z"),
        "ttl_seconds": 3600,
        "envelope_version": "1",
    }
    return _resign(payload, signing_key)


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
    response = client.put(
        "/v1/sync/envelopes/different_object_123456789",
        headers=PATIENT_HEADERS,
        json=replay,
    )
    assert response.status_code == 409


def test_invalid_envelopes_do_not_enroll_profile_or_replace_device_key(tmp_path: Path):
    client = TestClient(create_app(_settings(tmp_path)))
    tampered = _envelope()
    tampered["ciphertext"] = "tampered_ciphertext_123456789"
    invalid = client.put(
        "/v1/sync/envelopes/opaque_object_123456789",
        headers=PATIENT_HEADERS,
        json=tampered,
    )
    assert invalid.status_code == 409

    path_mismatch = client.put(
        "/v1/sync/envelopes/wrong_opaque_object_123456789",
        headers=PATIENT_HEADERS,
        json=_envelope(),
    )
    assert path_mismatch.status_code == 422

    valid = _envelope("valid_other_profile_object_123456789")
    valid["profile_pseudonym"] = "valid_other_profile_123456789"
    _resign(valid)
    accepted = client.put(
        "/v1/sync/envelopes/valid_other_profile_object_123456789",
        headers=PATIENT_HEADERS,
        json=valid,
    )
    assert accepted.status_code == 200

    alternate_key = ec.generate_private_key(ec.SECP256R1())
    substituted = _envelope(
        "substituted_device_object_123456789",
        sequence=2,
        signing_key=alternate_key,
    )
    substituted["profile_pseudonym"] = "valid_other_profile_123456789"
    _resign(substituted, alternate_key)
    rejected_substitution = client.put(
        "/v1/sync/envelopes/substituted_device_object_123456789",
        headers=PATIENT_HEADERS,
        json=substituted,
    )
    assert rejected_substitution.status_code == 409


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


def test_profile_enrollment_prevents_cross_patient_access_and_rebinding(tmp_path: Path):
    client = TestClient(create_app(_settings(tmp_path)))
    enrolled = client.put(
        "/v1/sync/envelopes/opaque_object_123456789",
        headers=PATIENT_HEADERS,
        json=_envelope(),
    )
    assert enrolled.status_code == 200

    cross_patient_read = client.get(
        "/v1/sync/envelopes",
        headers=OTHER_PATIENT_HEADERS,
        params={"profile_pseudonym": "profile_pseudonym_123456789", "cursor": 0},
    )
    assert cross_patient_read.status_code == 403

    cross_patient_tombstone = client.post(
        "/v1/sync/tombstones",
        headers=OTHER_PATIENT_HEADERS,
        json={
            "tombstone_id": str(uuid4()),
            "profile_pseudonym": "profile_pseudonym_123456789",
            "opaque_object_id": "opaque_object_123456789",
        },
    )
    assert cross_patient_tombstone.status_code == 403

    stolen_profile_write = _envelope("other_opaque_object_123456789", sequence=2)
    cross_patient_write = client.put(
        "/v1/sync/envelopes/other_opaque_object_123456789",
        headers=OTHER_PATIENT_HEADERS,
        json=stolen_profile_write,
    )
    assert cross_patient_write.status_code == 403

    other_profile = _envelope("patient_two_object_123456789", sequence=1)
    other_profile["profile_pseudonym"] = "second_profile_pseudonym_123456789"
    other_profile["device_id"] = "second_device_123456789"
    _resign(other_profile)
    second_enrollment = client.put(
        "/v1/sync/envelopes/patient_two_object_123456789",
        headers=OTHER_PATIENT_HEADERS,
        json=other_profile,
    )
    assert second_enrollment.status_code == 200

    rebinding = _envelope("rebind_object_123456789", sequence=3)
    rebinding["profile_pseudonym"] = "second_profile_pseudonym_123456789"
    _resign(rebinding)
    rebind_response = client.put(
        "/v1/sync/envelopes/rebind_object_123456789",
        headers=PATIENT_HEADERS,
        json=rebinding,
    )
    assert rebind_response.status_code == 403


def test_safety_role_can_inspect_release_but_not_patient_payloads(tmp_path: Path):
    client = TestClient(create_app(_settings(tmp_path)))
    client.put(
        "/v1/sync/envelopes/opaque_object_123456789",
        headers=PATIENT_HEADERS,
        json=_envelope(),
    )

    payload_attempt = client.get(
        "/v1/sync/envelopes",
        headers=SAFETY_HEADERS,
        params={"profile_pseudonym": "profile_pseudonym_123456789", "cursor": 0},
    )
    assert payload_attempt.status_code == 403

    manifest = client.get("/v1/releases/preclinical/manifest", headers=SAFETY_HEADERS)
    assert manifest.status_code == 200
    health = client.get("/v1/operations/health", headers=SAFETY_HEADERS)
    assert health.status_code == 200
    assert "encrypted_envelopes" not in health.json()
    assert "scheduled_generic_pushes" not in health.json()


def test_push_schedule_forces_generic_message(tmp_path: Path):
    client = TestClient(create_app(_settings(tmp_path)))
    enrollment = client.put(
        "/v1/sync/envelopes/opaque_object_123456789",
        headers=PATIENT_HEADERS,
        json=_envelope(),
    )
    assert enrollment.status_code == 200
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

    patient_health = client.get("/v1/operations/health", headers=PATIENT_HEADERS)
    assert patient_health.status_code == 200
    assert patient_health.json()["encrypted_envelopes"] == 1
    assert patient_health.json()["scheduled_generic_pushes"] == 1

    other_profile = _envelope("patient_two_object_123456789", sequence=1)
    other_profile["profile_pseudonym"] = "second_profile_pseudonym_123456789"
    other_profile["device_id"] = "second_device_123456789"
    _resign(other_profile)
    second_enrollment = client.put(
        "/v1/sync/envelopes/patient_two_object_123456789",
        headers=OTHER_PATIENT_HEADERS,
        json=other_profile,
    )
    assert second_enrollment.status_code == 200

    cross_patient_delete = client.delete(
        "/v1/push/schedules/opaque_schedule_123456789",
        headers=OTHER_PATIENT_HEADERS,
    )
    assert cross_patient_delete.status_code == 404

    still_scheduled = client.get("/v1/operations/health", headers=PATIENT_HEADERS)
    assert still_scheduled.json()["scheduled_generic_pushes"] == 1


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
