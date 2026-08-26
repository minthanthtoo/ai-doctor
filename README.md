# AI Doctor OS v3 — Preclinical Personal Health Steward

![Safety status view](docs/img/safety-status.png)

**Personal Health Steward** is a local-first, bilingual (မြန်မာ/English) personal health record PWA with deterministic safety screening. It is **preclinical**: not a licensed medical service, with no validated clinical claim.

- **Does:** encrypted offline record · red-flag emergency lock (model-independent) · guided intake · possibility maps · encrypted sync to your own relay.
- **Refuses:** diagnosis as fact, prescribing, orders, dispatch, autonomous advice — by construction, not policy.
- **Proven:** 167 executable tests (121 Python incl. privacy-surface audit, backup/corruption drills, data-exit drills · 39 kernel incl. 33-case never-event corpus · 7 PWA locale-parity) + zero-violation axe sweep + green CI on every push. **Unproven:** clinical performance, comprehension studies, regulatory authorization — blocked pending external owners.

One-page boundary: [docs/BOUNDARY_ONE_PAGER.md](docs/BOUNDARY_ONE_PAGER.md) · Screenshots: [onboarding](docs/img/onboarding.png) · [recovery kit](docs/img/recovery-kit.png) · [concern intake](docs/img/concern-intake.png)

## Releases

Current: **`v0.2.0-preclinical`** (see [CHANGELOG.md](CHANGELOG.md)). Cut with `scripts/cut_release.py` (runs the test gates, writes the v3 manifest with `"signature": null`, tags). CI runs the Python suite, kernel+PWA suites, and the a11y/perf-budget drills on every push.

## Custody

Source is mirrored to two remotes — `github` (private github.com/minthanthtoo/ai-doctor) and `offsite` (bare mirror on an external volume). Push **both** after every change: `git push github main && git push offsite main`.

The repository now includes a working local-first personal longitudinal health steward alongside the preserved clinician-supervised v0 reference API. The v3 PWA stores an encrypted append-only record on the phone, performs deterministic safety preflight, manages guided workups and user-owned reminders, and can sync only encrypted envelopes to a private home relay.

Start with [Personal Steward v3](docs/PERSONAL_STEWARD_V3.md) for the implemented architecture, local/home-server setup, and exact safety boundary. The older clinician-supervised capability path remains documented below for development compatibility.

Long-horizon completion evidence is tracked in [Master goal status](docs/MASTER_GOAL_STATUS.md), with the requirement mapping in [Requirements traceability](docs/REQUIREMENTS_TRACEABILITY.md) and active security findings in [Threat model](docs/security/THREAT_MODEL.md).

An executable, clinician-supervised implementation of four clinical capability families:

- deterministic emergency red-flag triage;
- bounded, non-authoritative diagnostic differential support;
- signed-protocol prescription drafting;
- patient advice rendered from emergency rules or clinician-approved structured decisions.

This repository is **preclinical software**. It is not a licensed medical service, has no validated clinical-performance claim, cannot execute or transmit a prescription, and must not be used as a substitute for emergency services or a qualified clinician.

The safety and product architecture is documented in [AI Doctor OS — Blueprint v2](docs/AI_DOCTOR_OS_BLUEPRINT_V2.md).

## What is implemented

```text
patient snapshot
→ deterministic emergency triage
→ capability/role/population safety gate
→ bounded diagnosis-support patterns
→ clinician review or amendment
→ signed protocol prescription draft
→ prescriber approval while executable=false
→ clinician-authored or approved-prescription patient advice
→ case versions + transactional audit outbox + hash-chain verification
```

Important behavior:

