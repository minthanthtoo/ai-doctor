# Privacy-Surface Audit + Signed Manifest Verification Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Commit the Aug-12+ working-tree changes, then close the two "Partial" security threats the project's own ledger names as the active milestone — T-05 (automated privacy-surface audit) and T-08 (signed manifest verification + tamper/revocation drill).

**Architecture:** Two independent deliverables on top of the existing v3 steward. (A) A pytest-based privacy auditor (`tests/test_privacy_surface.py`) that drives the real relay app end-to-end with planted PHI canaries and scans every reachable surface — API responses, captured logs, push payloads — asserting zero leakage; its correctness is proven by a temporary canary-leak self-test. (B) Ed25519 signing of `release_manifest_v3.json` via a new `scripts/sign_release_manifest.py` (mirroring the existing `sign_protocol.py` pattern), verified fail-closed at relay startup, exercised by tamper/wrong-key/stable-channel drill tests.

**Tech Stack:** Python 3.11 (miniforge3 — repo `.venv` is bare), FastAPI TestClient, pytest `caplog`, `cryptography` Ed25519, hatchling layout (`src/ai_doctor`). No new dependencies.

**Verification baseline (verified 2026-08-23):**
```bash
/Users/min/miniforge3/bin/python -m pytest -q     # 55 passed
/Users/min/miniforge3/bin/python -m ruff check src tests   # All checks passed
npm run typecheck && npm run test:frontend && npm run build   # exit 0, 9 vitest tests
```
All commands below run from `/Users/min/projects/ai-doctor`. Python invocations use `/Users/min/miniforge3/bin/python` because `.venv/bin/python` lacks pytest/ruff.

---

## Current context / assumptions

- Working tree (all verified passing): modified `README.md`, `apps/pwa/src/cryptoVault.ts`, `src/ai_doctor/domain/longitudinal.py`, `src/ai_doctor/relay.py`, `tests/test_longitudinal_relay.py`; untracked `apps/pwa/src/cryptoVault.test.ts`, `docs/MASTER_GOAL_STATUS.md`, `docs/REQUIREMENTS_TRACEABILITY.md`, `docs/security/THREAT_MODEL.md`, `docs/security/INCIDENT_REGISTER.md`.
- Uncommitted relay work adds P-256 envelope signature verification (`verify_envelope_signature`, `_envelope_signing_payload`, JWK validation in `domain/longitudinal.py`); PWA adds `canonicalJson` + `device_signing_public_jwk`.
- `src/ai_doctor/config/release_manifest_v3.json` ends with `"signature": null` — the field this plan fills. Manifest artifacts are keyed by SHA-256 digest; `knowledge/v3/cardiometabolic_pack.json` is the single required artifact (digest `1a51827…f8f`).
- Relay release endpoints live at `src/ai_doctor/relay.py:709-733` (`GET /v1/releases/{channel}/manifest`, `GET /v1/releases/artifacts/{digest}`); `_manifest_digest()` at line 595 canonicalizes with `sort_keys=True, separators=(",", ":")`. Stable channel already fails closed while `approved_for_clinical_use=false`.
- Settings pattern to follow: `Settings.from_env()` in `src/ai_doctor/settings.py`; protocol keys already use `AI_DOCTOR_PROTOCOL_PUBLIC_KEYS_JSON` style naming.
- House signing conventions from `scripts/sign_protocol.py`: private key never printed/stored; canonical bytes signed; atomic output write; approval requires explicit state field.
- Docs to update after each milestone: `docs/security/THREAT_MODEL.md` (threat register rows T-05, T-08), `docs/MASTER_GOAL_STATUS.md` (release-gate ledger "Privacy and security" row + Decision/evidence notes), `docs/REQUIREMENTS_TRACEABILITY.md` (PS-01, EV-01, OP-02 evidence cells).

---

## Phase 0 — Commit the Aug-12+ work

### Task 0.1: Commit envelope-signature verification (code + tests)

**Objective:** Land the P-256 signature-verification vertical slice as one reviewable commit.

**Files (exact):**
- `src/ai_doctor/relay.py`, `src/ai_doctor/domain/longitudinal.py`, `tests/test_longitudinal_relay.py`
- `apps/pwa/src/cryptoVault.ts`, `apps/pwa/src/cryptoVault.test.ts`

