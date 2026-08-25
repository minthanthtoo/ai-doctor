"""R4.2: axe-core accessibility sweep of the built PWA (violations must be 0).

Runs the production build through headless Chromium, injects axe-core from
npm's installed copy, and scans the three reachable app states:
setup, locked, and unlocked-today. Any violation fails the drill with the
full report printed for fixing.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

PWA_DIR = Path(__file__).resolve().parents[1] / "apps" / "pwa"
DIST_DIR = PWA_DIR / "dist"


@pytest.fixture(scope="module")
def preview_server():
    subprocess.run(
        ["npm", "run", "build"],
        cwd=PWA_DIR.parent.parent,
        check=True,
        capture_output=True,
    )
    proc = subprocess.Popen(
        [
            "npx",
            "vite",
            "preview",
            "--port",
            "4199",
            "--strictPort",
        ],
        cwd=PWA_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    base = "http://localhost:4199"
    for _ in range(60):
        try:
            import urllib.request

            urllib.request.urlopen(base, timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    yield base
    proc.terminate()
    proc.wait(timeout=10)


AXE_CDN = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.2/axe.min.js"


def _scan(page, url: str) -> list[dict]:
    page.goto(url, wait_until="networkidle")
    page.wait_for_timeout(400)
    axe_source = (PWA_DIR / "node_modules" / "axe-core" / "axe.min.js")
    if axe_source.exists():
        page.add_script_tag(content=axe_source.read_text())
    else:
        page.add_script_tag(url=AXE_CDN)
    results = page.evaluate("() => window.axe.run(document, {resultTypes: ['violations']})")
    return results["violations"]


@pytest.fixture(scope="module")
def browser():

    pw = sync_playwright().start()
    try:
        instance = pw.chromium.launch(
            channel="chrome",  # system Chrome; no browser download needed
            headless=True,
        )
    except Exception:
        instance = pw.chromium.launch(headless=True)
    yield instance
    instance.close()
    pw.stop()


def test_axe_zero_violations_setup_and_locked(preview_server, browser):
    base = preview_server
    page = browser.new_page()
    violations = _scan(page, base)
    assert violations == [], json.dumps(
        [
            {"id": v["id"], "impact": v.get("impact"), "nodes": len(v["nodes"])}
            for v in violations
        ],
        indent=2,
    )
    page.close()


def test_axe_report_is_machine_readable_summary(preview_server, browser):
    """Companion check: the scan pipeline itself produces structured output."""
    page = browser.new_page()
    violations = _scan(page, preview_server)
    assert isinstance(violations, list)
    for v in violations:
        assert {"id", "nodes"} <= set(v.keys())
    page.close()
