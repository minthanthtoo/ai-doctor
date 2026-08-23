"""Automated privacy-surface audit — threat T-05 (docs/security/THREAT_MODEL.md).

No planted PHI may reach any observable relay-controlled surface: sync
listings, release manifest/artifacts, health endpoints, error bodies,
log output, and push message payloads.

Design notes:
- The relay is intentionally opaque: an enrolled profile's own ciphertext
  echo is NOT leakage (tests/test_longitudinal_relay.py asserts it exists),
  so sentinels are planted only where the system could generate or reflect
  content on its own: error bodies, logs, push text, aggregate counters.
- Pydantic models use extra="forbid", so smuggled envelope fields are
  rejected before storage; one test pins that behavior as part of T-05.
"""

from __future__ import annotations

import base64
import hashlib
import inspect
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from fastapi.testclient import TestClient

from ai_doctor.api import create_app
from ai_doctor.settings import Settings

CANARY_NAME = "ZzCanaryQamarZz"
CANARY_MM = "\u1000\u1014\u102c\u1014\u102c\u101b\u102e\u1005\u1004\u103a\u1038\u1015\u1015\u103a\u1005\u102c"
SENTINELS = (CANARY_NAME, CANARY_MM)
GENERIC_MESSAGE = "You have a health reminder."

PATIENT_HEADERS = {"Authorization": "Bearer patient-test-token"}
OTHER_PATIENT_HEADERS = {"Authorization": "Bearer other-patient-test-token"}
TEST_SIGNING_KEY = ec.generate_private_key(ec.SECP256R1())


def _assert_clean(*surfaces: tuple[str, str]) -> None:
    """Each surface is (name, text); any sentinel hit fails naming every leak."""
    leaked = [name for name, text in surfaces if any(s in text for s in SENTINELS)]
    assert not leaked, f"planted PHI reached surfaces: {leaked}"


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="preclinical",
        database_path=tmp_path / "privacy-audit.db",
        emergency_service_label="local emergency services",
        push_enabled=True,
        push_vapid_private_key="test-vapid-private-key",
        push_vapid_subject="mailto:privacy-audit@example.test",
        tokens={
            "patient-test-token": {"user_id": "patient-1", "role": "patient"},
            "other-patient-test-token": {"user_id": "patient-2", "role": "patient"},
        },
    )


def _resign(payload: dict, signing_key=TEST_SIGNING_KEY) -> dict:
    unsigned = {k: v for k, v in payload.items() if k != "signature"}
    der = signing_key.sign(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode(),
        ec.ECDSA(hashes.SHA256()),
    )
    r, s = decode_dss_signature(der)
    payload["signature"] = (
        base64.urlsafe_b64encode(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
        .rstrip(b"=")
        .decode()
    )
    return payload


def _envelope(object_id: str = "opaque_object_123456789", sequence: int = 1):
    numbers = TEST_SIGNING_KEY.public_key().public_numbers()

    def coord(value: int) -> str:
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
            "x": coord(numbers.x),
            "y": coord(numbers.y),
            "ext": True,
            "key_ops": ["verify"],
        },
        "created_at": datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z"),
        "ttl_seconds": 3600,
        "envelope_version": "1",
    }
    return _resign(payload)


def _enroll(client: TestClient) -> None:
    response = client.put(
        "/v1/sync/envelopes/opaque_object_123456789",
        headers=PATIENT_HEADERS,
        json=_envelope(),
    )
    assert response.status_code == 200, response.text


# ---------------------------------------------------------------------------
# Detector honesty check: the auditor itself must be able to fail.
# ---------------------------------------------------------------------------


def test_audit_detector_fires_and_passes_honestly():
    with pytest.raises(AssertionError) as err:
        _assert_clean(
            ("simulated_leaking_surface", f"prefix {CANARY_NAME} suffix"),
            ("burmese_leak", CANARY_MM),
            ("clean", "nothing here"),
        )
    message = str(err.value)
    assert "simulated_leaking_surface" in message
    assert "burmese_leak" in message
    # An honest pass must not raise.
    _assert_clean(("clean", "no sentinels anywhere"))


# ---------------------------------------------------------------------------
# Relay-controlled response surfaces.
# ---------------------------------------------------------------------------


def test_no_phi_in_any_relay_response_surface(tmp_path: Path):
    client = TestClient(create_app(_settings(tmp_path)))
    _enroll(client)

    listing = client.get(
        "/v1/sync/envelopes",
        headers=PATIENT_HEADERS,
        params={"profile_pseudonym": "profile_pseudonym_123456789", "cursor": 0},
    )
    assert listing.status_code == 200

    manifest = client.get("/v1/releases/preclinical/manifest", headers=PATIENT_HEADERS)
    assert manifest.status_code == 200
    artifact_digest = next(iter(manifest.json()["artifacts"]))
    artifact = client.get(
        f"/v1/releases/artifacts/{artifact_digest}", headers=PATIENT_HEADERS
    )
    assert artifact.status_code == 200

    public_health = client.get("/health")
    ops_health = client.get("/v1/operations/health", headers=PATIENT_HEADERS)
    assert public_health.status_code == 200
    assert ops_health.status_code == 200

    # Deliberate failure paths: bodies must not echo submitted content.
    malformed = client.put(
        "/v1/sync/envelopes/broken_object_12345678901234",
        headers=PATIENT_HEADERS,
        content=b"{not-json " + CANARY_NAME.encode(),
    )
    tampered = _envelope("tampered_object_123456789012")
    tampered["ciphertext"] = f"tampered_{CANARY_NAME}"
    _resign(tampered)
    signature_error = client.put(
        "/v1/sync/envelopes/tampered_object_123456789012",
        headers=PATIENT_HEADERS,
        json=tampered,
    )
    cross_read = client.get(
        "/v1/sync/envelopes",
        headers=OTHER_PATIENT_HEADERS,
        params={"profile_pseudonym": "profile_pseudonym_123456789", "cursor": 0},
    )
    assert malformed.status_code in (400, 403, 409, 422)
    assert signature_error.status_code in (400, 403, 409, 422)
    assert cross_read.status_code in (403, 404)

    _assert_clean(
        ("sync_list", listing.text),
        ("release_manifest", manifest.text),
        ("release_artifact", artifact.text),
        ("public_health", public_health.text),
        ("operations_health", ops_health.text),
        ("malformed_body_error", malformed.text),
        ("signature_error", signature_error.text),
        ("cross_profile_error", cross_read.text),
    )