**Steps:**
1. Re-run gates to confirm the tree is green before committing:
   ```bash
   /Users/min/miniforge3/bin/python -m pytest -q          # expect: 55 passed
   npm run typecheck && npm run test:frontend             # expect: exit 0
   ```
2. Stage and commit:
   ```bash
   git add src/ai_doctor/relay.py src/ai_doctor/domain/longitudinal.py \
           tests/test_longitudinal_relay.py \
           apps/pwa/src/cryptoVault.ts apps/pwa/src/cryptoVault.test.ts
   git commit -m "feat: verify P-256 device signatures on sync envelopes"
   ```
3. Verify: `git status --short` shows only README/docs paths remaining.

### Task 0.2: Commit governance documentation

**Objective:** Land the release-gate ledger, traceability matrix, and threat model that Phase 1–2 will amend.

**Files:** `README.md`, `docs/MASTER_GOAL_STATUS.md`, `docs/REQUIREMENTS_TRACEABILITY.md`, `docs/security/THREAT_MODEL.md`, `docs/security/INCIDENT_REGISTER.md`

**Steps:**
```bash
git add README.md docs/
git commit -m "docs: add master-goal ledger, requirements traceability, threat model"
git status --short    # expect: empty
```

---

## Phase 1 — Automated privacy-surface audit (T-05)

Design principle: the auditor drives the **real** app through `create_app` exactly like `tests/test_longitudinal_relay.py` does (fixture helpers at top of that file show the enrollment/sync/push setup pattern — reuse them, extract shared helpers if needed without breaking existing tests). Planted PHI values must be unique sentinel strings that cannot occur naturally, e.g. patient name `"ZzCanaryQamarZz"` and Burmese string `"ကနာရီစမ်းသပ်စာ"`. Every surface is serialized to text and scanned for those sentinels.

### Task 1.1: Write the auditor harness + response-surface test (RED)

**Files:**
- Create: `tests/test_privacy_surface.py`
- Reference (do not modify yet): `tests/test_longitudinal_relay.py:1-90` (app/client/profile-enrollment fixtures)

**Step 1: Write failing test**

Core shape:

```python
"""Automated privacy-surface audit: no planted PHI may reach any observable surface.

Covers threat T-05 in docs/security/THREAT_MODEL.md. Sentinels are unique
canary strings; any hit is a hard failure with the offending surface named.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

CANARY_NAME = "ZzCanaryQamarZz"
CANARY_MM = "ကနာရီစမ်းသပ်စာ"
SENTINELS = (CANARY_NAME, CANARY_MM)


def _assert_clean(*surfaces: tuple[str, str]) -> None:
    """Each surface is (name, text). Fail loudly naming every leaking surface."""
    leaked = [
        name for name, text in surfaces
        if any(sentinel in text for sentinel in SENTINELS)
    ]
    assert not leaked, f"planted PHI reached surfaces: {leaked}"
```

Then a test that enrolls a profile, pushes an encrypted envelope whose *plaintext* (built locally in-test before encryption, using the `cryptoVault`-equivalent Python-side fixture pattern from `test_longitudinal_relay.py`) embeds both sentinels, then walks every read path:

- `GET /v1/sync/envelopes` (list + each item JSON-dumped),
- `GET /v1/releases/preclinical/manifest`,
- `GET /v1/releases/artifacts/<digest>`,
- `GET /v1/operations/health`, `GET /health`,
- error responses from deliberately invalid requests (40x bodies),

and calls `_assert_clean("sync_list", json.dumps(...), ...)` per surface.

**Step 2: Run it**
```bash
/Users/min/miniforge3/bin/python -m pytest tests/test_privacy_surface.py -q
# Expect: PASS (controls currently hold) — the RED proof comes from Task 1.2's canary.
```
If it FAILS immediately, stop: that is a real finding — record it in `docs/security/INCIDENT_REGISTER.md` before proceeding.

### Task 1.2: Prove the auditor detects leaks (canary self-test, then remove)

**Objective:** An auditor that cannot fail is decoration. Temporarily plant a leak, watch the audit go red, revert.

**Files:** Modify `tests/test_privacy_surface.py` only.

