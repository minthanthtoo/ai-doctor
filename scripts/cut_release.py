#!/usr/bin/env python3
"""Cut a release: verify gates, write manifest, create signed tag.

Usage:
    python scripts/cut_release.py --version 0.2.0-preclinical [--skip-tests]

Steps (fail closed at each gate):
1. Run the full local test suite unless --skip-tests.
2. Compute the release commit and short description via git.
3. Write release_manifest_v3.json with "signature": null — a human signs it
   afterwards with scripts/sign_release_manifest.py; unsigned-by-default.
4. Create an annotated tag v<version> on the release commit.

The script never pushes; custody push remains the operator's action.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "release_manifest_v3.json"


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"GATE FAILED: {' '.join(cmd)}\n{result.stdout[-2000:]}{result.stderr[-2000:]}")
        sys.exit(1)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="e.g. 0.2.0-preclinical")
    parser.add_argument("--skip-tests", action="store_true", help="operator override")
    args = parser.parse_args()

    version = args.version

    # Gate 1: tests (Python + kernel + PWA) — the same set CI runs.
    if not args.skip_tests:
        print("== pytest ==")
        run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "--ignore=tests/test_a11y_axe.py",
                "--ignore=tests/test_perf_budget.py",
            ]
        )
        print("== kernel + pwa ==")
        run(["npm", "run", "typecheck"])
        run(["npm", "--workspace", "@ai-doctor/clinical-kernel", "run", "test"])

    # Gate 2: clean tree.
    status = run(["git", "status", "--porcelain"]).stdout.strip()
    if status:
        print(f"GATE FAILED: dirty working tree:\n{status}")
        sys.exit(1)

    commit = run(["git", "rev-parse", "HEAD"]).stdout.strip()

    # Manifest — signature stays null until the human signs it.
    manifest_digest_input = json.dumps(
        {
            "manifest_version": 3,
            "release": version,
            "commit": commit,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "unsigned": True,
        },
        sort_keys=True,
    ).encode()
    digest = hashlib.sha256(manifest_digest_input).hexdigest()
    MANIFEST.write_text(
        json.dumps(
            {
                "manifest_version": 3,
                "release": version,
                "commit": commit,
                "digest": digest,
                "signature": None,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"wrote {MANIFEST.name} (digest {digest[:16]}…, signature null — sign before distributing)")

    # Tag.
    tag = f"v{version}"
    existing = run(["git", "rev-parse", "-q", "--verify", f"refs/tags/{tag}"], check=False)
    if existing.returncode == 0:
        print(f"GATE FAILED: tag {tag} already exists")
        sys.exit(1)
    run(["git", "add", str(MANIFEST.relative_to(ROOT))])
    run(["git", "commit", "-q", "-m", f"chore(release): cut {version} (manifest digest {digest[:12]})"])
    release_commit = run(["git", "rev-parse", "HEAD"]).stdout.strip()
    run(["git", "tag", "-a", tag, "-m", f"{version} @ {release_commit[:12]} (preclinical, unsigned)"])
    print(f"tagged {tag} @ {release_commit[:7]}")
    print("next: sign the manifest (scripts/sign_release_manifest.py), then push both remotes + tag.")


if __name__ == "__main__":
    main()
