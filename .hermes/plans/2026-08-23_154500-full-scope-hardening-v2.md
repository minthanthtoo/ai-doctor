# AI Doctor OS — Full-Scope Hardening & Completion Plan (v2, Breadth + Depth)

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task. Fresh subagent per task; two-stage review (spec compliance → code quality); proceed only when both approve.

**Goal:** Take AI Doctor OS from "green but fragile" (7.2/10) to "durable, provable, showable" by executing the council's ranked moves: land custody (Phase 0), close ledger threats T-05/T-08 with executable evidence (Phases 1–2), create the missing external surface — icons, screenshots, first-contact clarity (Phase 3), and convert governance honesty into a stated distribution decision + reviewer-recruitment asset (Phase 4).

**Architecture:** Four sequential phases, each independently shippable and ending in commits + doc updates. Phase 0 is pure git hygiene (no code changes). Phases 1–2 are test-first security engineering on the existing FastAPI relay (`src/ai_doctor/`) using pytest + TestClient + `cryptography` Ed25519 — zero new runtime dependencies. Phase 3 adds build assets only (SVG→PNG via installed `rsvg-convert`, no npm changes beyond `vite-plugin-pwa` defaults already present). Phase 4 touches only docs. Every phase re-runs the full verification matrix before committing.

**Tech Stack:** Python 3.11 via `/Users/min/miniforge3/bin/python` (repo `.venv` is bare — verified), pytest 8.4.2, FastAPI TestClient, `cryptography` (Ed25519), pytest `caplog`; Node workspace scripts already wired (`npm run typecheck | test:frontend | build`); Pillow 12.3.0 + `rsvg-convert` + ImageMagick (all verified installed) for icon generation; plain `git` (no `gh` CLI installed — verified).

**Verified environment facts this plan relies on (2026-08-23):**
```bash
/Users/min/miniforge3/bin/python -m pytest -q        # 55 passed
/Users/min/miniforge3/bin/python -m ruff check src tests   # All checks passed!
npm run typecheck && npm run test:frontend && npm run build   # exit 0; 9 vitest tests
git -C /Users/min/projects/ai-doctor remote -v       # EMPTY — no remote exists
gh --version                                          # gh: command not found
python3 -c 'import PIL'                              # PIL 12.3.0 available
```

---

## Working-state snapshot (what Phase 0 inherits)

Uncommitted modified: `README.md`, `apps/pwa/src/cryptoVault.ts`, `src/ai_doctor/domain/longitudinal.py`, `src/ai_doctor/relay.py`, `tests/test_longitudinal_relay.py`.
Untracked: `apps/pwa/src/cryptoVault.test.ts`, `docs/MASTER_GOAL_STATUS.md`, `docs/REQUIREMENTS_TRACEABILITY.md`, `docs/security/THREAT_MODEL.md`, `docs/security/INCIDENT_REGISTER.md`.
Branch `main` @ `1cb4619`; sole author `Min Thant Htoo <minthanthtoo.cs@gmail.com>` (verified identity).
Key anchors: `relay.py:595` `_manifest_digest()`, `relay.py:709-733` release routes, `settings.py` env-var convention, `scripts/sign_protocol.py` house signing pattern, `release_manifest_v3.json` ends `"signature": null`, `deployment/.env.example` currently comment-only.

---

# PHASE 0 — Custody & Baseline (council move #1)

**Why first:** everything else is worthless if the disk dies. Also the smallest effort/highest score-delta item (Continuity 4→8).

### Task 0.1: Re-verify green, then commit the security slice

**Files:** `src/ai_doctor/relay.py`, `src/ai_doctor/domain/longitudinal.py`, `tests/test_longitudinal_relay.py`, `apps/pwa/src/cryptoVault.ts`, `apps/pwa/src/cryptoVault.test.ts`

