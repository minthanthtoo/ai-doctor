# Personal steward security threat model

Status: active preclinical threat model; not an independent security assessment.

## Trust boundaries and assets

| Boundary | Trusted assets | Untrusted inputs |
|---|---|---|
| Phone PWA | Profile key, device signing key, decrypted events, active snapshot | Chat, imported files, OCR, model output, notification wake-up |
| Home relay | Credential-to-profile binding, device public keys, ciphertext envelopes, schedules | All client requests and envelope metadata |
| Model broker | Provider credential, strict request schema, release configuration | Minimized clinical facts, provider response, network failure |
| Push provider | No clinical content | Delivery metadata and generic wake-up message |
| Release channel | Pinned manifests and artifacts | Stale, revoked, substituted or corrupted content |

The browser cannot protect secrets on a fully compromised or coerced device. Relay metadata—timing, IP address, object size and device count—is sensitive even when payloads are encrypted.

## Threat register

| ID | Threat / abuse case | Preventive control | Detection / evidence | Current state | Remaining work |
|---|---|---|---|---|---|
| T-01 | Patient credential reads or deletes another profile | First-use principal binding; every profile-bearing route checks ownership | Cross-token read/write/tombstone/delete tests | Implemented | Replace static credential with production identity and penetration-test |
| T-02 | Forged or tampered sync envelope | P-256 signature over canonical envelope; ciphertext hash verification; enrolled device key pin | Invalid signature, hash tamper and key substitution tests | Implemented | Cross-browser/device interoperability matrix |
| T-03 | Replay or sequence rollback | Unique profile/device/sequence constraint and idempotent object ID | Replay/idempotency tests | Implemented | Clock-skew and bounded-retention abuse suite |
| T-04 | Safety auditor gains payload access | Oversight restricted to release artifacts and aggregate-free health | Role-isolation tests | Implemented | Independent authorization review |
| T-05 | PHI enters logs, push text, URLs or analytics | Opaque schema, fixed generic push, no analytics; Pydantic `extra="forbid"` blocks smuggled envelope fields | `tests/test_privacy_surface.py`: sentinel canaries across sync listings, release endpoints, health, error bodies, DEBUG log capture and captured push payloads; detector-honesty self-test included | Implemented (local evidence) | Privacy + security | No independent penetration test or deployed-configuration log-capture audit |
| T-06 | Prompt/document injection alters authority | Data/instruction separation, strict candidate schema, no arbitrary tools | Existing broker validation; planned adversarial corpus | Partial | Parser sandbox and injection fixture suite |
| T-07 | Model invents facts, treatment or urgency | Candidate-only schema, grounding checks, prohibited language, deterministic fallback | Broker tests | Partial | Task-specific qualification and provider-drift probes |
| T-08 | Stale or corrupted clinical release is used | Hash-pinned artifact, stable channel fails closed while unapproved | Artifact integrity tests | Partial | Signed manifest verification, expiry/revocation drill |
| T-09 | Device/profile key loss or recovery abuse | Local recovery wrapping; no server recovery key | Local tests only | Partial | Replacement-device recovery and coercion usability drill |
| T-10 | Backup is corrupt or unavailable | SQLite online backup API | Backup readability test | Partial | Encrypted-volume and live restore drill |
| T-11 | Reminder is mistaken for monitoring | Generic message and separated acceptance/display/ack states | Push policy tests | Partial | Browser/provider outage drill and UI comprehension test |
| T-12 | Denial of service or oversized request exhausts relay | Pydantic field limits and bounded listing | Structural limits | Partial | Reverse-proxy body/rate limits and load test |

## Security completion rule

Repository controls may move a threat to “implemented,” but the privacy/security release gate requires an independent assessment, remediation of material findings, verified incident response, and evidence from the deployed configuration. No internal model review substitutes for that evidence.