- Emergency escalation preempts diagnosis and prescribing.
- Missing data produces `insufficient_data` or a blocked capability, not reassurance.
- Patients cannot request diagnostic or prescription outputs.
- A prescription is created only from an approved protocol whose detached Ed25519 signature verifies.
- Drafting always requires a clinician-confirmed snapshot, age, known pregnancy status, reconciled allergy and medication lists, and a clinician-verified indication bound into the signed protocol.
- A prescription draft remains `executable=false` even after clinician approval.
- Non-emergency advice is either a bounded clinician-authored care plan or fixed rendering of reviewed structured content.
- Amendments create successor snapshots and re-run triage/diagnosis.
- Every clinical mutation creates a new decision ID; stale concurrent writes are rejected rather than overwriting newer emergency state.
- Case access is deny-by-default; safety oversight is globally read-only; decision versions and audit events are append-only.
- Executed triage and diagnosis rule artifacts are SHA-256 pinned to their capability releases and checked at startup.
- An optional model gateway can add clinician-review hypotheses only. It is off by default and cannot alter triage, prescribing, or patient advice.

The bundled protocol registry is intentionally empty. A clinical governance process must supply appropriately licensed, reviewed, signed, and validated protocol content.

See [Prescribing protocol releases](docs/PRESCRIBING_PROTOCOLS.md) for the Ed25519 signing and key-rotation procedure.

## Run locally

Python 3.9+ is supported.

> Verified runner on this machine: `/Users/min/miniforge3/bin/python -m pytest -q`
> (the checked-in `.venv/` is an empty shell; recreate with `uv venv && uv sync --extra test`).

```bash
uv sync --extra test
uv run uvicorn ai_doctor.main:app --host 127.0.0.1 --port 8080
```

Open `http://127.0.0.1:8080/docs` for the generated API interface.

Preclinical mode exposes demonstration bearer credentials:

| Role | Token |
|---|---|
| Physician | `preclinical-physician-token` |
| Pharmacist | `preclinical-pharmacist-token` |
| Patient | `preclinical-patient-token` |
| Clinical safety officer | `preclinical-safety-token` |

The application refuses these credentials in `AI_DOCTOR_ENV=production`.

### Create a clinician case

```bash
curl -X POST http://127.0.0.1:8080/v1/cases \
  -H 'Authorization: Bearer preclinical-physician-token' \
  -H 'Content-Type: application/json' \
  -d @examples/routine_case.json
```

### Run verification

```bash
uv run pytest -q
```

### Release a reviewed general advice plan

An authorized physician or nurse can attach structured patient instructions while acknowledging a case:

```bash
curl -X POST http://127.0.0.1:8080/v1/cases/CASE_ID/review \
  -H 'Authorization: Bearer preclinical-physician-token' \
  -H 'Content-Type: application/json' \
  -d '{
    "disposition": "acknowledge",
    "rationale": "Reviewed against the source encounter",
    "advice_plan": {
      "summary": "Follow the reviewed care plan.",
      "actions": ["Follow the clinician-documented next step."],
      "warning_signs": ["Seek reassessment if symptoms become severe."],
      "follow_up": ["Attend the scheduled follow-up."]
    }
  }'
```

The renderer copies those bounded fields verbatim after recording the reviewer; it does not ask a model to expand them.

## API surface

| Endpoint | Purpose |
|---|---|
| `POST /v1/cases` | Run triage and permitted diagnostic support |
| `GET /v1/cases/{case_id}` | Retrieve the current sourced snapshot and decision |
| `GET /v1/cases/{case_id}/versions` | Retrieve immutable successor versions |
| `POST /v1/cases/{case_id}/prescription-drafts` | Evaluate an approved signed prescribing protocol |
| `POST /v1/cases/{case_id}/review` | Acknowledge, reject, defer, amend, or approve a draft |
| `GET /v1/cases/{case_id}/advice` | Retrieve permitted patient-facing advice |
| `POST /v1/cases/{case_id}/access` | Grant case-scoped access |
| `GET /v1/cases/{case_id}/audit` | Retrieve the decision audit trail |
| `GET /v1/cases/{case_id}/audit/verify` | Verify event ordering and hash integrity |
| `GET /v1/capabilities` | Inspect released capability versions |

## Configuration

