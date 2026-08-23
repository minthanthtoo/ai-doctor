# AI Doctor OS v3 — Master goal status

Last evidence review: 2026-08-12  
Baseline: `1cb4619`  
Overall state: **active; not clinically releasable**

## Release-gate ledger

| Gate | Status | Current evidence | Strongest counterevidence / limitation | Next evidence-producing action |
|---|---|---|---|---|
| Product-contract traceability | Conditional pass | [Traceability matrix](REQUIREMENTS_TRACEABILITY.md) maps the ten master gates to artifacts and tests | Several plan-level requirements have no implementation or external evidence | Keep the matrix current at every verified milestone |
| Production engineering | Fail | Runnable PWA, local encrypted ledger, SQLite relay, push and backup workers, Compose configuration | PostgreSQL, production identity, migrations, observability, accessibility audit, restore UI and failure-injection suite are incomplete | Close authorization isolation, then add production repository boundary and PostgreSQL |
| Deterministic clinical safety | Conditional pass | TypeScript kernel tests and Python triage regression tests; emergency lock is model-independent | Fixture set is small and not independently clinically adjudicated | Build locked synthetic never-event corpus and cross-runtime conformance harness |
| LLM containment | Conditional pass | Schema-bound broker, consent receipt, grounding and prohibited-language checks, disabled fallback | No task-specific qualified model or provider-drift evaluation | Add adversarial broker suite and signed qualification registry |
| Evidence and localization | Fail | Hash-pinned preclinical cardiometabolic pack with bilingual fields | No named clinical or Burmese-language approval; evidence corpus is incomplete | Create provenance register and independent review package |
| Privacy and security | Fail | Local encryption, ciphertext-only relay schema, generic push text, device-signature verification, profile isolation and append-only record tests, automated sentinel privacy-surface audit (`tests/test_privacy_surface.py`) | No independent penetration test, browser/device cryptographic review or full deployed log-capture audit | Complete threat-model controls; independent security assessment remains external |
| Clinical evaluation | Blocked | Thresholds and intended evaluation design are documented | No independently adjudicated Myanmar-relevant corpus or external holdout | Prepare corpus schema, adjudication protocol and reviewer package without real PHI |
| Human factors | Blocked | Bilingual interface exists | No representative comprehension/accessibility study | Prepare protocol and instruments; execution requires approved participants/review |
| Operations | Fail | Compose, health endpoint, transactional SQLite backup, generic push worker | No live private-host restore, outage, rollback or incident drill evidence | Add automated failure-injection and operator runbooks, then perform witnessed drill |
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

## External blockers

External clinical, Burmese-language, human-participant, legal and regulatory approvals cannot be generated by this repository. They remain required and must never be represented by model review.
