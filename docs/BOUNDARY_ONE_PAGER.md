# AI Doctor OS — Capability Boundary (One Page)

**Status:** preclinical engineering vertical slice · **Jurisdiction:** MM · **Languages:** my/en
**Release:** personal-steward-v3-preclinical.1 · manifest digest-pinned, signature support implemented (unsigned by default)

## What it does today

- Offline-capable bilingual (Burmese/English) React PWA storing an AES-256-GCM encrypted, append-only local record; non-extractable device key with offline recovery kit.
- Deterministic adult/non-pregnancy safety preflight: red-flag screening and emergency lock that no model can override.
- Guided concern intake, measurements, medication inventory, documents, timeline, tasks, evidence views.
- Structured possibility maps from a hash-pinned cardiometabolic pack (`approved_for_clinical_use=false`).
- Encrypted, P-256-signed sync envelopes to an opaque relay; generic-text push reminders; transactional SQLite backup worker; home-server Compose deployment.
- Automated privacy-surface audit (`tests/test_privacy_surface.py`) and signed-manifest verification drills (`tests/test_release_signing.py`) in the executable evidence base.

## What it refuses

- No diagnosis as fact, treatment selection, medication changes, prescribing, refills, orders, pharmacy transport, emergency dispatch, or clinician monitoring.
- No model may alter urgency, create facts, or emit instructions; the model path is disabled by default and candidate-only when enabled.
- No public-web clinical retrieval during a case; no self-training on user data.
- Stable release channel stays closed while `approved_for_clinical_use=false`.

## What is proven (executable evidence)

- 77 Python tests green: deterministic triage/diagnosis regressions, envelope signature/replay/tamper isolation, privacy-surface sentinel audit across responses/logs/push payloads, signing roundtrip + tamper/wrong-key/rotation-revocation drills, backup integrity.
- 9 frontend/kernel tests green; typecheck and production build clean; icons + webmanifest install-eligible.

## What is NOT proven

- Clinical performance (CE-01), human comprehension ≥90% (HF-01), and governance authorization (GV-01) are **blocked pending external owners** — no internal test can substitute.
- No independent penetration test, browser-crypto review, or deployed-configuration log audit has occurred.
- Burmese clinical content awaits a named language reviewer; the interface is bilingual but clinical approval status is "required."

## Who it's for right now

Personal-only use by the project owner until external gates name accountable owners. See the distribution decision record in `docs/MASTER_GOAL_STATUS.md` and the recruitment brief in `docs/REVIEWER_BRIEF.md`.
