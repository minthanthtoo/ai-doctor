"""R3.1 data-exit drills: full-profile export and hard delete.

The relay stores only ciphertext, so export hands the owner their opaque
envelopes (they alone hold keys) plus roster/schedule metadata; delete must
leave ZERO rows for the profile across every relay table.
"""

from __future__ import annotations

from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from test_device_lifecycle import _envelope_payload
from test_longitudinal_relay import PATIENT_HEADERS, _settings

from ai_doctor.api import create_app

PROFILE = "profile_pseudonym_123456789"


def _seed(tmp_path):
    client = TestClient(create_app(_settings(tmp_path)))
    for index in range(2):
        put = client.put(
            f"/v1/sync/envelopes/opaque_object_exit_{index}",
            headers=PATIENT_HEADERS,
            json=_envelope_payload(
                f"device_exit_{index}",
                ec.generate_private_key(ec.SECP256R1()),
                object_id=f"opaque_object_exit_{index}",
            ),
        )
        assert put.status_code == 200, put.text
    return client


def test_export_returns_profile_envelopes_and_metadata_without_plaintext(tmp_path):

    client = _seed(tmp_path)
    response = client.get(f"/v1/profile/export?profile_pseudonym={PROFILE}", headers=PATIENT_HEADERS)
    assert response.status_code == 200, response.text
    body = response.json()
    assert {e["opaque_object_id"] for e in body["envelopes"]} == {
        "opaque_object_exit_0",
        "opaque_object_exit_1",
    }
    # Export is ciphertext-only: no plaintext-shaped fields.
    envelope_keys = set(body["envelopes"][0].keys())
    forbidden = {"plaintext", "diagnosis", "name", "note"}
    assert not (envelope_keys & forbidden)
    assert isinstance(body["devices"], list)


def test_hard_delete_purges_every_trace_of_the_profile(tmp_path):
    import sqlite3

    client = _seed(tmp_path)
    # Add device + subscription + schedule so delete has more to purge.
    sub = client.post(
        "/v1/push/subscriptions",
        headers=PATIENT_HEADERS,
        json={
            "subscription_id": "11111111-2222-4333-8444-555555555555",
            "profile_pseudonym": PROFILE,
            "endpoint": "https://push.example/exit-endpoint",
            "p256dh": "P256DHKEYMATERIAL0000000000000000000000000000",
            "auth": "AUTHSECRET00000000000000",
            "created_at": "2026-08-25T00:00:00.000Z",
        },
    )
    assert sub.status_code == 201, sub.text

    deleted = client.delete(
        f"/v1/profile?profile_pseudonym={PROFILE}&confirm={PROFILE}",
        headers=PATIENT_HEADERS,
    )
    assert deleted.status_code == 204, deleted.text

    connection = sqlite3.connect(_settings(tmp_path).database_path)
    connection.row_factory = sqlite3.Row
    for table in (
        "relay_envelopes",
        "relay_tombstones",
        "relay_devices",
        "push_subscriptions",
        "push_schedules",
        "relay_profile_owners",
    ):
        count = connection.execute(
            f"SELECT COUNT(*) AS n FROM {table} WHERE profile_pseudonym = ?",
            (PROFILE,),
        ).fetchone()
        assert count["n"] == 0, f"{table} still holds rows after hard delete"


def test_delete_requires_exact_confirmation_token(tmp_path):
    client = _seed(tmp_path)
    wrong = client.delete(
        f"/v1/profile?profile_pseudonym={PROFILE}&confirm=wrong-token",
        headers=PATIENT_HEADERS,
    )
    assert wrong.status_code == 422
    # Data still present.
    feed = client.get(f"/v1/sync/envelopes?profile_pseudonym={PROFILE}", headers=PATIENT_HEADERS)
    assert len(feed.json()["items"]) >= 1


def test_delete_refuses_foreign_profile(tmp_path):
    client = _seed(tmp_path)
    foreign = client.delete(
        "/v1/profile?profile_pseudonym=someone_elses_profile_data&confirm=someone_elses_profile_data",
        headers=PATIENT_HEADERS,
    )
    assert foreign.status_code == 404
    # Own data untouched.
    feed = client.get(f"/v1/sync/envelopes?profile_pseudonym={PROFILE}", headers=PATIENT_HEADERS)
    assert len(feed.json()["items"]) >= 1