**Steps:**
1. Add a temporary test that monkeypatches a route dependency (or wraps the app with a middleware appending `CANARY_NAME` to a JSON response) and asserts `_assert_clean` raises `AssertionError`.
2. Run: `/Users/min/miniforge3/bin/python -m pytest tests/test_privacy_surface.py -k canary_detector -q` → expect PASS (detector fired).
3. Delete the temporary injection test. The permanent suite keeps only honest assertions.

### Task 1.3: Push-payload surface test

**Files:** Modify `tests/test_privacy_surface.py`.

**Step 1:** Assert the push path can only ever transmit the generic constant. Instantiate `GenericPushWorker` (from `src/ai_doctor/push_worker.py`) with a schedule whose endpoint/keys fields embed sentinels, monkeypatch `ai_doctor.push_worker.webpush` to capture `data`, run `run_once()`, then:

```python
captured = json.loads(webpush_calls[0].kwargs["data"])
assert captured == {"message": GENERIC_PUSH_MESSAGE}
_assert_clean(("push_payload", json.dumps(webpush_calls)))
```

Also assert provider acceptance ≠ display: `finish_push_attempt(..., accepted=True)` records delivery state without any content echo (mirror `tests/test_longitudinal_relay.py::test_push_schedule_forces_generic_message` but from the worker side).

**Step 2:** Run → expect PASS.

### Task 1.4: Log-capture surface test

**Files:** Modify `tests/test_privacy_surface.py`.

**Step 1:** Drive a full workflow (enroll → sync → invalid requests → push) under pytest `caplog` at `DEBUG` level, plus `logging.captureWarnings(True)`; concatenate `record.getMessage()` for all records:

```python
def test_no_phi_in_logs(client, enrolled_profile, caplog):
    ...
    with caplog.at_level(logging.DEBUG):
        # exercise workflow incl. deliberate 400/401/409 responses
    _assert_clean(("logs", "\n".join(r.getMessage() for r in caplog.records)))
```

**Step 2:** Run → expect PASS. Any uvicorn/FastAPI access-log style record containing query strings or bodies must be covered too (TestClient logs go through the same root logger).

### Task 1.5: Static guard on push text + full-suite gate

**Files:** Modify `tests/test_privacy_surface.py`.

**Step 1 (cheap static check):** Assert `GENERIC_PUSH_MESSAGE` imported in `push_worker.py` is the exact literal from `relay.py` (no interpolation possible):

```python
import inspect
src = inspect.getsource(push_worker_module)
assert 'json.dumps({"message": GENERIC_PUSH_MESSAGE})' in src
assert "f\"" not in next(
    line for line in src.splitlines() if "GENERIC_PUSH_MESSAGE" in line and "json.dumps" in line
)
```

**Step 2:** Full gate:
```bash
/Users/min/miniforge3/bin/python -m pytest -q        # expect: 55 + ~6 new = ~61 passed
/Users/min/miniforge3/bin/python -m ruff check src tests   # expect: All checks passed!
```

**Step 3: Commit**
```bash
git add tests/test_privacy_surface.py
git commit -m "test: automated privacy-surface audit for relay, logs, and push (T-05)"
```

### Task 1.6: Update governance docs to match evidence

**Files:**
- `docs/security/THREAT_MODEL.md` — row T-05: Current state `Partial` → `Implemented (local evidence)`; Detection/evidence cell += "automated surface audit (`tests/test_privacy_surface.py`)"; Remaining work narrows to independent assessment/log-capture-on-deployed-config.
- `docs/MASTER_GOAL_STATUS.md` — "Privacy and security" gate row: cite the automated audit as new current evidence; limitation cell drops "automated privacy surface audit" from incomplete list. Add one-line decision-record note pointing at the audit file.
- `docs/REQUIREMENTS_TRACEABILITY.md` — PS-01 verification-evidence cell += audit test reference.

**Verify:** numbers quoted in docs match actual test counts. Commit:
```bash
git add docs/
git commit -m "docs: record privacy-surface audit evidence (T-05)"
```

---

## Phase 2 — Signed manifest verification drill (T-08)

Design: fill the manifest's existing `"signature": null` slot. Signature covers the canonical manifest bytes (same canonicalization as `_manifest_digest`) with the `signature` field set to `null` during signing — mirroring how `sign_protocol.py` pops then re-adds `approval.signature`. Verification happens once at app creation: fail closed (refuse to start) whenever a signature is present-but-invalid, or when `AI_DOCTOR_REQUIRE_SIGNED_MANIFEST=true` and no valid signature exists. Preclinical default stays runnable unsigned (documented), preserving today's behavior; the drill proves the enforced path.

