"""Property-based fuzz of the longitudinal crypto envelope (R1.4).

Hypothesis generates hostile ciphertext/nonce material and arbitrary field
mutations; the drill asserts the security contract holds for every input:

1. A well-formed envelope whose signature covers exactly its own canonical
   bytes verifies; **any** single-field mutation invalidates verification.
2. Garbage signatures never verify and never crash the verifier.
3. Verification is deterministic: same input, same verdict.
"""

from __future__ import annotations

import base64
import hashlib
import json

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from hypothesis import given, settings
from hypothesis import strategies as st

from ai_doctor.domain.longitudinal import EncryptedEnvelope
from ai_doctor.relay import verify_envelope_signature

MAX_EXAMPLES = 40

TEST_SIGNING_KEY = ec.generate_private_key(ec.SECP256R1())


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _coordinate(value: int) -> str:
    return _b64u(value.to_bytes(32, "big"))


def _canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def _sign_payload(payload: dict, key=TEST_SIGNING_KEY) -> str:
    der = key.sign(_canonical(payload), ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    return _b64u(r.to_bytes(32, "big") + s.to_bytes(32, "big"))


def make_envelope(
    ciphertext: str,
    nonce: str,
    aad_hash: str = "a" * 64,
    signing_key=TEST_SIGNING_KEY,
    pinned_timestamp: str = "2026-08-23T00:00:00.000Z",
) -> EncryptedEnvelope:
    """Build a validly-signed envelope over arbitrary ciphertext/nonce."""
    numbers = signing_key.public_key().public_numbers()
    payload = {
        "opaque_object_id": "opaque_object_123456789",
        "profile_pseudonym": "profile_pseudonym_123456789",
        "device_id": "device_123456789",
        "client_sequence": 1,
        "ciphertext": ciphertext,
        "nonce": nonce,
        "aad_hash": aad_hash,
        "ciphertext_hash": hashlib.sha256(ciphertext.encode()).hexdigest(),
        "device_signing_public_jwk": {
            "kty": "EC",
            "crv": "P-256",
            "x": _coordinate(numbers.x),
            "y": _coordinate(numbers.y),
            "ext": True,
            "key_ops": ["verify"],
        },
        "created_at": pinned_timestamp,
        "ttl_seconds": 3600,
        "envelope_version": "1",
    }
    payload["signature"] = _sign_payload(payload, signing_key)
    return EncryptedEnvelope.model_validate(payload)


hostile_ciphertext = st.binary(min_size=16, max_size=256).map(
    lambda b: _b64u(b)
)
hostile_nonce = st.binary(min_size=12, max_size=48).map(_b64u)

MUTABLE_FIELDS = (
    "opaque_object_id",
    "profile_pseudonym",
    "device_id",
    "ciphertext",
    "nonce",
    "aad_hash",
    "signature",
)


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(
    ciphertext=hostile_ciphertext,
    nonce=hostile_nonce,
    field=st.sampled_from(MUTABLE_FIELDS),
)
def test_any_single_field_mutation_invalidates_signature(ciphertext: str, nonce: str, field: str):
    envelope = make_envelope(ciphertext, nonce)
    verify_envelope_signature(envelope)  # sanity: pristine envelope verifies

    original = getattr(envelope, field)
    # Mutate the FIRST character: base64url decoding discards trailing bits of
    # the final character, so a last-char swap can leave decoded bytes intact.
    mutated_value = ("A" if original[0] != "A" else "B") + original[1:]
    mutated = envelope.model_copy(update={field: mutated_value})

    with pytest.raises((ValueError, TypeError)):
        verify_envelope_signature(mutated)


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(junk=st.binary(max_size=128))
def test_garbage_signatures_never_verify_or_crash(junk: bytes):
    envelope = make_envelope(_b64u(b"opaque_ciphertext_1234567890"), _b64u(b"x" * 16))
    object.__setattr__(envelope, "signature", _b64u(junk))
    with pytest.raises((ValueError, TypeError)):
        verify_envelope_signature(envelope)


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(ciphertext=hostile_ciphertext, nonce=hostile_nonce)
def test_verification_is_deterministic(ciphertext: str, nonce: str):
    envelope = make_envelope(ciphertext, nonce)
    first_pass = verify_envelope_signature(envelope)
    second_pass = verify_envelope_signature(envelope.model_copy(deep=True))
    assert first_pass is None and second_pass is None
