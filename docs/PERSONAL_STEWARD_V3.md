# Personal Longitudinal Health Steward v3

## Implemented release boundary

This repository now contains an executable preclinical vertical slice of the personal steward. It is a local-first personal health organizer and research system, not a licensed medical service or an autonomous doctor.

Implemented:

- installable React/TypeScript PWA with an offline application shell;
- device-local AES-256-GCM encrypted append-only events and attachments;
- non-extractable browser wrapper key, optional passkey presence, and an offline recovery kit;
- deterministic adult/non-pregnancy safety preflight and emergency lock;
- guided concern intake, measurements, medication inventory, documents, timeline, tasks, evidence, consent, and privacy views;
- structured possibility maps restricted to the preclinical cardiometabolic pack;
- encrypted, signed, idempotent backup/sync envelopes;
- generic Web Push scheduling with delivery states kept separate from display and acknowledgement;
- a stateless, consent-bound model broker with strict schemas and a deterministic disabled fallback;
- signed/hash-pinned release artifacts and capability states;
- a private home-server Compose deployment.

Not implemented or enabled:

- confirmed diagnoses, treatment selection, medication changes, prescribing, refills, orders, pharmacy transport, emergency dispatch, or clinician monitoring;
- production-approved Myanmar rules or Burmese clinical-language releases;
- medical-image analysis, live-web clinical retrieval, autonomous learning, or an unbounded agent;
- multi-device clinical merge (replacement-device restore is the v1 boundary);
- clinical qualification or regulatory approval.

The bundled pack is intentionally marked `approved_for_clinical_use=false`. The stable release endpoint fails closed until clinical and Burmese-language review are complete.

## Runtime structure

```text
apps/pwa
  encrypted record + UI + offline safety kernel + generic push client
packages/clinical-kernel
  deterministic TypeScript rules, quality checks, state transitions, rendering
src/ai_doctor
  opaque relay + release service + bounded model broker + push/backup workers
```

The personal deployment exposes patient and safety-auditor credentials only. Existing clinician-supervised prescribing scaffolds remain development-only and are not reachable with those roles.

## Local development

```bash
npm install
npm run dev
python -m uvicorn ai_doctor.main:app --host 127.0.0.1 --port 8080
```

Set `VITE_RELAY_URL` and `VITE_RELAY_TOKEN` in `apps/pwa/.env.local` when testing sync. Never embed a production bearer token in a public PWA build; the static token is a local preclinical integration mechanism only.

Verification:

```bash
npm run typecheck
npm run test:frontend
npm run build
python -m pytest -q
python -m ruff check src tests
```

## Home server

1. Copy `deployment/.env.example` to a private operator environment and replace every demonstration token.
2. Keep the server behind WireGuard or Tailscale. Do not expose clinical endpoints directly to the public internet.
3. Configure a trusted certificate for the phone. Caddy's internal CA is suitable only after explicitly trusting that CA on the device.
4. Start with `docker compose -f deployment/docker-compose.yml up --build -d`.
5. Verify `/v1/operations/health`, create a recovery kit, perform an encrypted sync, and complete a restore drill before relying on backup.

The reference relay currently uses SQLite to preserve compatibility with the preclinical code and provide a runnable single-user deployment. PostgreSQL, independently controlled audit storage, organization-managed identity, secret rotation, monitoring, and tested disaster recovery remain production-promotion requirements.

The backup worker uses SQLite's online backup API, not a raw copy of a live database. Backup files still contain relay ciphertext and sensitive metadata, so the backup volume itself must be encrypted and access-controlled.

## Generic Web Push

Generate a VAPID key pair using an approved operator tool, then configure:

```text
AI_DOCTOR_PUSH_ENABLED=true
AI_DOCTOR_PUSH_VAPID_PUBLIC_KEY=...
AI_DOCTOR_PUSH_VAPID_PRIVATE_KEY=...
AI_DOCTOR_PUSH_VAPID_SUBJECT=mailto:operator@example.com
```

Only the fixed text “You have a health reminder.” is sent. Provider acceptance does not mean the message was displayed, read, acknowledged, or acted on. Offline or missed check-ins never imply stability.

## Model use

Model egress is disabled by default. Enabling it requires a qualified task/model pair, an allowlisted HTTPS endpoint, a fresh per-workup consent receipt, provider/privacy review, and synthetic-case qualification. The model receives only allowlisted facts and evidence excerpts tied to a snapshot hash. It cannot change urgency, create facts or alerts, call tools, or produce medication/treatment instructions. Failure returns the deterministic experience.

## Promotion gates

Clinical visibility remains blocked until the repository has a named Myanmar clinical owner and Burmese-language reviewer, signed and independently reviewed content, locked external evaluation, bilingual human-factors testing, security/privacy assessment, stop thresholds, rollback drills, and the applicable legal and regulatory approvals.
