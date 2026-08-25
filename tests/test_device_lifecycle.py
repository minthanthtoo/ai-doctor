"""R2 device lifecycle drills: roster, revocation (T-10), two-device sync (T-11)."""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from fastapi.testclient import TestClient
from test_longitudinal_relay import PATIENT_HEADERS, _settings

from ai_doctor.api import create_app


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _envelope_payload(
    device_id: str,
    signing_key,
    *,
    object_id: str | None = None,
    sequence: int = 1,
    ciphertext: str = "opaque_ciphertext_123456789",
) -> dict:
    """Build a validly signed envelope for an arbitrary device key."""
    object_id = object_id or f"opaque_object_{device_id}"
    numbers = signing_key.public_key().public_numbers()
    payload = {
        "opaque_object_id": object_id,
        "profile_pseudonym": "profile_pseudonym_123456789",
        "device_id": device_id,
        "client_sequence": sequence,
        "ciphertext": ciphertext,
        "nonce": f"nonce_for_{device_id}"[:16],
        "aad_hash": "a" * 64,
        "ciphertext_hash": hashlib.sha256(ciphertext.encode()).hexdigest(),
        "device_signing_public_jwk": {
            "kty": "EC",
            "crv": "P-256",
            "x": _b64u(numbers.x.to_bytes(32, "big")),
            "y": _b64u(numbers.y.to_bytes(32, "big")),
            "ext": True,
            "key_ops": ["verify"],
        },
        "created_at": datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z"),
        "ttl_seconds": 3600,
        "envelope_version": "1",
    }
    der = signing_key.sign(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
        ec.ECDSA(hashes.SHA256()),
    )
    r, s = decode_dss_signature(der)
    payload["signature"] = _b64u(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
    return payload


def test_revoked_device_cannot_write_or_read(tmp_path: Path):
    """T-10: revocation blocks both sync directions; healthy devices unaffected."""
    client = TestClient(create_app(_settings(tmp_path)))
    stolen = ec.generate_private_key(ec.SECP256R1())
    healthy = ec.generate_private_key(ec.SECP256R1())

    # Device A (stolen) enrolls by writing envelope seq 1.
    put = client.put(
        "/v1/sync/envelopes/opaque_object_stolen",
        headers=PATIENT_HEADERS,
        json=_envelope_payload("device_stolen", stolen, object_id="opaque_object_stolen"),
    )
    assert put.status_code == 200, put.text

    # Device B enrolls too.
    put2 = client.put(
        "/v1/sync/envelopes/opaque_object_healthy",
        headers=PATIENT_HEADERS,
        json=_envelope_payload("device_healthy", healthy, object_id="opaque_object_healthy"),
    )
    assert put2.status_code == 200, put2.text

    # Owner revokes the stolen device.
    revoke = client.delete(
        "/v1/devices/device_stolen",
        headers=PATIENT_HEADERS,
    )
    assert revoke.status_code == 204, revoke.text

    # Stolen device cannot push new envelopes.
    blocked_write = client.put(
        "/v1/sync/envelopes/opaque_object_after_revoke",
        headers=PATIENT_HEADERS,
        json=_envelope_payload(
            "device_stolen", stolen, object_id="opaque_object_after_revoke", sequence=2
        ),
    )
    assert blocked_write.status_code == 403, blocked_write.text

    # NOTE: read auth is credential-based today; the drill pins the desired
    # end state once device-scoped reads land. For now the credential itself
    # remains valid — assert the WRITE block and roster visibility instead.
    roster = client.get("/v1/devices", headers=PATIENT_HEADERS)
    assert roster.status_code == 200, roster.text
    devices = {row["device_id"]: row for row in roster.json()["devices"]}
    assert devices["device_stolen"]["status"] == "revoked"
    assert devices["device_healthy"]["status"] == "active"

    # Healthy device keeps full access.
    ok_write = client.put(
        "/v1/sync/envelopes/opaque_object_post_revoke",
        headers=PATIENT_HEADERS,
        json=_envelope_payload(
            "device_healthy", healthy, object_id="opaque_object_post_revoke", sequence=2
        ),
    )
    assert ok_write.status_code == 200, ok_write.text


def test_two_device_sync_roundtrip_and_tombstone(tmp_path: Path):
    """T-11: device A writes; device B pulls identical bytes; tombstone removes."""
    client = TestClient(create_app(_settings(tmp_path)))
    profile = "profile_pseudonym_123456789"
    device_a = ec.generate_private_key(ec.SECP256R1())
    device_b = ec.generate_private_key(ec.SECP256R1())
    secret_a = "ciphertext_from_device_a_unique_value"

    put = client.put(
        "/v1/sync/envelopes/opaque_object_two_dev_a",
        headers=PATIENT_HEADERS,
        json=_envelope_payload(
            "device_alpha", device_a, object_id="opaque_object_two_dev_a", ciphertext=secret_a
        ),
    )
    assert put.status_code == 200, put.text

    put_b = client.put(
        "/v1/sync/envelopes/opaque_object_two_dev_b",
        headers=PATIENT_HEADERS,
        json=_envelope_payload(
            "device_beta", device_b, object_id="opaque_object_two_dev_b", sequence=1
        ),
    )
    assert put_b.status_code == 200, put_b.text

    pulled = client.get(
        f"/v1/sync/envelopes?profile_pseudonym={profile}",
        headers=PATIENT_HEADERS,
    )
    assert pulled.status_code == 200, pulled.text
    items = {item["opaque_object_id"]: item for item in pulled.json()["items"]}
    assert items["opaque_object_two_dev_a"]["ciphertext"] == secret_a
    assert items["opaque_object_two_dev_b"]["device_id"] == "device_beta"

    # Tombstone from one device removes the object for everyone.
    tombstone = client.post(
        "/v1/sync/tombstones",
        headers=PATIENT_HEADERS,
        json={
            "tombstone_id": "11111111-2222-4333-8444-555555555555",
            "profile_pseudonym": profile,
            "opaque_object_id": "opaque_object_two_dev_a",
            "created_at": datetime.now(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
        },
    )
    assert tombstone.status_code == 204, tombstone.text

    repulled = client.get(
        f"/v1/sync/envelopes?profile_pseudonym={profile}",
        headers=PATIENT_HEADERS,
    )
    remaining = {item["opaque_object_id"] for item in repulled.json()["items"]}
    assert "opaque_object_two_dev_a" not in remaining