**Steps:**
1. `cd /Users/min/projects/ai-doctor`
2. Run gates:
   ```bash
   /Users/min/miniforge3/bin/python -m pytest -q     # expect: 55 passed
   npm run typecheck && npm run test:frontend        # expect: exit 0
   ```
   If anything fails: STOP, report, do not commit broken state.
3. Commit:
   ```bash
   git add src/ai_doctor/relay.py src/ai_doctor/domain/longitudinal.py tests/test_longitudinal_relay.py apps/pwa/src/cryptoVault.ts apps/pwa/src/cryptoVault.test.ts
   git commit -m "feat: verify P-256 device signatures on sync envelopes"
   ```
4. Verify: `git status --short` → only README/docs lines remain.

### Task 0.2: Commit governance docs

**Files:** `README.md`, `docs/MASTER_GOAL_STATUS.md`, `docs/REQUIREMENTS_TRACEABILITY.md`, `docs/security/THREAT_MODEL.md`, `docs/security/INCIDENT_REGISTER.md`

**Steps:**
```bash
git add README.md docs/
git commit -m "docs: master-goal ledger, requirements traceability, threat model"
git status --short    # expect: empty tree
```

### Task 0.3: Create a remote and push (custody fix)

**Constraint:** `gh` is not installed. Two acceptable strategies — pick ONE before starting (decision recorded here, not improvised later):

- **Option A (preferred): GitHub private repo via browser.** User creates empty private repo `ai-doctor` on github.com (account `minthanthtoo`, verified); agent then runs:
  ```bash
  git remote add origin git@github.com:minthanthtoo/ai-doctor.git   # or https URL if no SSH key set up
  git push -u origin main
  ```
  Pre-check first: `ssh -T git@github.com` (10s timeout). If SSH fails, fall back to HTTPS and let the OS credential helper prompt the user.
- **Option B (offline-safe): local bare mirror as pseudo-offsite.**
  ```bash
  git init --bare /Volumes/<EXTERNAL>/git-mirrors/ai-doctor.git    # requires mounted external volume
  git remote add offsite /Volumes/<EXTERNAL>/git-mirrors/ai-doctor.git
  git push -u offsite main
  ```
  If no external volume is mounted, ask the user; do not silently skip custody.

**Verify:** `git ls-remote <origin-or-offsite> HEAD` returns the pushed SHA equal to `git rev-parse HEAD`. Record chosen option + URL in the final report.

### Task 0.4: Record the runnable-truth note (env drift fix, one-line class)

**Files:** Modify `README.md` ("Run locally" section).

**Step:** Insert directly under the existing `uv sync --extra test` block:
```markdown
> Verified runner on this machine: `/Users/min/miniforge3/bin/python -m pytest -q`
> (the checked-in `.venv/` is an empty shell; recreate with `uv venv && uv sync --extra test`).
```
Commit with Phase 0 wrap-up: `git commit -am "docs: note verified test runner"`.

---

# PHASE 1 — Automated Privacy-Surface Audit (ledger T-05)

