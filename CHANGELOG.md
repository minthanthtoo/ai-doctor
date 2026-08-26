# Changelog

All notable changes to AI Doctor OS v3 (personal health steward).
Format based on Keep a Changelog; versions follow semver with a
preclinical suffix. **This software is not clinically approved.**

## [0.2.0-preclinical] — 2026-08-25

Tagged `v0.2.0-preclinical` @ `f3ca423`. Manifest
`release_manifest_v3.json` carries `"signature": null` until a human signs
it (`scripts/sign_release_manifest.py`); unsigned-by-default.

### Added

**Safety**
- 33-case never-event corpus (CS-01) driving NegEx-lite negation scope in
  both runtimes; cross-runtime parity pinned by test. Ambiguous input stays
  fail-closed (locks).
- Adversarial injection/containment suite (T-06/T-07) around the schema-bound
  model broker.

**Longitudinal sync & devices**
- Device roster with revocation (T-10): `/v1/devices` list + DELETE;
  unknown devices enroll on first write, known-and-revoked are blocked.
- Two-device sync round-trip drill incl. tombstones (T-11).
- Property-based envelope signature fuzz (3 properties × 40 hostile examples).

**Push (T-09)**
- Push-contract drills: wire payload pinned to generic text only (no PHI),
  VAPID-disabled refusal, provider-rejection resilience, claim/deliver/
  reschedule lifecycle.
- Manual device checklist (`docs/PUSH_MANUAL_CHECKLIST.md`).

**Resilience**
- Backup restore-fidelity, migration-replay and corruption-refusal drills
  (`tests/test_backup_drills.py`).

**Data exit & observability**
- `/v1/profile/export` full export and confirmed hard delete (16-char
  confirm; foreign-profile requests → 403) (`tests/test_data_exit.py`).
- Structured JSON access logs — whitelisted fields only, query strings
  excluded, sentinel-proven PHI-free (`tests/test_observability.py`).
- `/v1/operations/metrics` request counters.

**Storage seam**
- `CaseStoreProtocol` + fail-closed Postgres skeleton; SQLite stays default.

**PWA**
- Keyed my/en copy module with build-breaking locale parity tests.
- axe-core sweep of the built app: zero violations (muted ink raised to
  5.2:1 contrast).
- Committed performance budgets (`apps/pwa/budget.json`) enforced by drill:
  JS ≤ 400 KB raw, total ≤ 750 KB.

**Release engineering**
- GitHub Actions CI (python / kernel+PWA / a11y+budget jobs), green.
- `scripts/cut_release.py`: test-gated release cutter writing the v3
  manifest and annotated tags.
- Hardened compose: PWA port loopback-bound, relay internal-only (no host
  publish), non-root + read-only containers.

### Fixed

- Pydantic v2+ echoed client payloads back in 422 error bodies (CI-caught);
  responses now carry field locations only — submitted content never
  reflected.

### Security notes

- Relay stores ciphertext only; device signatures verified per envelope.
- Read auth remains credential-based; device-scoped read blocking is future
  work (NOTE-pinned in the T-10 drill).

## [0.1.0] — earlier preclinical baseline

See `docs/IMPLEMENTATION_STATUS.md` and `git log v0-preclinical-baseline`.
