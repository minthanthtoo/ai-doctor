# Prescribing protocol releases

This is the release procedure for protocol-bounded **prescription drafts**. A protocol is not a prescription, and signing one never enables order placement. The runtime emits a non-executable `PrescriptionDraft`; a named authorized clinician must approve it separately. The application does not place, transmit, or modify an order.

## Protocol record

Each JSON file passed to the signing tool contains one object. The clinically governed release process owns the contents, clinical validity, review evidence, and approval state.

```json
{
  "id": "organization-controlled-identifier",
  "version": "release-version",
  "approval": {
    "state": "approved",
    "signer_id": "filled-by-signing-tool",
    "key_id": "filled-by-signing-tool",
    "signed_at": "filled-by-signing-tool",
    "signature": "filled-by-signing-tool"
  },
  "required_inputs": [
    "age_years",
    "allergy_status_confirmed",
    "medication_list_confirmed",
    "pregnancy_status",
    "confirmed_by_clinician",
    "condition:organization-approved-indication"
  ],
  "contraindications": ["organization-defined-condition"],
  "medication": {
    "name": "organization-controlled name",
    "dose": "approved protocol text",
    "route": "approved protocol text",
    "frequency": "approved protocol text",
    "indication": "approved protocol text",
    "duration": "optional approved text",
    "monitoring": [],
    "warnings": []
  }
}
```

`id`, `version`, `approval`, `required_inputs`, `contraindications`, and all five required `medication` fields are required. At least one `condition:<name>` input must bind the protocol to a clinician-verified indication. Independently of protocol content, the runtime always requires age, a clinician-confirmed snapshot, reconciled allergy and medication lists, and known pregnancy status. The runtime rejects unknown protocol IDs, records not in `approved` state, missing approval metadata, invalid signatures, and malformed records. It blocks drafting when any required input is missing, an indication is unverified, pregnancy is not permitted, an allergy or protocol-listed interaction is present, or another signed contraindication matches.

## Signing

Use an unencrypted Ed25519 PKCS#8 PEM private key held in the organization’s approved key-management system or secure release environment. Never put that key into a protocol repository, deployment configuration, ticket, terminal transcript, or chat.

```bash
python scripts/sign_protocol.py \
  --input releases/protocol-unsigned.json \
  --output releases/protocol-signed.json \
  --private-key /secure/path/protocol-release-ed25519.pem \
  --key-id clinical-protocol-2026q3 \
  --signer-id clinical-safety-owner
```

The tool adds `signer_id`, `key_id`, `signed_at`, and a Base64 detached Ed25519 `signature`. It signs a deterministic UTF-8 JSON encoding of the complete record after removing only `approval.signature`; changing any other signed field invalidates verification. It will not replace an existing destination without `--force`, and it never prints private-key material.

## Verification and deployment

Deploy an `Ed25519ProtocolVerifier` with a release-controlled map of `key_id` to Base64 raw Ed25519 public key:

```python
repository = ProtocolRepository.from_file(
    path_to_release,
    signature_verifier=Ed25519ProtocolVerifier({
        "clinical-protocol-2026q3": "base64-raw-ed25519-public-key"
    }),
)
```

Production must always provide a verifier. The `LOCAL_TEST_FIXTURE_ONLY` signature is accepted only if `allow_test_fixtures=True`; that setting is exclusively for automated tests and must never be enabled in a deployed environment.

## Key rotation

1. Generate a new Ed25519 key pair in the approved key-management system and give its public key a new immutable `key_id`.
2. Add the new public key to the verifier key ring while retaining the prior key for all retained releases that it signed.
3. Re-sign each new protocol release with the new key and record the signing approver in the change-control record.
4. Verify the signed artifact in a clean environment before promotion; retain the artifact, public-key mapping, verification result, and clinical approval evidence together.
5. Remove a retired public key only after every retained artifact it verifies has been migrated or has passed its defined retention period. A suspected compromise requires an immediate disablement/kill-switch decision, incident review, and re-signing from a trusted key.

The public-key map itself is a controlled, versioned release artifact. Key IDs are identifiers, not secrets.
