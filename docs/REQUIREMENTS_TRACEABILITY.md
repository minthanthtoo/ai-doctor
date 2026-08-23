# Requirements-to-evidence traceability

This matrix is the canonical index from the locked master goal to implementation and evidence. A referenced file or passing test proves only the behavior it actually exercises.

| ID | Requirement | Implementation evidence | Verification evidence | Release state | Owner | Residual limitation |
|---|---|---|---|---|---|---|
| PC-01 | Preserve the locked patient authority boundary | `release_manifest_v3.json`; patient renderer and broker restrictions | kernel and relay tests | Preclinical | Engineering + clinical safety | Independent clinical review missing |
| PE-01 | Offline installable bilingual PWA | `apps/pwa`; custom service worker | Typecheck, Vitest, production build | Preclinical | Engineering | Device/browser matrix incomplete |
| PE-02 | Encrypted append-only local record and recovery | `cryptoVault.ts`, `db.ts`, `state.ts` | state tests and build | Preclinical | Engineering + security | Independent cryptographic review and device-loss drill missing |
| PE-03 | Opaque durable sync and backup | `relay.py`, `backup.py` | relay/backup tests | Preclinical | Engineering + operations | SQLite only; PostgreSQL and live restore drill missing |
| PE-04 | Credential/device-to-profile isolation | `relay_profile_owners`, `relay_devices`, P-256 signature verifier and route guards in `relay.py` | cross-token, invalid-signature, tamper, rebind, tombstone and delete tests | Preclinical control passed | Security | First-use binding must be replaced/integrated with production identity and independently penetration-tested |
| CS-01 | Emergency preempts routine reasoning | clinical kernel and triage capabilities | kernel and triage tests | Preclinical | Clinical safety | Not evaluated on independently adjudicated corpus |
| CS-02 | Missing, stale, conflicting or out-of-scope data fail closed | clinical kernel coverage states | kernel fixtures | Preclinical | Clinical safety | Coverage breadth incomplete |
| LM-01 | Model output is candidate-only, grounded and snapshot-bound | `PrivacyMinimizedModelBroker`; strict contracts | relay and gateway tests | Disabled | Model evaluation | No qualified external model/task pair |
| EV-01 | Runtime evidence is signed/hash-pinned and offline | release manifest and cardiometabolic pack | artifact-integrity test | Preclinical | Clinical content | Provenance, licensing and independent review register incomplete |
| LO-01 | Burmese/English structured parity | shared codes and bilingual pack fields | limited kernel fixtures | Preclinical | Language review | No qualified Burmese reviewer or comprehension study |
| PS-01 | No plaintext PHI in relay/push/log surfaces | opaque relay schema; generic push constant | relay inspection tests | Preclinical | Privacy + security | No independent penetration test or log-capture audit |
| OP-01 | Honest reminders and delivery states | push worker, PWA service worker | push policy tests | Preclinical | Operations | No live provider/browser delivery drill |
| OP-02 | Kill, rollback, revocation and outage recovery | release manifest capability states; offline fallback | partial tests | Preclinical | Operations + safety | Automated incident/failure-injection suite incomplete |
| CE-01 | Meet locked clinical performance thresholds | evaluation design in implementation plan | None | Blocked | Independent clinical evaluators | Corpus, adjudication and external holdout absent |
| HF-01 | ≥90% emergency-action comprehension | intended human-factors gate | None | Blocked | Independent UX/language study | Approved representative participants absent |
| GV-01 | Named clinical, language, privacy, legal and regulatory authorization | promotion-gate documentation | None | Blocked | External accountable organizations | Owners and signed determinations absent |

## Evidence rules

- Structural presence is not functional proof.
- Local tests do not establish clinical effectiveness, production operation, legal compliance or human comprehension.
- “Blocked” means an intrinsic external decision or study is missing; preparation continues locally.
- Any release-enabling change requires a new manifest, regression evidence and explicit accountable approval.