### Task 2.1: Canonical bytes helper + signing script (RED→GREEN)

**Files:**
- Create: `scripts/sign_release_manifest.py` (pattern-copy of `scripts/sign_protocol.py`)
- Create: `tests/test_release_signing.py`

**Step 1: Write failing test** (imports the script module via the same `sys.path` insert trick `sign_protocol.py` uses):

```python
def test_sign_and_verify_roundtrip(tmp_path):
    manifest = json.loads(Path("src/ai_doctor/config/release_manifest_v3.json").read_text())
    key = Ed25519PrivateKey.generate()
    signed = sign_release_manifest.sign_manifest(
        manifest, private_key=key, key_id="drill-key-1", signer_id="release-drill"
    )
    assert signed["signature"]["state"] == "approved"
    verify_release_manifest.verify_manifest_signature(signed, {"drill-key-1": key.public_key()})
```

**Step 2:** Run → FAIL (module missing).

**Step 3: Implement** `scripts/sign_release_manifest.py` with three functions kept import-safe (no side effects at import, `main()` guarded — same discipline as `sign_protocol.py`):

- `manifest_signing_bytes(manifest)` → deep-copied manifest with `signature=None`, then `json.dumps(sort_keys=True, separators=(",", ":")).encode()` — identical canonicalization to `relay._manifest_digest` so digests stay consistent;
- `sign_manifest(record, private_key, key_id, signer_id)` → sets `signature = {"state": "approved", "key_id": ..., "signer_id": ..., "signed_at": <UTC ISO>, "signature": base64(...)}`; refuses if `approved_for_clinical_use` is being flipped relative to input;
- CLI `main()`: `--input/--output/--private-key/--key-id/--signer-id/--force`, atomic write, private key never logged.

Plus `src/ai_doctor/config/verify_release_manifest.py` (runtime verifier, importable by both relay and tests):
- `verify_manifest_signature(manifest, public_keys: dict[str, Ed25519PublicKey])` → re-canonicalizes with `signature=None`, decodes base64 sig, `public_key.verify(...)`; raises `ValueError` on: missing signature object, unknown `key_id`, bad base64, verification failure.

**Step 4:** Run → PASS. Then:
```bash
git add scripts/sign_release_manifest.py src/ai_doctor/config/verify_release_manifest.py tests/test_release_signing.py
git commit -m "feat: ed25519 signing + verification for release manifests"
```

### Task 2.2: Wire fail-closed verification into relay startup

**Files:**
- Modify: `src/ai_doctor/settings.py` — add `release_manifest_public_keys_path: Path | None` (`AI_DOCTOR_RELEASE_MANIFEST_PUBLIC_KEYS_JSON`, map of key-id → base64 public key, same shape as protocol keys) and `require_signed_manifest: bool` (`AI_DOCTOR_REQUIRE_SIGNED_MANIFEST`, default `false`).
- Modify: `src/ai_doctor/relay.py` — in the app-factory path where `release_manifest_path` is resolved (near the routes at lines 605/709), load manifest once; if public-keys file configured OR manifest has non-null `signature` → call `verify_manifest_signature`; raise (factory fails, server refuses boot) on any verification error. Unsigned + unconfigured + `require_signed=false` → proceed unchanged.

**Tests (add to `tests/test_release_signing.py`)** — build tiny fixture manifests in `tmp_path` rather than mutating the real one:

```python
def test_tampered_artifact_digest_refuses_startup(tmp_path): ...
def test_unknown_key_id_refuses_startup(tmp_path): ...
def test_unsigned_allowed_by_default_but_refused_when_required(tmp_path): ...
```

Tamper technique: sign correctly, then flip one byte inside the artifact file the manifest pins (write a mutated copy of the pack JSON) → startup must raise. Unknown key: sign with key not in the configured map → raise.

**Run:** `/Users/min/miniforge3/bin/python -m pytest tests/test_release_signing.py -q` → all PASS; full suite still green.

**Commit:** `git commit -am "feat: fail-closed manifest signature verification at relay startup"`

### Task 2.3: End-to-end drill through the running app

**Files:** Modify `tests/test_release_signing.py`.

