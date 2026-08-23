#!/usr/bin/env python3
"""Create a detached Ed25519 approval signature for the v3 release manifest.

Mirrors scripts/sign_protocol.py conventions: the private key is read only
to sign canonical bytes, never printed or stored; output is written
atomically; an existing output file requires --force.

The signature covers the canonical manifest JSON with ``signature`` set to
``null`` — byte-identical recipe to relay._manifest_digest. Verify with
ai_doctor.config.verify_release_manifest.verify_manifest_signature.

Key generation (one-time, operator-run):

    /Users/min/miniforge3/bin/python - <<'PY'
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    import base64
    key = Ed25519PrivateKey.generate()
    print(base64.b64encode(key.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
        serialization.NoEncryption())).decode())
    print(base64.b64encode(key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode())
    PY

Keep the private material in an approved secret store; publish only the
base64 public half into the trusted-key map consumed by
AI_DOCTOR_RELEASE_MANIFEST_PUBLIC_KEYS_JSON.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import tempfile
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cryptography.exceptions import InvalidSignature  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import (  # noqa: E402
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
try:  # optional self-check that the signed bytes verify before writing
    from ai_doctor.config.verify_release_manifest import (  # noqa: E402
        manifest_canonical_bytes,
        verify_manifest_signature,
    )
except ImportError as error:  # pragma: no cover - src always present in repo layout
    raise SystemExit(f"cannot import verifier module: {error}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sign the release manifest with Ed25519."
    )
    parser.add_argument("--input", required=True, type=Path, help="unsigned manifest JSON")
    parser.add_argument("--output", required=True, type=Path, help="destination for the signed manifest")
    parser.add_argument("--private-key-b64", required=True, help="base64 raw Ed25519 private key (32 bytes)")
    parser.add_argument("--key-id", required=True, help="release-controlled public-key identifier")
    parser.add_argument("--signer-id", required=True, help="release approver identifier")
    parser.add_argument(
        "--force", action="store_true", help="allow replacement of an existing output file"
    )
    return parser.parse_args()


def _load_private_key(material_b64: str) -> Ed25519PrivateKey:
    try:
        raw = base64.b64decode(material_b64, validate=True)
    except Exception as error:
        raise ValueError("private key is not valid base64") from error
    if len(raw) != 32:
        raise ValueError("private key material must decode to exactly 32 bytes")
    return Ed25519PrivateKey.from_private_bytes(raw)


def sign_manifest(
    record: Dict[str, Any],
    private_key: Ed25519PrivateKey,
    key_id: str,
    signer_id: str,
) -> Dict[str, Any]:
    """Return a signed copy; refuses to re-sign an already-approved manifest."""
    if not isinstance(record.get("release_id"), str) or not record["release_id"]:
        raise ValueError("manifest requires a non-empty release_id")
    existing = record.get("signature")
    if isinstance(existing, dict) and existing.get("state") == "approved":
        raise ValueError("manifest already carries an approved signature; start from the unsigned release record")

    signed = json.loads(json.dumps(record))
    public_key = private_key.public_key()
    encoded_signature = base64.b64encode(private_key.sign(manifest_canonical_bytes(signed))).decode("ascii")
    signed["signature"] = {
        "state": "approved",
        "key_id": key_id,
        "signer_id": signer_id,
        "signed_at": datetime.now(timezone.utc).isoformat(),
        "algorithm": "ed25519",
        "signature": encoded_signature,
    }
    # Self-check before anything touches disk.
    check_keys: dict[str, Ed25519PublicKey] = {key_id: public_key}
    verify_manifest_signature(signed, check_keys)
    return signed


def _write_json_atomically(path: Path, payload: Dict[str, Any], force: bool) -> None:
    if path.exists() and not force:
        raise ValueError("output already exists; use --force to replace it")
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(prefix=".signed-manifest-", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except Exception:
        with suppress(FileNotFoundError):
            os.unlink(temporary_name)
        raise


def main() -> int:
    args = parse_args()
    try:
        with args.input.open("r", encoding="utf-8") as handle:
            record = json.load(handle)
        if not isinstance(record, dict):
            raise ValueError("input must contain one manifest object")
        signed = sign_manifest(record, _load_private_key(args.private_key_b64), args.key_id, args.signer_id)
        _write_json_atomically(args.output, signed, args.force)
    except (OSError, ValueError, json.JSONDecodeError, InvalidSignature) as exc:
        print("manifest signing failed: " + str(exc), file=sys.stderr)
        return 2
    print("signed manifest written to " + str(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
