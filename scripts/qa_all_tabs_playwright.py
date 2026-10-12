#!/usr/bin/env python3
"""Click every top-level tab on desktop and mobile; capture screenshots."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = Path(os.environ.get("QA_SCREENSHOT_DIR", "/opt/cursor/artifacts/screenshots"))
PORT = int(os.environ.get("QA_STREAMLIT_PORT", "8523"))

TOP_TABS = (
    "Wealth at a glance",
    "Portfolio",
    "My Mutual Funds",
    "Top Mutual Funds",
    "Snapshots",
    "Profile review",
    "Orchestration runs",
)


def _start(work_dir: Path) -> subprocess.Popen[bytes]:
    env = os.environ.copy()
    env["INVESTING_WORK_DIR"] = str(work_dir)
    env["INVESTING_UI_RESEARCH_OFFLINE"] = "1"
    env["INVESTING_AUTO_DEMO_PORTFOLIO"] = "1"
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(ROOT / "streamlit_app.py"),
            "--server.headless",
            "true",
            "--server.port",
            str(PORT),
        ],
        cwd="/tmp",
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


def _healthy(base: str, process: subprocess.Popen[bytes]) -> None:
    for _ in range(45):
        try:
            import urllib.request

            urllib.request.urlopen(f"{base}/_stcore/health", timeout=2)
            return
        except Exception:
            if process.poll() is not None:
                raise RuntimeError((process.stderr.read() if process.stderr else b"").decode())
            time.sleep(1)
    raise RuntimeError("Streamlit not healthy")


def _visit_tabs(page, prefix: str) -> None:
    from playwright.sync_api import expect

    for label in TOP_TABS:
        tab = page.get_by_role("tab", name=label)
        expect(tab).to_be_visible(timeout=30_000)
        tab.click()
        page.wait_for_timeout(2000)
        safe = label.lower().replace(" ", "-")
        page.screenshot(path=str(ARTIFACTS / f"{prefix}-tab-{safe}.png"), full_page=True)
    expect(page.locator('[data-testid="stException"]')).to_have_count(0)


def main() -> int:
    from playwright.sync_api import sync_playwright

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    work_dir = Path(tempfile.mkdtemp(prefix="all-tabs-qa-"))
    process = _start(work_dir)
    base = f"http://127.0.0.1:{PORT}"
    try:
        _healthy(base, process)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)

            desktop = browser.new_page(viewport={"width": 1440, "height": 1200})
            desktop.goto(base, wait_until="domcontentloaded", timeout=120_000)
            desktop.wait_for_selector("text=Wealth at a glance", timeout=120_000)
            _visit_tabs(desktop, "pro-tabs-desktop")

            mobile = browser.new_page(viewport={"width": 390, "height": 844})
            mobile.goto(base, wait_until="domcontentloaded", timeout=120_000)
            mobile.wait_for_selector("text=Wealth at a glance", timeout=120_000)
            _visit_tabs(mobile, "pro-tabs-mobile")

            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=10)
    print(f"All-tabs screenshots saved to {ARTIFACTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
