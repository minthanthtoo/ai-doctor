"""R4.3: performance budget drill.

Lighthouse CLI needs a global install + Chrome launch flags that vary per
machine; the budget contract is enforced here directly against the built
bundle: parse dist/ asset sizes and the committed budget.json, fail when any
budget line is exceeded. Same numbers Lighthouse's resourceSize audit reads.
"""

from __future__ import annotations

import json
from pathlib import Path

PWA_DIR = Path(__file__).resolve().parents[1] / "apps" / "pwa"
DIST_DIR = PWA_DIR / "dist"
BUDGET_FILE = PWA_DIR / "budget.json"


def _dist_bytes() -> dict[str, int]:
    sizes: dict[str, int] = {}
    for asset in DIST_DIR.rglob("*"):
        if asset.is_file():
            rel = str(asset.relative_to(DIST_DIR))
            sizes[rel] = asset.stat().st_size
    return sizes


def test_bundle_fits_committed_budget():
    assert BUDGET_FILE.exists(), "budget.json missing"
    budgets = json.loads(BUDGET_FILE.read_text())[0]
    sizes = _dist_bytes()
    assert sizes, "dist/ missing — run npm run build first"

    script_budget_kb = next(
        b["budget"] for b in budgets["resourceSizes"] if b["resourceType"] == "script"
    )
    total_budget_kb = next(
        b["budget"] for b in budgets["resourceSizes"] if b["resourceType"] == "total"
    )
    script_count_budget = next(
        b["budget"] for b in budgets["resourceCounts"] if b["resourceType"] == "script"
    )

    scripts = {k: v for k, v in sizes.items() if k.endswith(".js") and not k.startswith("sw")}
    total_kb = sum(sizes.values()) / 1024
    script_kb = sum(scripts.values()) / 1024
    script_count = len(scripts)

    assert script_kb <= script_budget_kb, (
        f"JS bundle {script_kb:.0f}KB exceeds {script_budget_kb}KB budget"
    )
    assert total_kb <= total_budget_kb, f"total payload {total_kb:.0f}KB exceeds {total_budget_kb}KB"
    assert script_count <= script_count_budget, (
        f"{script_count} scripts exceed count budget {script_count_budget}"
    )


def test_service_worker_precache_stays_bounded():
    """The SW precaches dist/*; its manifest must stay under 1.5MB total."""
    sizes = _dist_bytes()
    precached = sum(sizes.values()) / 1024
    assert precached <= 1536, f"precache payload {precached:.0f}KB exceeds 1.5MB"