| Variable | Meaning |
|---|---|
| `AI_DOCTOR_ENV` | `preclinical` by default; production disables demo credentials |
| `AI_DOCTOR_DATABASE` | SQLite path for the preclinical repository |
| `AI_DOCTOR_TOKENS_JSON` | Bearer-token records for preclinical integration testing |
| `AI_DOCTOR_PROTOCOL_PATH` | JSON file containing controlled prescribing protocols |
| `AI_DOCTOR_PROTOCOL_PUBLIC_KEYS_JSON` | Map of Ed25519 key IDs to base64 public keys |
| `AI_DOCTOR_ALLOW_TEST_PROTOCOLS` | Allows explicit test fixtures only in preclinical mode |
| `AI_DOCTOR_MODEL_GATEWAY_ENABLED` | Opt in to model augmentation; `false` by default |
| `AI_DOCTOR_MODEL_GATEWAY_ENDPOINT` | OpenAI-compatible chat-completions endpoint; HTTPS except preclinical localhost |
| `AI_DOCTOR_MODEL_GATEWAY_MODEL` | Explicit deployed model identifier |
| `AI_DOCTOR_MODEL_GATEWAY_API_KEY` | Optional gateway bearer secret |
| `AI_DOCTOR_MODEL_GATEWAY_TIMEOUT_SECONDS` | Bounded to 1–60 seconds |
| `AI_DOCTOR_MODEL_GATEWAY_RELEASE` | Immutable local release label recorded on augmented output |
| `AI_DOCTOR_RELEASE_MANIFEST_PATH` | Optional override for the served release manifest location |
| `AI_DOCTOR_RELEASE_MANIFEST_PUBLIC_KEYS_JSON` | Map of Ed25519 key IDs to base64 public keys trusted for manifest signatures |
| `AI_DOCTOR_REQUIRE_SIGNED_MANIFEST` | `true` refuses startup unless the release manifest carries a valid approved signature |
| `AI_DOCTOR_MODEL_GATEWAY_ALLOWED_HOSTS` | Comma-separated egress allowlist; required outside preclinical mode |

The gateway omits direct patient and encounter references, arbitrary symptom attributes, and source metadata. The remaining clinical facts may still contain sensitive health information. Enable it only for an organization-approved endpoint with the necessary privacy, security, consent, contracting, and data-residency controls.

Production deployment requires organization-managed OIDC/SMART authentication, a production database and independently controlled audit sink, licensed drug knowledge, quality-system controls, clinical validation, jurisdiction-specific regulatory assessment, and site deployment assurance. The local tokens and SQLite storage are reference implementations, not production controls.

## Source layout

```text
src/ai_doctor/
├── api.py                         FastAPI transport and access checks
├── orchestrator.py                bounded clinical workflow
├── domain/models.py               typed clinical and decision objects
├── models/gateway.py              optional untrusted diagnosis augmentation
├── capabilities/
│   ├── triage.py                  deterministic emergency rules
│   ├── diagnosis.py               bounded syndromic differential
│   ├── prescribing.py             signed-protocol drafting
│   └── advice.py                  fixed reviewed rendering
├── safety/
│   ├── registry.py                versioned capability envelopes
│   └── policy.py                  fail-closed policy gate
└── storage/sqlite.py              case versions and audit reference store
```

The detailed architecture and phased assurance plan are in [AI Doctor OS — Blueprint v2](docs/AI_DOCTOR_OS_BLUEPRINT_V2.md). The exact code-to-capability mapping and remaining release gates are in [Implementation status and release boundary](docs/IMPLEMENTATION_STATUS.md). The code implements the preclinical reference workflow, not the validation evidence required to operate a medical device or licensed clinical service.

## Deliberately prohibited

- Autonomous diagnosis communicated as fact.
- Autonomous prescription signing, order placement, or pharmacy transmission.
- Public-web medical retrieval during a case.
- Live self-training from patient outcomes.
- Patient-facing non-emergency treatment advice without clinical review.
- Suppressing deterministic emergency escalation because another model disagrees.
