# AI Doctor OS — Master Plan: Preclinical Vertical Slice → Production-Grade Product

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Take ai-doctor from its current verified preclinical state (77 tests green, signed manifests, privacy audit, custody in place) to a production-grade personal health product: hardened multi-device sync, real push delivery, production data layer, observability, accessibility, and a supervised-pilot release posture — while keeping every safety invariant that defines the project.

**Architecture:** The repo already holds two generations (v0 clinician-supervised CDS API; v3 local-first steward). This plan hardens v3's full stack: React PWA (Dexie/AES-GCM vault) → opaque relay (FastAPI + SQLite) → push/backup workers → Compose deployment. Every phase ends with the full gate matrix green and the governance ledger updated; nothing claims clinical validity — the target grade is "production-grade *preclinical* software," the ceiling the project's own gates permit without external clinical owners.

**Tech Stack:** Python 3.11 (FastAPI, SQLAlchemy-free raw SQLite, cryptography Ed25519/P-256), TypeScript/React 19 + Vite + Dexie + vite-plugin-pwa, Docker Compose, pytest/ruff/vitest/tsc. Runner: `/Users/min/miniforge3/bin/python`.

---

## Current context / assumptions (verified 2026-08-23)

- Baseline `0174dee`: 77 Python + 9 frontend/kernel tests, ruff/tsc/build green, tree clean.
- Custody: offsite bare mirror on SANDISK128 synced; **GitHub arm pending user action** (add SSH key at github.com/settings/keys + create private `ai-doctor` repo — exact key value is in chat history).
- Governance docs are live and honest: MASTER_GOAL_STATUS.md ledger (10 gates), REQUIREMENTS_TRACEABILITY.md, THREAT_MODEL.md (T-01…T-12), BOUNDARY_ONE_PAGER.md, REVIEWER_BRIEF.md.
- Known gaps from the ledger itself: no migrations, no production DB boundary, no observability, no CI, no accessibility audit, single-device assumption, push never delivered end-to-end, backup restore untested against corruption, model-broker adversarial suite missing (T-06/T-07 partial).

## Guiding invariants (violating any = plan failure)

1. Emergency lock stays deterministic, model-independent, first-evaluated.
2. Relay stays opaque: no plaintext PHI on any server-controlled surface (T-05 audit must keep passing).
3. Fail-closed everywhere: unsigned/invalid manifest refuses boot; unknown states refuse rather than guess.
4. Append-only longitudinal record; no destructive migrations of existing user data.
5. Honest docs: every claim maps to a test or an explicitly blocked external owner.

---

# PHASE R0 — Custody completion (prerequisite, ~15 min)

### Task R0.1: GitHub remote once user adds SSH key
- Verify: `ssh -T git@github.com -o BatchMode=yes` → expect "Hi minthanthtoo"
- `git remote add github git@github.com:minthanthtoo/ai-doctor.git`
- `git push -u github main` → verify `git ls-remote github refs/heads/main` SHA == local HEAD
- Keep SANDISK mirror as second remote (`git push offsite main` after every push)
- Update README "Custody" line to name both remotes

---

# PHASE R1 — Correctness hardening (~1 day)

### Task R1.1: Schema migration framework (RED→GREEN)
- Create `src/ai_doctor/storage/migrations.py` + `tests/test_migrations.py`
- Design: `MIGRATIONS: list[tuple[int, Callable[[sqlite3.Connection], None]]]`; `_apply_migrations(conn)` records `(version, applied_at_utc)` in `schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT)`; wrap each in a transaction; refuse downgrade (version > code ⇒ RuntimeError)
- Test: fresh DB reaches latest; re-open is idempotent (no double-apply); tampered future version raises
- Refactor `storage/sqlite.py` init path to call it (6 CREATE TABLEs become migration 1); existing DBs detect version 0 → stamp 1 without altering tables (backward-compat test: open legacy fixture DB, assert row counts intact)
- Commit `feat(storage): versioned schema migrations`

### Task R1.2: Adversarial broker suite (closes T-06/T-07 test gap)
- Extend `tests/test_model_gateway.py` (or new `tests/test_broker_adversarial.py`)
- Cases: instruction-in-document ("ignore previous instructions…") treated as inert text; prompt-leak attempts via concern text cannot change candidate schema; prohibited-language filter rejects imperative advice ("take aspirin", "you have X"); urgency fields immutable by gateway output; grounding check rejects uncoded entities; consent receipt absent ⇒ broker.run raises before egress
- Each case = one test; all fail-closed assertions
- Commit `test(broker): adversarial injection and containment suite`
- Ledger: T-06/T-07 evidence column gains suite name; status Partial→Implemented (local evidence)

### Task R1.3: Never-event corpus harness (kernel conformance)
- New `tests/test_never_events.py` + fixture `tests/fixtures/never_events.json` (≥25 synthetic cases: classic red flags → MUST emergency-lock; benign variants → MUST NOT)
- Kernel cases run through TS via existing vitest bridge if present, else Python triage mirror asserts parity with documented mapping
- Any miss = fix pack/kernel, not the assertion
- Commit `test(safety): synthetic never-event corpus (25 cases)`
- Ledger CS-01 evidence updated