**Design principle:** audit the REAL app through `create_app`, exactly like `tests/test_longitudinal_relay.py` does (reuse its fixture helpers at top of file; extract shared helpers into `tests/conftest.py` ONLY if it doesn't change existing test behavior — run that file after extraction). Planted PHI = unique sentinels that cannot occur naturally: `ZzCanaryQamarZz` (name) and `ကနာရီစမ်းသပ်စာ` (Burmese string). Any sentinel on any observable surface = hard failure naming the surface.

### Task 1.1: Auditor harness + API-response surface (RED→GREEN)

**Files:** Create `tests/test_privacy_surface.py`.

**Step 1: write the harness + first surfaces**

```python
"""Automated privacy-surface audit — threat T-05 (docs/security/THREAT_MODEL.md).

No planted PHI may reach any observable surface: sync listings, release
manifest/artifacts, health endpoints, error bodies, logs, push payloads.
"""
from __future__ import annotations
import json

CANARY_NAME = "ZzCanaryQamarZz"
CANARY_MM = "ကနာရီစမ်းသပ်စာ"
SENTINELS = (CANARY_NAME, CANARY_MM)

def _assert_clean(*surfaces: tuple[str, str]) -> None:
    leaked = [n for n, t in surfaces if any(s in t for s in SENTINELS)]
    assert not leaked, f"planted PHI reached surfaces: {leaked}"
```

Then a test that enrolls a profile (fixture pattern from `test_longitudinal_relay.py`), pushes one encrypted envelope whose plaintext embeds BOTH sentinels, and walks every GET surface: `/v1/sync/envelopes` (list JSON), `/v1/releases/preclinical/manifest`, `/v1/releases/artifacts/<digest-from-manifest>`, `/v1/operations/health`, `/health`, plus error bodies from deliberate bad requests (malformed envelope → 4xx body scanned too).

**Step 2:** `/Users/min/miniforge3/bin/python -m pytest tests/test_privacy_surface.py -q` → expect PASS (controls hold today). If FAIL: real finding — log in `docs/security/INCIDENT_REGISTER.md` before any other task.

### Task 1.2: Prove the auditor can fail (canary self-test, then delete)

**Files:** modify `tests/test_privacy_surface.py` temporarily.

1. Add `test_canary_detector_works`: wrap the app with a tiny ASGI middleware that appends `CANARY_NAME` to one JSON response; assert `_assert_clean` raises `AssertionError`.
2. Run `-k canary_detector` → PASS means detector fires.
3. Delete the middleware test. Permanent suite keeps only honest assertions.

### Task 1.3: Push-payload surface

**Files:** extend `tests/test_privacy_surface.py`.

Instantiate `GenericPushWorker` (`src/ai_doctor/push_worker.py`) against a schedule whose endpoint/keys embed sentinels; monkeypatch `ai_doctor.push_worker.webpush` to capture kwargs; run `run_once()`; assert captured payload equals exactly `{"message": GENERIC_PUSH_MESSAGE}` and `_assert_clean(("push_payload", json.dumps(calls)))`. Also assert acceptance ≠ acknowledgement: `finish_push_attempt(..., accepted=True)` stores delivery state with no content echo (worker-side mirror of existing `test_push_schedule_forces_generic_message`). Run → PASS.

### Task 1.4: Log-capture surface

**Files:** extend `tests/test_privacy_surface.py`.

Drive enroll→sync→deliberate-400s→push inside `caplog.at_level(logging.DEBUG)` plus `logging.captureWarnings(True)`; scan `"\n".join(r.getMessage() for r in caplog.records)` including uvicorn error/access records emitted through root logging. Run → PASS. Residual gap (third-party handlers outside root logger) stays documented in THREAT_MODEL wording.

### Task 1.5: Static push-text guard + full gate + commit

**Files:** extend `tests/test_privacy_surface.py`.

Static guard via `inspect.getsource(push_worker_module)`: assert the send call is literally `json.dumps({"message": GENERIC_PUSH_MESSAGE})` and that line contains no f-string/concatenation. Then:
```bash
/Users/min/miniforge3/bin/python -m pytest -q               # expect ~61 passed
/Users/min/miniforge3/bin/python -m ruff check src tests    # All checks passed!
git add tests/test_privacy_surface.py
git commit -m "test: automated privacy-surface audit for relay, logs, push (T-05)"
```

### Task 1.6: Governance doc updates (evidence must match tests)

**Files:** `docs/security/THREAT_MODEL.md` (T-05 row: Partial → Implemented (local evidence); evidence cell += audit file; remaining work narrows to independent assessment + deployed-config capture), `docs/MASTER_GOAL_STATUS.md` (Privacy-and-security gate row cites audit; drop "automated privacy surface audit" from incomplete list), `docs/REQUIREMENTS_TRACEABILITY.md` (PS-01 evidence cell += audit reference).
Verify quoted counts match actual suite size. Commit: `git commit -am "docs: record privacy-audit evidence (T-05)"`.

---

# PHASE 2 — Signed Manifest Verification Drill (ledger T-08)

**Design:** fill the manifest's existing `"signature": null` slot. Signature over canonical bytes identical to `_manifest_digest` canonicalization, computed with `signature=None`. Verification at app creation, fail-closed when signature present-but-invalid OR when enforcement flag set and unsigned. Unsigned+unconfigured default remains runnable (documented compromise — preclinical posture; flipping happens at home-server key ceremony).

### Task 2.1: Canonical signer + verifier modules (RED→GREEN)

**Files:** Create `scripts/sign_release_manifest.py`, `src/ai_doctor/config/verify_release_manifest.py`, `tests/test_release_signing.py`.

Test first (RED):
```python
def test_sign_and_verify_roundtrip():
    manifest = json.loads(Path("src/ai_doctor/config/release_manifest_v3.json").read_text())
    key = Ed25519PrivateKey.generate()
    signed = sign_release_manifest.sign_manifest(manifest, private_key=key,
                                                 key_id="drill-key-1", signer_id="release-drill")
    verify_release_manifest.verify_manifest_signature(signed, {"drill-key-1": key.public_key()})
```

Implement (GREEN):
- `manifest_signing_bytes(manifest)`: deepcopy, `signature=None`, `json.dumps(sort_keys=True, separators=(",", ":")).encode("utf-8")` — byte-identical recipe to `relay._manifest_digest` (DRY follow-up optional: single shared helper).
- `sign_manifest(...)`: sets `signature={"state":"approved","key_id","signer_id","signed_at","signature"(base64)}`; refuses if input already carries a non-null signature unless `--force` semantics; never prints/logs the key.
- `verify_manifest_signature(manifest, public_keys)`: raises `ValueError` on missing/malformed signature object, unknown key_id, bad base64, failed verify.
- CLI mirrors `sign_protocol.py`: `--input/--output/--private-key/--key-id/--signer-id/--force`, atomic temp-file write.
- Import-safe: all side effects under `main()` guard (so tests can import functions).

Run roundtrip → PASS. Commit: `git commit -m "feat: ed25519 sign/verify for release manifests"`.

### Task 2.2: Fail-closed startup wiring

**Files:** Modify `src/ai_doctor/settings.py`, `src/ai_doctor/relay.py`.

- Settings additions (naming follows existing convention): `release_manifest_public_keys_path` ← `AI_DOCTOR_RELEASE_MANIFEST_PUBLIC_KEYS_JSON` (map key-id→base64 public key); `require_signed_manifest` ← `AI_DOCTOR_REQUIRE_SIGNED_MANIFEST` (default false).
- In app factory where `release_manifest_path` resolves (~line 605): load once; if keys configured OR manifest.signature non-null → verify; any failure raises so the server refuses boot. Unsigned + unconfigured + flag false → proceed unchanged (today's behavior preserved).

Tests (fixture manifests in `tmp_path` only — NEVER mutate committed config): tampered artifact byte → startup raises; signed-by-unknown-key → raises; unsigned allowed by default but refused when `require_signed_manifest=true`. Run file → PASS; full suite still green. Commit: `git commit -am "feat: fail-closed manifest verification at relay startup"`.

### Task 2.3: End-to-end drill scenarios

**Files:** extend `tests/test_release_signing.py`.

1. Keypair in-test → public-key map JSON in `tmp_path` → signed copy of real manifest pointing at `tmp_path` pack copy → `create_app` boots → `GET /v1/releases/preclinical/manifest` returns 200 and served `manifest_digest` recomputes exactly from served body.
2. `require_signed=true` + unsigned manifest → creation raises.
3. Rotation/revocation: map contains only `drill-key-2`, manifest signed by `drill-key-1` → raises (removing a key kills trust in everything it signed).
4. Stable-channel regression: `GET /v1/releases/stable/manifest` still 404 while `approved_for_clinical_use=false`.

Run + commit: `git commit -m "test: signed-manifest tamper/revocation/stable drill (T-08)"`.

### Task 2.4: Operator runbook + docs

**Files:** `deployment/.env.example` (append commented block: the two new vars + warning style already used), `docs/PERSONAL_STEWARD_V3.md` ("Release signing" subsection: openssl/cryptography keygen, sign command example, rotation = new key map + re-sign), THREAT_MODEL T-08 row → Implemented (local evidence), MASTER_GOAL_STATUS ledger row update, REQUIREMENTS_TRACEABILITY EV-01/OP-02 cells.
Every doc claim maps to an existing test. Commit: `git commit -am "docs: manifest signing runbook (T-08)"`.

---

# PHASE 3 — External Surface: Icons, Screenshots, First Contact (council move #2)

**Why:** `apps/pwa/public/` is verifiably empty → degraded install prompts, zero first-contact clarity. All tooling verified present (`rsvg-convert`, Pillow, ImageMagick). No design taste required: geometric mark derived from the product's own identity (shield + pulse line), bilingual label support already in-app.

### Task 3.1: Generate PWA icon set

**Files:** Create `apps/pwa/public/icon-192.png`, `icon-512.png`, `maskable-512.png`, `favicon.svg`; Modify `apps/pwa/vite.config.ts` (VitePWA manifest block: icons + theme_color `#0f172a`, background_color same, display standalone — match existing styles.css palette).

**Steps:**
1. Write `scripts/make_icons.py` (checked in, reproducible): draws shield outline + ECG polyline on transparent/solid background via Pillow primitives (no font dependency), exports 192/512 + maskable (safe-zone padded 80%).
   ```bash
   /Users/min/miniforge3/bin/python scripts/make_icons.py
   ```
2. Verify sizes: `file apps/pwa/public/*.png` shows exact dimensions.
3. `npm run build` → dist contains copied icons; `dist/manifest.webmanifest` lists them.
4. Lighthouse-style sanity: open `dist/index.html` via preview — install prompt eligibility needs icons+SW; SW already precaches (verified earlier: 5 entries → will grow).
5. Commit: `git commit -am "feat(pwa): app icons and web manifest metadata"`.

### Task 3.2: Three screenshots + README hero

**Files:** Create `docs/img/onboarding.png`, `timeline.png`, `emergency-lock.png`; Modify `README.md` top section.

**Steps:**
1. `npm run dev --workspace @ai-doctor/pwa` (background) → drive the real UI through its three states (concern intake, timeline, deterministic emergency lock) in the desktop preview/browser session → capture PNGs into `docs/img/`.
2. If a view requires seeded data, seed via the app's own dev path or Dexie fixture — never fabricate screenshots of unimplemented features; caption honestly ("preclinical build").
3. README hero block: screenshot + three-line boundary summary lifted from MASTER_GOAL_STATUS ("does / refuses / proven / unproven").
4. Commit: `git commit -am "docs: real UI screenshots and README hero"`.

### Task 3.3: One-page boundary document (trust asset extraction, council move #4)

**Files:** Create `docs/BOUNDARY_ONE_PAGER.md`; link from README top.

Content skeleton (extract, don't invent — cite ledger cells): What it does today (5 bullets from implemented list) · What it refuses (prohibited list) · What's proven (test counts, green gates, implemented threat rows) · What isn't (blocked gates verbatim) · Who it's for right now (Task 4.1's answer). Commit: `git commit -am "docs: one-page capability boundary summary"`.

---

# PHASE 4 — Distribution Decision & Reviewer Recruitment Asset (council moves #5–6)

### Task 4.1: Explicit distribution stance (liability containment)

**Files:** Modify `README.md` (new short section "Distribution status"), `docs/MASTER_GOAL_STATUS.md` (decision-record entry following the existing format: Decision/Evidence/Alternatives/Why/Confidence/Reversal conditions).

**Decision to record (recommended default, user confirms):** *personal-only until external gates name owners* — no public distribution, no App Store listing, sharing only via direct collaboration. Alternatives considered: supervised pilot (requires GV-01 owner — blocked), silent public demo build (rejected: liability asymmetry). Reversal condition: named clinical owner signs on.

**Steps:** draft entry in ledger format → README section references it → commit: `git commit -am "docs: record personal-only distribution decision"`.

### Task 4.2: Reviewer-recruitment package (unblocks EV/LO/HF gates)

**Files:** Create `docs/REVIEWER_BRIEF.md`.

Contents assembled from existing artifacts only: intended-use statement (Blueprint §1.1 pattern applied to v3), the cardiometabolic pack scope (7 red flags, 6 vital rules — actual counts from the JSON), bilingual parity approach, what review would require (per promotion gates: content sign-off + language review), time estimate, and the one-pager attached. Written in English with a Burmese courtesy paragraph (draft; flagged as machine-assisted pending LO-01 reviewer — consistent with project honesty rules).
Commit: `git commit -am "docs: clinical/language reviewer recruitment brief"`.

---

# Final verification sweep (every phase end AND overall)

```bash
cd /Users/min/projects/ai-doctor
/Users/min/miniforge3/bin/python -m pytest -q                  # expect ≥ 61 passed (55 base + ~6 audit + signing/drill tests)
/Users/min/miniforge3/bin/python -m ruff check src tests       # All checks passed!
npm run typecheck && npm run test:frontend && npm run build    # exit 0
git log --oneline                                              # ~12 focused commits since 1cb4619
git status --short                                             # empty
git ls-remote origin HEAD 2>/dev/null || echo "offsite mirror in use"   # custody confirmed
ls apps/pwa/public                                             # icons present
```

Manual smoke (Phase 2 acceptance): boot unsigned (today's mode) → `/v1/releases/preclinical/manifest` 200; boot with `AI_DOCTOR_REQUIRE_SIGNED_MANIFEST=true` and no keys → process exits with verification error.

---

## Risks, tradeoffs, open questions

1. **Remote choice (Task 0.3)** is the only true user decision — Option A vs B differ in trust model. Do not improvise; ask once if ambiguous.
2. **Unsigned-by-default manifests** remain a documented compromise; the enforcement switch exists for the operator posture flip. Not a risk in preclinical; revisit at key ceremony.
3. **Screenshot authenticity rule (Task 3.2):** only capture real UI states; if a state can't be reached without fake data, skip it rather than stage it — project credibility outranks completeness.
4. **Icon aesthetic minimalism:** generated geometric marks won't win design awards; goal is install-eligibility + non-embarrassment. Custom design can replace them losslessly later (same filenames).
5. **Sentinel audits prove tested surfaces only** (timing/metadata channels, deployed proxy logs out of scope) — THREAT_MODEL keeps "not an independent assessment" wording.
6. **Canonicalization drift** between signer and `_manifest_digest` — mitigated by shared recipe; optional DRY refactor flagged, not blocking.
7. **Burmese paragraph in reviewer brief** is explicitly marked machine-assisted pending qualified review — consistent with LO-01 honesty; do not present it as reviewed content.
8. **Scope guards (YAGNI):** no CI pipeline, no PostgreSQL migration, no multi-device merge, no PWA-side manifest verification in this pass — separate ledger items.

## Execution order & dependencies

Phases strictly sequential (0 custody → 1 audit → 2 signing → 3 surface → 4 governance). Within phases, tasks ordered; Tasks 1.x depend on clean Phase 0 tree; Task 3.2 depends on 3.1 (icons in manifest before screenshots); Task 4.2 depends on 4.1 (stance sentence feeds the brief).
