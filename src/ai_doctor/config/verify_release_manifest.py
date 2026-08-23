"""Runtime verification of the signed v3 release manifest (threat T-08).

The manifest carries an optional detached Ed25519 approval signature under
the top-level ``signature`` field. Signing covers the canonical manifest
bytes with ``signature`` set to ``null`` — the exact canonicalization used
by ``relay._manifest_digest`` so digests and signatures stay consistent.

Verification fails closed: any missing, malformed, untrusted-key, or
non-verifying signature raises ``ValueError``. Callers decide whether an
absent signature is acceptable (preclinical default) or fatal (enforced
operator posture).
"""

from __future__ import annotations

import base64
import binascii
import json
from typing import Any, Dict, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def manifest_canonical_bytes(manifest: Mapping[str, Any]) -> bytes:
    unsigned = dict(manifest)
    unsigned["signature"] = None
    return json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode("utf-8")


def decode_public_key(material: str) -> Ed25519PublicKey:
    """Decode base64-encoded raw 32-byte Ed25519 public key material."""
    try:
        raw = base64.b64decode(material, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError("public key material is not valid base64") from error
    if len(raw) != 32:
        raise ValueError("public key material must decode to exactly 32 bytes")
    return Ed25519PublicKey.from_public_bytes(raw)


def load_public_keys(mapping: Mapping[str, str]) -> Dict[str, Ed25519PublicKey]:
    keys: Dict[str, Ed25519PublicKey] = {}
    for key_id, material in mapping.items():
        try:
            keys[key_id] = decode_public_key(material)
        except ValueError as error:
            raise ValueError(f"invalid public key for {key_id!r}: {error}") from error
    return keys


def public_key_b64(public_key: Ed25519PublicKey) -> str:
    """Encode an Ed25519 public key for trusted-key-map JSON files."""
    return base64.b64encode(
        public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    ).decode("ascii")


def verify_manifest_signature(
    manifest: Mapping[str, Any],
    public_keys: Mapping[str, Ed25519PublicKey],
) -> None:
    """Raise ``ValueError`` unless the manifest verifies against a trusted key."""
    signature_block = manifest.get("signature")
    if not isinstance(signature_block, dict):
        raise ValueError("release manifest is not signed")
    if signature_block.get("state") != "approved":
        raise ValueError("manifest signature block is not approved")
    key_id = signature_block.get("key_id")
    if not isinstance(key_id, str) or key_id not in public_keys:
        raise ValueError("manifest signed by a key absent from the trusted map")
    encoded_signature = signature_block.get("signature")
    if not isinstance(encoded_signature, str):
        raise ValueError("manifest signature material is missing")
    try:
        decoded = base64.b64decode(encoded_signature, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError("manifest signature is not valid base64") from error
    try:
        public_keys[key_id].verify(decoded, manifest_canonical_bytes(manifest))
    except InvalidSignature as error:
        raise ValueError("manifest signature verification failed") from error