**Scenario tests (the actual "drill"):**
1. Generate keypair in-test; write public-key map JSON to `tmp_path`; produce a signed copy of the real manifest whose artifact path points at a `tmp_path` copy of the cardiometabolic pack.
2. `create_app(...)` with the keys configured + signed manifest → client hits `GET /v1/releases/preclinical/manifest` → 200, and `manifest_digest` returned matches recomputation from the served body.
3. Same setup but `require_signed_manifest=true` with an *unsigned* manifest → app creation raises.
4. Signed manifest, then rotate: configure map with only `drill-key-2` while manifest signed by `drill-key-1` → raises (revocation semantics: removing a key kills trust in everything it signed).
5. Stable-channel regression: `GET /v1/releases/stable/manifest` still 404s while `approved_for_clinical_use=false`.

**Run + commit:** `pytest -q` green → `git commit -m "test: signed-manifest tamper, revocation, and stable-channel drill (T-08)"`.

### Task 2.4: Operator runbook + docs

**Files:**
- Modify: `deployment/.env.example` — append documented lines (commented, demo-token warning style already established there):
  ```text
  # Release-manifest signature enforcement (optional in preclinical):
  # AI_DOCTOR_RELEASE_MANIFEST_PUBLIC_KEYS_JSON=/secure/path/manifest_keys.json
  # AI_DOCTOR_REQUIRE_SIGNED_MANIFEST=true
  ```
- Modify: `docs/PERSONAL_STEWARD_V3.md` — short "Release signing" subsection: key generation (`cryptography` one-liner or openssl), signing command invocation example, rotation = publish new key map + re-sign.
- Modify: `docs/security/THREAT_MODEL.md` T-08 row → `Implemented (local evidence)`, evidence = drill tests; Remaining work = expiry policy + deployed-config drill.
- Modify: `docs/MASTER_GOAL_STATUS.md` ledger row "Deterministic clinical safety"/"Privacy and security" cross-reference + traceability EV-01/OP-02 cells.

**Verify:** every doc claim maps to a test that exists. Commit:
```bash
git add deployment/.env.example docs/
git commit -m "docs: release-manifest signing runbook and updated threat register (T-08)"
```

---

## Final verification sweep

```bash
cd /Users/min/projects/ai-doctor
/Users/min/miniforge3/bin/python -m pytest -q                 # expect ≥ 61 passed, 0 failed
/Users/min/miniforge3/bin/python -m ruff check src tests      # All checks passed!
npm run typecheck && npm run test:frontend && npm run build   # exit 0
git log --oneline                                             # ~8 commits, clean tree
```

Manual smoke (optional but cheap): boot the relay unsigned (today's mode) and hit `/v1/releases/preclinical/manifest` → 200; boot again with `AI_DOCTOR_REQUIRE_SIGNED_MANIFEST=true` and no keys → process exits with the verification error.

---

## Risks, tradeoffs, open questions

1. **Unsigned-by-default is a documented compromise.** Requiring signatures unconditionally would break every existing dev/deploy flow for zero attacker-model gain in preclinical (keys would live beside the code). Mitigation: the `AI_DOCTOR_REQUIRE_SIGNED_MANIFEST` switch gives operators the enforced posture now; flip it in Compose when the home-server key ceremony happens. Open question: should Compose default the flag to `true` with a mounted key file? Left out until a real operator environment exists (matches the repo's "no fake production claims" rule).
2. **Sentinel-based audits prove the tested surfaces only.** Timing/metadata channels and the deployed reverse-proxy logs are out of scope locally — THREAT_MODEL wording must keep saying "not an independent assessment."
3. **Canonicalization drift risk:** `manifest_signing_bytes` must stay byte-identical to `relay._manifest_digest` logic. Both derive from one `json.dumps(sort_keys=True, separators=(",",":"))` recipe; consider importing a single shared helper if duplication starts to smell (DRY follow-up, not a blocker).
4. **Fixture-manifest tests must not touch the real config file.** All drill tests operate on `tmp_path` copies; the committed `release_manifest_v3.json` keeps `signature: null` until a human signs a release.
5. **caplog coverage gap:** third-party libs logging via their own handlers (not the root logger) could escape `caplog`. Acceptable residual risk preclinical; noted in docs.
6. **Scope guard (YAGNI):** no CI pipeline, no PWA-side manifest verification, no PostgreSQL migration in this pass — those are separate ledger items.
