#!/usr/bin/env python3
"""Verify every dashboard section is reachable from the sidebar (desktop + mobile)."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
ARTIFACTS = Path(os.environ.get("QA_SCREENSHOT_DIR", "/tmp/qa-screenshots"))
PORT = int(os.environ.get("QA_STREAMLIT_PORT", "8531"))

from src.investing.sidebar_nav import SIDEBAR_SECTIONS

SECTIONS = SIDEBAR_SECTIONS


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


from qa_streamlit_nav import click_sidebar_section


def _visit_sections(page, prefix: str) -> None:
    from playwright.sync_api import expect

    for label in SECTIONS:
        if label != "Dashboard":
            click_sidebar_section(page, label)
        expect(page.locator('[data-testid="stException"]')).to_have_count(0)
        if page.get_by_text("We hit a snag").count():
            raise AssertionError(f"Friendly error shown on section: {label}")
        safe = label.lower().replace(" ", "-").replace("&", "and")
        page.screenshot(path=str(ARTIFACTS / f"{prefix}-nav-{safe}.png"), full_page=True)


def main() -> int:
    from playwright.sync_api import sync_playwright

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    work_dir = Path(tempfile.mkdtemp(prefix="sidebar-nav-qa-"))
    process = _start(work_dir)
    base = f"http://127.0.0.1:{PORT}"
    try:
        _healthy(base, process)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)

            desktop = browser.new_page(viewport={"width": 1440, "height": 1200})
            desktop.goto(base, wait_until="domcontentloaded", timeout=120_000)
            desktop.wait_for_selector("text=Wealth home", timeout=120_000)
            desktop.wait_for_selector("text=Showing example data", timeout=60_000)
            desktop.screenshot(path=str(ARTIFACTS / "demo-banner-desktop.png"), full_page=False)
            _visit_sections(desktop, "sidebar-desktop")
            click_sidebar_section(desktop, "Portfolio")
            desktop.wait_for_timeout(1500)
            desktop.screenshot(path=str(ARTIFACTS / "portfolio-xirr-desktop.png"), full_page=True)

            mobile = browser.new_page(viewport={"width": 390, "height": 1200})
            mobile.goto(base, wait_until="domcontentloaded", timeout=120_000)
            mobile.wait_for_selector("text=Wealth home", timeout=120_000)
            _visit_sections(mobile, "sidebar-mobile")

            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=10)
    print(f"Sidebar navigation screenshots saved to {ARTIFACTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