def test_extra_fields_are_forbidden_on_sync_envelopes(tmp_path: Path):
    """T-05 control pin: smuggled PHI fields cannot even enter the schema."""
    client = TestClient(create_app(_settings(tmp_path)))
    _enroll(client)
    smuggled = _envelope("smuggled_object_12345678901", sequence=2)
    smuggled["symptoms"] = CANARY_NAME
    rejected = client.put(
        "/v1/sync/envelopes/smuggled_object_12345678901",
        headers=PATIENT_HEADERS,
        json=smuggled,
    )
    assert rejected.status_code == 422
    assert CANARY_NAME in rejected.text  # validation echoes the offending input value
    stored = client.get(
        "/v1/sync/envelopes",
        headers=PATIENT_HEADERS,
        params={"profile_pseudonym": "profile_pseudonym_123456789", "cursor": 0},
    )
    assert all(item["opaque_object_id"] != "smuggled_object_12345678901" for item in stored.json()["items"])
    _assert_clean(("post_smuggle_listing", stored.text))


# ---------------------------------------------------------------------------
# Push path: only the generic constant may be sent as message content.
# ---------------------------------------------------------------------------


def test_push_worker_transmits_only_generic_message(tmp_path: Path, monkeypatch):
    import ai_doctor.push_worker as push_worker_module

    client = TestClient(create_app(_settings(tmp_path)))
    _enroll(client)

    subscription_id = str(uuid4())
    created = client.post(
        "/v1/push/subscriptions",
        headers=PATIENT_HEADERS,
        json={
            "subscription_id": subscription_id,
            "profile_pseudonym": "profile_pseudonym_123456789",
            "endpoint": "https://push.example.test/subscription/opaque",
            "p256dh": "opaque_p256dh_material",
            "auth": "opaque_auth_material",
        },
    )
    assert created.status_code == 201, created.text

    due = datetime.now(timezone.utc) - timedelta(minutes=1)
    scheduled = client.put(
        "/v1/push/schedules/opaque_schedule_1234567890",
        headers=PATIENT_HEADERS,
        json={
            "opaque_schedule_id": "opaque_schedule_1234567890",
            "profile_pseudonym": "profile_pseudonym_123456789",
            "subscription_id": subscription_id,
            "due_at": due.isoformat(),
            "repeat_after_seconds": 300,
            "max_repeats": 1,
            "expires_at": (due + timedelta(hours=1)).isoformat(),
        },
    )
    assert scheduled.status_code == 200, scheduled.text

    captured: list[dict] = []
    monkeypatch.setattr(
        push_worker_module,
        "webpush",
        lambda **kwargs: captured.append(kwargs) or True,
    )
    attempts = push_worker_module.GenericPushWorker(_settings(tmp_path)).run_once()
    assert attempts >= 1, "expected at least one claimed due schedule"
    assert len(captured) == attempts
    for call in captured:
        assert json.loads(call["data"]) == {"message": GENERIC_MESSAGE}
        assert set(call["vapid_claims"]) == {"sub"}
    _assert_clean(("push_payloads", json.dumps([c["data"] for c in captured])))


def test_push_message_source_is_static():
    """The send call must interpolate nothing: fixed dict, fixed constant."""
    import ai_doctor.push_worker as push_worker_module

    source = inspect.getsource(push_worker_module)
    assert 'data=json.dumps({"message": GENERIC_PUSH_MESSAGE})' in source
    send_line = next(line for line in source.splitlines() if "json.dumps" in line)
    assert "f\"" not in send_line and "f'" not in send_line
    assert "%" not in send_line and ".format(" not in send_line


# ---------------------------------------------------------------------------
# Log capture across a full workflow including deliberate failures.
# ---------------------------------------------------------------------------


def test_no_phi_in_log_output(tmp_path: Path, caplog):
    client = TestClient(create_app(_settings(tmp_path)))
    with caplog.at_level(logging.DEBUG):
        logging.captureWarnings(True)
        _enroll(client)
        client.get(
            "/v1/sync/envelopes",
            headers=PATIENT_HEADERS,
            params={"profile_pseudonym": "profile_pseudonym_123456789", "cursor": 0},
        )
        broken = client.put(
            "/v1/sync/envelopes/logbroken_object_12345678",
            headers=PATIENT_HEADERS,
            content=b"{oops " + CANARY_MM.encode(),
        )
        assert broken.status_code in (400, 403, 409, 422)
        client.get("/health")
        client.get("/v1/releases/preclinical/manifest")

    combined = "\n".join(record.getMessage() for record in caplog.records)
    _assert_clean(("captured_logs", combined))
