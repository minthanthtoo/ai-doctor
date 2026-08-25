# AI Doctor OS v3 — Master goal status

Last evidence review: 2026-08-25 (R5 — release cut)  
Baseline: `f3ca423` (tag `v0.2.0-preclinical`)  
Overall state: **active; not clinically releasable**

## Release-gate ledger

| Gate | Status | Current evidence | Strongest counterevidence / limitation | Next evidence-producing action |
|---|---|---|---|---|
| Product-contract traceability | Conditional pass | [Traceability matrix](REQUIREMENTS_TRACEABILITY.md) maps the ten master gates to artifacts and tests | Several plan-level requirements have no implementation or external evidence | Keep the matrix current at every verified milestone |
| Production engineering | Fail | Runnable PWA, local encrypted ledger, SQLite relay, push and backup workers, Compose configuration; versioned per-store schema migrations | PostgreSQL, production identity, observability, accessibility audit, restore UI and failure-injection suite are incomplete | Close authorization isolation, then add production repository boundary and PostgreSQL |
| Deterministic clinical safety | Conditional pass | TypeScript kernel tests and Python triage regression tests; emergency lock is model-independent; 33-case never-event corpus with cross-runtime negation parity (CS-01) | Fixture set not independently clinically adjudicated | Independent clinical adjudication of the corpus |
| LLM containment | Conditional pass | Schema-bound broker, consent receipt, grounding and prohibited-language checks, disabled fallback; adversarial injection/containment suite (T-06/T-07) | No task-specific qualified model or provider-drift evaluation | Add signed qualification registry |
| Evidence and localization | Fail | Hash-pinned preclinical cardiometabolic pack with bilingual fields; Ed25519 manifest signing + fail-closed startup verification drills (`tests/test_release_signing.py`) | No named clinical or Burmese-language approval; evidence corpus is incomplete | Create provenance register and independent review package |
| Privacy and security | Fail | Local encryption, ciphertext-only relay schema, generic push text, device-signature verification, profile isolation and append-only record tests, automated sentinel privacy-surface audit (`tests/test_privacy_surface.py`), device roster with revocation (T-10), push-contract drills (T-09); structured access logs are JSON with whitelisted fields only and query strings excluded (`tests/test_observability.py`) | No independent penetration test, browser/device cryptographic review or full deployed log-capture audit; device-scoped read auth still credential-based | Complete threat-model controls; independent security assessment remains external |
| Clinical evaluation | Blocked | Thresholds and intended evaluation design are documented | No independently adjudicated Myanmar-relevant corpus or external holdout | Prepare corpus schema, adjudication protocol and reviewer package without real PHI |
| Human factors | Blocked | Bilingual interface exists; keyed my/en copy module with build-breaking parity tests (`apps/pwa/src/copy.ts`, `copy.test.ts`); axe-core sweep of the built PWA reports zero violations (`tests/test_a11y_axe.py`) | No representative comprehension/accessibility study; manual screen-reader pass not yet witnessed | Prepare protocol and instruments; execution requires approved participants/review |
| Operations | Fail | Compose (hardened: loopback-bound PWA port, relay internal-only, non-root + read-only containers), health endpoint, transactional SQLite backup, generic push worker; automated restore-fidelity, migration-replay and corruption-refusal drills (`tests/test_backup_drills.py`); request metrics endpoint (`/v1/operations/metrics`); profile data exit — full export and confirmed hard delete (`tests/test_data_exit.py`); GitHub Actions CI green on all three jobs; `scripts/cut_release.py` gate script used to cut `v0.2.0-preclinical` | No live private-host restore, outage, rollback or incident drill evidence | Add operator runbooks and witnessed drill |
| Governance and authorization | Blocked | Product boundary and promotion gates are documented | No named Myanmar clinical owner, language approver, legal determination or release signatures | Produce explicit external-review requests and signature artifacts |

Statuses mean: `pass`, `conditional pass`, `fail`, `not tested`, or `blocked`. A blocked external gate does not stop locally executable preparation.

## Active milestone

**Privacy/security: threat-model closure and automated privacy surface audit.**

Expected evidence:

- enumerate trust boundaries, assets, adversaries and abuse cases;
- link each threat to preventive/detective controls and executable evidence;
- automatically inspect relay schemas, API responses, logs and push payloads for plaintext PHI fixtures;
- preserve fail-closed behavior under tampering and cross-profile attempts.

## Decision record

Decision: bind each patient principal to one opaque profile on first successful profile-bearing request.  
Evidence: the v3 API previously accepted any syntactically valid `profile_pseudonym` from any patient token.  
Alternatives considered: configure profile IDs inside static token records; add a separate enrollment endpoint; defer to future OIDC.  
Why selected: first-use binding preserves the current single-user setup while closing cross-token access immediately and remains replaceable by OIDC subject binding.  
Confidence: high for the preclinical single-profile boundary.  
What would reverse it: a multi-profile or guardian delegation requirement.  
Downstream effects: sync, tombstones, push subscriptions/schedules and per-profile operational counts must enforce the same owner mapping.

Result: passed locally. Envelopes are now verified against enrolled P-256 device keys; invalid signatures and ciphertext hashes do not enroll a profile; credentials cannot rebind, read, tombstone or delete another profile; safety oversight cannot access encrypted payloads; per-profile counts do not leak to oversight. This is not an independent penetration-test result.

## Decision record — distribution status

Decision: personal-only distribution until external gates name accountable owners. No public listing, store submission, or unsolicited sharing; collaboration copies go only to named reviewers under the recruitment brief.
Evidence: GV-01/CE-01/HF-01 remain blocked with no external owners; MM-jurisdiction health data plus distribution capability without a legal entity creates asymmetric liability.
Alternatives considered: supervised clinical pilot (requires a named clinical owner — blocked); public demo build (rejected — real reliance risk without validated content).
Why selected: preserves honest release posture at zero engineering cost while reviewer outreach proceeds.
Confidence: high for the current preclinical state.
What would reverse it: a named Myanmar clinical owner and language approver signing on via `docs/REVIEWER_BRIEF.md`, enabling a supervised pilot path.
Downstream effects: PWA stays behind private relay auth; no public hosting of the built app until reversal conditions are met.

## External blockers

External clinical, Burmese-language, human-participant, legal and regulatory approvals cannot be generated by this repository. They remain required and must never be represented by model review.