### Task R1.4: Property-based fuzz for crypto/envelope paths
- Add `hypothesis` dev-dep; `tests/test_envelope_fuzz.py`: random byte mutations of valid envelopes never crash the app (always 4xx), signature verification monotone (any bit flip ⇒ reject), base64url roundtrip property
- Commit `test(crypto): property-based envelope mutation resistance`

### Task R1.5: Full gate + docs
- Matrix: pytest · ruff · typecheck · vitest · build
- Ledger baseline bump commit `docs: advance ledger after correctness hardening`

---

# PHASE R2 — Multi-device & real delivery (~1–2 days)

### Task R2.1: Device roster & rotation (RED→GREEN)
- `domain/longitudinal.py`: add `DeviceRecord(device_id, profile_id, pub_jwk, label, enrolled_at, revoked_at|None)`
- Relay routes: GET `/v1/devices` (own only), POST `/v1/devices/revoke` (body device_id; sets revoked_at; subsequent envelopes from it rejected 409)
- Tests: enroll second device, revoke it, old-key envelope now rejected; owner sees own devices only
- PWA: Settings screen lists devices + revoke button (calls new endpoints)
- Commit `feat(sync): device roster and revocation`

### Task R2.2: Cross-device E2E sync drill
- Integration test spinning TWO TestClients sharing one relay DB: device A enrolls + PUTs envelope; device B enrolls different key, GETs listing, fetches ciphertext, verifies signature with A's JWK, decrypts locally
- Asserts cross-token isolation still holds (B cannot read A's other profiles)
- Commit `test(sync): two-device end-to-end drill`

### Task R2.3: Real Web Push delivery drill
- Requires VAPID keys: generate once into `.zsh_secrets` as `AI_DOCTOR_VAPID_PUBLIC/PRIVATE` (never committed); document in `.env.example`
- `tests/test_push_live.py` marked `@pytest.mark.live` (skipped unless env present): schedule reminder → worker delivers to real endpoint stub? NO — instead use pywebpush against a local HTTP catcher (aiohttp test server acting as push service) asserting: correct TTL/urgency headers, payload is exactly the generic constant, endpoint errors mark attempt failed and back off
- Manual checklist doc `docs/PUSH_DELIVERY_CHECKLIST.md` for the one thing automation can't do (browser notification permission UX) with screenshots
- Commit `feat(push): delivery drill + operator checklist`

### Task R2.4: Backup restore drill incl. corruption
- Extend backup tests: restore to NEW db file; row counts + audit-chain head match; corrupt Nth byte → restore refuses with explicit error; restore into running app boots and serves same digest
- Commit `test(backup): restore and corruption-refusal drills`
- Ledger T-10 Partial→Implemented

---

# PHASE R3 — Production data layer (~1–2 days)

### Task R3.1: PostgreSQL boundary behind repository protocol
- Define `RelayRepository` Protocol in `storage/repository.py` matching today's OpaqueRelayRepository surface
- Concrete `SqliteRelayRepository` (rename, zero logic change) + `PostgresRelayRepository` skeleton implementing envelope put/get/list with identical semantics; asyncpg dep optional-extra `[postgres]`
- Selection by env `AI_DOCTOR_DB_BACKEND=sqlite|postgres`; default sqlite; compose gains commented postgres profile
- Tests: contract test suite parametrized over both backends (postgres tests skip cleanly without DSN)
- Commit `feat(storage): repository protocol + postgres backend skeleton`
- Explicitly OUT OF SCOPE (YAGNI): ORM adoption, multi-region, connection pooling tuning

### Task R3.2: Retention & export APIs
- GET `/v1/export` → streaming JSONL of owner's envelopes+metadata (their right to exit; ciphertext only, keys stay client-side)
- DELETE `/v1/profiles/me` → tombstone + purge path consistent with append-only design (tombstone visible, payloads dropped after grace window setting)
- Tests: export shape, delete then list-empty, isolation (cannot export others)
- Commit `feat(relay): data export and account deletion`
- Ledger GV column note: supports MM PDPL-style expectations

### Task R3.3: Observability floor
- structured JSON logging via logging config (request id, route, latency, status; NEVER bodies — T-05 audit re-run proves it)
- `/v1/operations/metrics` (auth'd): counters per route, push attempts/failures, backup age
- Compose: optional Prometheus scrape comment block (YAGNI: no Grafana stack)
- Commit `feat(ops): structured logs and metrics endpoint`
- Re-run privacy audit as part of task (log lines are a scanned surface)

---

# PHASE R4 — Accessibility & i18n depth (~1 day)

### Task R4.1: axe-core accessibility sweep
- Dev-dep `vitest-axe` (or jest-axe equivalent for vitest): render App views (onboarding, intake, timeline, settings), assert zero serious/critical violations
- Fix what surfaces (likely: contrast on cream bg, button names in Burmese-only labels, focus order)
- Manual keyboard-nav checklist appended to PUSH_DELIVERY_CHECKLIST-style ops doc
- Commit `feat(pwa): accessibility fixes from axe sweep`

### Task R4.2: Locale infrastructure (real my/en split)
- Extract UI strings to `apps/pwa/src/i18n/{my,en}.ts` keyed dictionaries; App reads `mg_locale` localStorage
- All existing bilingual inline strings migrate; parity test: every key exists in both locales (fails CI on drift)
- Burmese strings remain flagged "machine-assisted pending LO-01 reviewer" in code comments — honesty preserved
- Commit `refactor(pwa): keyed i18n with parity enforcement`

### Task R4.3: Lighthouse budget gate
- Script `scripts/lighthouse_budget.mjs` run against `vite preview` build: performance ≥90, accessibility ≥95, best-practices ≥90; fails build otherwise
- Wire as npm script `check:lighthouse` (documented; not yet CI)
- Commit `chore(pwa): lighthouse budget script`

---

# PHASE R5 — Release engineering (~½ day)

### Task R5.1: CI pipeline (GitHub Actions)
- `.github/workflows/ci.yml`: matrix python 3.11/3.12 → ruff+pytest; node 20 → typecheck+vitest+build
- Cache pip/npm; concurrency-cancel; badge in README
- First green run = evidence link recorded in ledger
- Commit `ci: full matrix pipeline`

### Task R5.2: Release tooling
- `scripts/cut_release.py`: runs full matrix, bumps version, regenerates manifest artifact digests, invokes sign_release_manifest.py with env key, writes CHANGELOG entry from commits
- Tags `v0.x.y-preclinical`; signed manifest committed alongside tag
- Commit `chore(release): cut_release script + changelog`

### Task R5.3: Deployment hardening
- Compose: healthchecks for relay/push-worker/backup; resource limits; restart policies; UGW: bind relay to `127.0.0.1:8080` inside a `relay` network, PWA nginx proxies internally (implements DA council finding #2 — public-interface foot-gun removed by construction)
- `docs/DEPLOYMENT.md` rewrite: VPN-only posture, token rotation procedure, restore procedure, signed-manifest enforcement steps
- Commit `feat(deploy): hardened compose + deployment guide`

### Task R5.4: Final ledger reconciliation
- All rows updated with new evidence links; baseline bump; BOUNDARY_ONE_PAGER numbers refreshed (test counts, new refusals if any)
- Tag `v0.2.0-preclinical` + signed manifest; push both remotes

---

# Files likely to change (summary)

- New: `storage/migrations.py`, `storage/repository.py`, `tests/test_migrations.py`, `tests/test_broker_adversarial.py`, `tests/test_never_events.py`, `tests/fixtures/never_events.json`, `tests/test_envelope_fuzz.py`, `tests/test_push_live.py`, `docs/PUSH_DELIVERY_CHECKLIST.md`, `docs/DEPLOYMENT.md`, `.github/workflows/ci.yml`, `scripts/cut_release.py`, `scripts/lighthouse_budget.mjs`, `apps/pwa/src/i18n/{my,en}.ts`, `apps/pwa/src/DeviceSettings.tsx`
- Modified: `settings.py` (backend/env knobs), `relay.py` (device routes, export/delete), `push_worker.py` (live drill hooks), `backup.py` (restore API), `storage/sqlite.py` (migration wiring), `apps/pwa/vite.config.ts`, `README.md`, all four governance docs

# Tests / validation (every phase)

Full matrix: `/Users/min/miniforge3/bin/python -m pytest -q` (target ≥100 tests by R5) · `ruff check src tests` · `npm run typecheck && npm run test:frontend && npm run build` · privacy-surface audit must stay green after ANY relay/push/log change · offsite push after every phase.

# Risks, tradeoffs, open questions

1. **PostgreSQL scope creep** — mitigated: contract-suite skeleton only, sqlite default; revisit only when a second relay node exists (likely never for personal scale).
2. **Live-push testing needs real browser** — automated part covers provider-contract; human checklist covers UX; do not fake the latter.
3. **i18n extraction churn** — mechanical but large diff; do it as its own commit; parity test prevents regression forever after.
4. **Never-event corpus could expose kernel gaps** — that is its purpose; fixes go to pack/kernel with tests, never by weakening assertions.
5. **CI on GitHub requires Phase R0 done** — if user delays SSH key, CI lands as committed-but-unrun; ledger notes it honestly.
6. **Clinical ceiling unchanged** — CE-01/HF-01/GV-01 stay blocked pending external owners; REVIEWER_BRIEF.md remains the unlock path; no amount of engineering substitutes.
7. **Open question:** does the user want pilot-user onboarding docs (install-on-phone walkthrough) in R5, or is personal-use sufficient for this cycle?

# Execution order & dependencies

R0 → R1 → R2 → R3 → R4 → R5 strictly (R3.1 depends on R1.1 migrations; R5.1 depends on R0; R4 independent of R3 except final reconciliation). Estimated total: 5–7 focused working days.
