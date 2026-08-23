"""Signing and verification drills for the v3 release manifest (threat T-08).

All fixtures live in tmp_path copies; the committed release_manifest_v3.json
is read-only here and keeps ``signature: null`` until a human signs a release.
"""

from __future__ import annotations

import base64
import hashlib
import json
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import sign_release_manifest  # noqa: E402

from ai_doctor.config.verify_release_manifest import (  # noqa: E402
    load_public_keys,
    manifest_canonical_bytes,
    public_key_b64,
    verify_manifest_signature,
)
from ai_doctor.relay import _manifest_digest  # noqa: E402

REAL_MANIFEST = PROJECT_ROOT / "src" / "ai_doctor" / "config" / "release_manifest_v3.json"
DRILL_KEY = Ed25519PrivateKey.generate()
OTHER_KEY = Ed25519PrivateKey.generate()
TRUSTED_KEYS = {"drill-key-1": DRILL_KEY.public_key(), "drill-key-2": OTHER_KEY.public_key()}


def _unsigned_copy() -> dict:
    manifest = json.loads(REAL_MANIFEST.read_text(encoding="utf-8"))
    manifest["signature"] = None
    return manifest


# ---------------------------------------------------------------------------
# Roundtrip and canonicalization consistency.
# ---------------------------------------------------------------------------


def test_sign_and_verify_roundtrip():
    signed = sign_release_manifest.sign_manifest(
        _unsigned_copy(), private_key=DRILL_KEY, key_id="drill-key-1", signer_id="release-drill"
    )
    assert signed["signature"]["state"] == "approved"
    assert signed["signature"]["algorithm"] == "ed25519"
    verify_manifest_signature(signed, TRUSTED_KEYS)


def test_signing_bytes_match_relay_manifest_digest_recipe():
    """Signature bytes must hash identically to the relay's manifest digest."""
    manifest = _unsigned_copy()
    assert hashlib.sha256(manifest_canonical_bytes(manifest)).hexdigest() == _manifest_digest(manifest)


def test_committed_manifest_is_unsigned_preclinical_default():
    manifest = json.loads(REAL_MANIFEST.read_text(encoding="utf-8"))
    assert manifest.get("signature") is None


def test_refuses_to_double_sign():
    signed = sign_release_manifest.sign_manifest(
        _unsigned_copy(), private_key=DRILL_KEY, key_id="drill-key-1", signer_id="release-drill"
    )
    with pytest.raises(ValueError, match="already carries an approved signature"):
        sign_release_manifest.sign_manifest(
            signed, private_key=DRILL_KEY, key_id="drill-key-1", signer_id="release-drill"
        )


# ---------------------------------------------------------------------------
# Fail-closed verification paths.
# ---------------------------------------------------------------------------


def test_tampered_manifest_field_fails_verification():
    signed = sign_release_manifest.sign_manifest(
        _unsigned_copy(), private_key=DRILL_KEY, key_id="drill-key-1", signer_id="release-drill"
    )
    signed["jurisdiction"] = "US"
    with pytest.raises(ValueError, match="verification failed"):
        verify_manifest_signature(signed, TRUSTED_KEYS)


def test_unknown_key_id_fails_verification():
    signed = sign_release_manifest.sign_manifest(
        _unsigned_copy(), private_key=DRILL_KEY, key_id="rogue-key", signer_id="release-drill"
    )
    with pytest.raises(ValueError, match="absent from the trusted map"):
        verify_manifest_signature(signed, TRUSTED_KEYS)


def test_wrong_trusted_key_fails_verification():
    signed = sign_release_manifest.sign_manifest(
        _unsigned_copy(), private_key=DRILL_KEY, key_id="drill-key-2", signer_id="release-drill"
    )
    # key_id claims drill-key-2 but the signature was produced by DRILL_KEY.
    with pytest.raises(ValueError):
        verify_manifest_signature(signed, {"drill-key-2": OTHER_KEY.public_key()})


def test_missing_signature_block_fails_closed():
    with pytest.raises(ValueError, match="not signed"):
        verify_manifest_signature(_unsigned_copy(), TRUSTED_KEYS)


def test_corrupted_signature_material_fails_closed():
    signed = sign_release_manifest.sign_manifest(
        _unsigned_copy(), private_key=DRILL_KEY, key_id="drill-key-1", signer_id="release-drill"
    )
    raw = base64.b64decode(signed["signature"]["signature"])
    flipped = bytearray(raw)
    flipped[0] ^= 0xFF
    signed["signature"]["signature"] = base64.b64encode(bytes(flipped)).decode()
    with pytest.raises(ValueError, match="verification failed"):
        verify_manifest_signature(signed, TRUSTED_KEYS)


def test_non_base64_signature_material_fails_closed():
    signed = sign_release_manifest.sign_manifest(
        _unsigned_copy(), private_key=DRILL_KEY, key_id="drill-key-1", signer_id="release-drill"
    )
    signed["signature"]["signature"] = "!!!not-base64!!!"
    with pytest.raises(ValueError, match="valid base64"):
        verify_manifest_signature(signed, TRUSTED_KEYS)


