# Security and safety incident register

No production incidents are recorded because no clinical production deployment is authorized.

| ID | Detected | Severity | Release | Description | Containment | Evidence preserved | Owner | Status |
|---|---|---|---|---|---|---|---|---|
| PRE-001 | 2026-08-12 | High, preclinical finding | `1cb4619` | Any patient bearer token could previously supply another opaque profile ID to relay routes | Added principal/profile enrollment binding, per-route ownership, device-key verification and cross-tenant tests | Git diff, test output and decision record | Engineering/security | Remediated locally; independent review pending |

For a real incident, preserve timestamps, affected release and decision IDs, encrypted payload hashes, relevant metadata-access logs, containment actions, notification decisions, restoration criteria and accountable approvals. Never place plaintext PHI in this register.
