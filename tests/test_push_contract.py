"""T-09 push-contract drills: generic-only payload, no PHI, schedule lifecycle.

The manual UX checklist (device-side notification display, acknowledgement
timing) lives in docs/PUSH_MANUAL_CHECKLIST.md and is executed by hand on a
real device; this file pins everything provable in-process.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from pywebpush import WebPushException
from test_longitudinal_relay import PATIENT_HEADERS, _settings

from ai_doctor.api import create_app
from ai_doctor.push_worker import GenericPushWorker
from ai_doctor.settings import Settings


def _subscription_payload(profile: str = "profile_pseudonym_123456789") -> dict:
    return {
        "subscription_id": str(uuid4()),
        "profile_pseudonym": profile,
        "endpoint": "https://push.example/endpoint/1",
        "p256dh": "P256DHKEYMATERIAL0000000000000000000000000000",
        "auth": "AUTHSECRET00000000000000",
        "created_at": datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z"),
    }


def test_push_worker_sends_generic_message_only(monkeypatch):
    """The wire payload is exactly the generic wake-up string — no fields more."""
    settings = Settings(
        environment="preclinical",
        database_path=Path("/tmp/unused.db"),
        emergency_service_label="local emergency services",
        tokens={"patient-test-token": {"user_id": "patient-1", "role": "patient"}},
        push_enabled=True,
        push_vapid_private_key="private",
        push_vapid_subject="mailto:ops@example.org",
    )
    worker = GenericPushWorker(settings)

    captured: dict = {}

    class FakeOK(Exception):
        pass

    def fake_webpush(**kwargs):
        captured.update(kwargs)
        # pywebpush returns None on success; nothing raised means accepted.

    monkeypatch.setattr("ai_doctor.push_worker.webpush", fake_webpush)

    schedule = {
        "opaque_schedule_id": "sched-1",
        "endpoint": "https://push.example/endpoint/1",
        "p256dh": "k",
        "auth": "a",
    }
    assert worker._send(schedule) is True
    payload = json.loads(captured["data"])
    assert set(payload.keys()) == {"message"}
    from ai_doctor.relay import GENERIC_PUSH_MESSAGE

    assert payload["message"] == GENERIC_PUSH_MESSAGE
    # No PHI-shaped keys anywhere on the wire.
    forbidden = {"name", "diagnosis", "severity", "instruction", "advice", "case"}
    assert not (set(payload.keys()) & forbidden)


def test_push_worker_disabled_without_vapid(monkeypatch):
    settings = Settings(
        environment="preclinical",
        database_path=Path("/tmp/unused.db"),
        emergency_service_label="local emergency services",
        tokens={"patient-test-token": {"user_id": "patient-1", "role": "patient"}},
        push_enabled=False,
    )
    worker = GenericPushWorker(settings)
    assert (
        worker._send({"opaque_schedule_id": "s", "endpoint": "e", "p256dh": "k", "auth": "a"})
        is False
    )


def test_push_worker_provider_rejection_is_recorded_not_raised(monkeypatch):
    """A 410/404 push-provider rejection must not crash the loop."""
    settings = Settings(
        environment="preclinical",
        database_path=Path("/tmp/unused.db"),
        emergency_service_label="local emergency services",
        tokens={"patient-test-token": {"user_id": "patient-1", "role": "patient"}},
        push_enabled=True,
        push_vapid_private_key="private",
        push_vapid_subject="mailto:ops@example.org",
    )
    worker = GenericPushWorker(settings)

    def fake_webpush(**kwargs):
        raise WebPushException("gone")

    monkeypatch.setattr("ai_doctor.push_worker.webpush", fake_webpush)
    assert (
        worker._send({"opaque_schedule_id": "s", "endpoint": "e", "p256dh": "k", "auth": "a"})
        is False
    )


def test_schedule_lifecycle_claim_and_finish(tmp_path: Path, monkeypatch):
    """claim_due_schedules flips state so a second claim returns nothing."""
    from cryptography.hazmat.primitives.asymmetric import ec
    from test_device_lifecycle import _envelope_payload

    client = TestClient(create_app(_settings(tmp_path)))

    # Enroll the profile first: a signed envelope write binds credential→profile.
    enroll = client.put(
        "/v1/sync/envelopes/opaque_object_push_probe",
        headers=PATIENT_HEADERS,
        json=_envelope_payload(
            "device_push",
            ec.generate_private_key(ec.SECP256R1()),
            object_id="opaque_object_push_probe",
        ),
    )
    assert enroll.status_code == 200, enroll.text

    sub = client.post(
        "/v1/push/subscriptions",
        headers=PATIENT_HEADERS,
        json=_subscription_payload(),
    )
    assert sub.status_code == 201, sub.text
    subscription_id = sub.json()["subscription_id"]

    due_at = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
    schedule = client.put(
        "/v1/push/schedules/schedule_probe_1",
        headers=PATIENT_HEADERS,
        json={
            "opaque_schedule_id": "schedule_probe_1",
            "subscription_id": subscription_id,
            "profile_pseudonym": "profile_pseudonym_123456789",
            "due_at": due_at,
            "repeat_after_seconds": 60,
            "max_repeats": 2,
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        },
    )
    assert schedule.status_code == 200, schedule.text

    from ai_doctor.relay import OpaqueRelayRepository

    repo = OpaqueRelayRepository(_settings(tmp_path).database_path)
    first_claim = repo.claim_due_schedules()
    assert len(first_claim) == 1
    second_claim = repo.claim_due_schedules()  # 'delivering' now — no double-fire
    assert second_claim == []

    repo.finish_push_attempt("schedule_probe_1", accepted=True)
    # Repeat window is due_at + 60s; fake the clock past it instead of sleeping.
    real_utc_now = __import__("ai_doctor.relay", fromlist=["_utc_now"])._utc_now

    class _Shifted(datetime):
        @classmethod
        def now(cls, tz=None):
            return real_utc_now().replace(microsecond=0) + timedelta(seconds=61)

    import ai_doctor.relay as relay_module

    monkeypatch.setattr(relay_module, "_utc_now", lambda: _Shifted.now(timezone.utc))
    third_claim = repo.claim_due_schedules()
    assert len(third_claim) == 1  # repeat window rescheduled it