def test_public_key_roundtrip_via_b64_map():
    material = public_key_b64(DRILL_KEY.public_key())
    loaded = load_public_keys({"drill-key-1": material})
    signed = sign_release_manifest.sign_manifest(
        _unsigned_copy(), private_key=DRILL_KEY, key_id="drill-key-1", signer_id="release-drill"
    )
    verify_manifest_signature(signed, loaded)


# ---------------------------------------------------------------------------
# End-to-end drills through the running app (Task 2.3).
# ---------------------------------------------------------------------------


from fastapi.testclient import TestClient  # noqa: E402

from ai_doctor.api import create_app  # noqa: E402
from ai_doctor.settings import Settings  # noqa: E402

DRILL_TOKENS = {"patient-test-token": {"user_id": "patient-1", "role": "patient"}}


def _drill_settings(tmp_path: Path, **overrides) -> Settings:
    defaults = dict(
        environment="preclinical",
        database_path=tmp_path / "drill.db",
        emergency_service_label="local emergency services",
        tokens=DRILL_TOKENS,
        release_manifest_path=tmp_path / "config" / "release_manifest_v3.json",
    )
    defaults.update(overrides)
    return Settings(**defaults)


def _write_fixture_release(tmp_path: Path, manifest: dict) -> Path:
    """Mirror the repo layout: <root>/config/manifest.json + <root>/knowledge/v3/pack.json."""
    config_dir = tmp_path / "config"
    pack_dir = tmp_path / "knowledge" / "v3"
    config_dir.mkdir(parents=True, exist_ok=True)
    pack_dir.mkdir(parents=True, exist_ok=True)
    raw_pack = (PROJECT_ROOT / "src" / "ai_doctor" / "knowledge" / "v3" / "cardiometabolic_pack.json").read_bytes()
    (pack_dir / "cardiometabolic_pack.json").write_bytes(raw_pack)
    manifest_path = config_dir / "release_manifest_v3.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest_path


def _signed_fixture(tmp_path: Path, key=DRILL_KEY, key_id="drill-key-1") -> Path:
    return _write_fixture_release(
        tmp_path,
        sign_release_manifest.sign_manifest(_unsigned_copy(), private_key=key, key_id=key_id, signer_id="release-drill"),
    )


def test_drill_signed_manifest_boots_and_serves_verifiable_digest(tmp_path: Path):
    _signed_fixture(tmp_path)
    settings = _drill_settings(
        tmp_path, release_manifest_public_keys={"drill-key-1": public_key_b64(DRILL_KEY.public_key())}
    )
    client = TestClient(create_app(settings))
    headers = {"Authorization": "Bearer patient-test-token"}
    served = client.get("/v1/releases/preclinical/manifest", headers=headers)
    assert served.status_code == 200
    body = served.json()
    expected = body.pop("manifest_digest")
    assert _manifest_digest(body) == expected


def test_drill_require_signed_refuses_unsigned_startup(tmp_path: Path):
    _write_fixture_release(tmp_path, _unsigned_copy())
    settings = _drill_settings(tmp_path, require_signed_manifest=True)
    with pytest.raises(RuntimeError, match="carries no approved signature"):
        create_app(settings)


def test_drill_key_rotation_revokes_old_signer(tmp_path: Path):
    """Signed by drill-key-1 while only drill-key-2 is trusted -> refuse boot."""
    _signed_fixture(tmp_path)  # signed by DRILL_KEY (drill-key-1)
    settings = _drill_settings(
        tmp_path, release_manifest_public_keys={"drill-key-2": public_key_b64(OTHER_KEY.public_key())}
    )
    with pytest.raises(RuntimeError):
        create_app(settings)


def test_drill_tampered_artifact_refuses_startup(tmp_path: Path):
    _signed_fixture(tmp_path)
    pack_path = tmp_path / "knowledge" / "v3" / "cardiometabolic_pack.json"
    poisoned = json.loads(pack_path.read_text(encoding="utf-8"))
    poisoned["red_flag_symptoms"][0]["terms"] = ["tampered chest pain"]
    pack_path.write_text(json.dumps(poisoned, ensure_ascii=False), encoding="utf-8")
    settings = _drill_settings(
        tmp_path, release_manifest_public_keys={"drill-key-1": public_key_b64(DRILL_KEY.public_key())}
    )
    with pytest.raises(RuntimeError, match="integrity verification"):
        create_app(settings)


def test_drill_stable_channel_stays_closed_while_unapproved(tmp_path: Path):
    _signed_fixture(tmp_path)
    settings = _drill_settings(
        tmp_path, release_manifest_public_keys={"drill-key-1": public_key_b64(DRILL_KEY.public_key())}
    )
    client = TestClient(create_app(settings))
    headers = {"Authorization": "Bearer patient-test-token"}
    assert client.get("/v1/releases/stable/manifest", headers=headers).status_code == 404
