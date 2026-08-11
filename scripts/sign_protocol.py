#!/usr/bin/env python3
"""Create a detached Ed25519 approval signature for one protocol JSON record.

The private key is read only to sign the canonical record and is never printed,
stored in the output, or included in exception details.
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

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

from ai_doctor.capabilities.prescribing import canonical_protocol_bytes  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sign an approved prescribing protocol with Ed25519."
    )
    parser.add_argument("--input", required=True, type=Path, help="unsigned protocol JSON record")
    parser.add_argument(
        "--output", required=True, type=Path, help="destination for the signed JSON record"
    )
    parser.add_argument("--private-key", required=True, type=Path, help="Ed25519 private key PEM")
    parser.add_argument("--key-id", required=True, help="release-controlled public-key identifier")
    parser.add_argument("--signer-id", required=True, help="clinical release approver identifier")
    parser.add_argument(
        "--force", action="store_true", help="allow replacement of an existing output file"
    )
    return parser.parse_args()


def sign_record(
    record: Dict[str, Any], private_key: Ed25519PrivateKey, key_id: str, signer_id: str
) -> Dict[str, Any]:
    """Return a new signed record; the input mapping is not modified."""

    if not isinstance(record.get("id"), str) or not record["id"]:
        raise ValueError("protocol record requires a non-empty id")
    if not isinstance(record.get("version"), str) or not record["version"]:
        raise ValueError("protocol record requires a non-empty version")
    approval = record.get("approval")
    if not isinstance(approval, dict) or approval.get("state") != "approved":
        raise ValueError("protocol approval.state must be approved before signing")

    signed = json.loads(json.dumps(record))
    signed_approval = signed["approval"]
    signed_approval["signer_id"] = signer_id
    signed_approval["key_id"] = key_id
    signed_approval["signed_at"] = datetime.now(timezone.utc).isoformat()
    signed_approval.pop("signature", None)
    signed_approval["signature"] = base64.b64encode(
        private_key.sign(canonical_protocol_bytes(signed))
    ).decode("ascii")
    return signed


def _read_private_key(path: Path) -> Ed25519PrivateKey:
    try:
        key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    except (OSError, TypeError, ValueError) as exc:
        raise ValueError("could not load an unencrypted Ed25519 private-key PEM") from exc
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("private key must be an Ed25519 private key")
    return key


def _write_json_atomically(path: Path, payload: Dict[str, Any], force: bool) -> None:
    if path.exists() and not force:
        raise ValueError("output already exists; use --force to replace it")
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(prefix=".signed-protocol-", dir=str(path.parent))
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
            raise ValueError("input must contain one protocol object")
        signed = sign_record(
            record, _read_private_key(args.private_key), args.key_id, args.signer_id
        )
        _write_json_atomically(args.output, signed, args.force)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print("protocol signing failed: " + str(exc), file=sys.stderr)
        return 2
    print("signed protocol written to " + str(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
