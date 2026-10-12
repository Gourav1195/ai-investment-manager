#!/usr/bin/env python3
"""Playwright walkthrough as a first-time, non-technical user."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = Path(os.environ.get("QA_SCREENSHOT_DIR", "/opt/cursor/artifacts/screenshots"))
PORT = int(os.environ.get("QA_STREAMLIT_PORT", "8522"))


def _wait_healthy(base: str, process: subprocess.Popen[bytes]) -> None:
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


def _start(work_dir: Path) -> subprocess.Popen[bytes]:
    env = os.environ.copy()
    env["INVESTING_WORK_DIR"] = str(work_dir)
    env["INVESTING_UI_RESEARCH_OFFLINE"] = "1"
    env.pop("INVESTING_AUTO_DEMO_PORTFOLIO", None)
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


def _seed_demo_portfolio(work_dir: Path) -> None:
    sys.path.insert(0, str(ROOT))
    from src.investing.app_preferences import AppPreferences
    from src.investing.onboarding_ui import _load_demo_portfolio
    from src.investing.portfolio_store import PortfolioStore

    portfolio_path = work_dir / "portfolio.db"
    prefs = AppPreferences(work_dir / "ui_prefs.json")
    _load_demo_portfolio(portfolio_path, prefs)


def main() -> int:
    from playwright.sync_api import expect, sync_playwright

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    work_dir = Path(tempfile.mkdtemp(prefix="first-time-user-"))
    process = _start(work_dir)
    base = f"http://127.0.0.1:{PORT}"
    try:
        _wait_healthy(base, process)

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 390, "height": 844})
            page.goto(base, wait_until="domcontentloaded", timeout=120_000)
            page.wait_for_selector("text=Your wealth at a glance", timeout=120_000)
            page.get_by_role("tab", name="Portfolio").click()
            page.wait_for_selector("text=Step 1 of 2", timeout=120_000)
            page.screenshot(path=str(ARTIFACTS / "first-time-step1-mobile.png"), full_page=True)

            expect(page.get_by_text("Where do I download these files in Console?")).to_be_visible()
            expect(page.locator('[data-testid="stException"]')).to_have_count(0)
            expect(
                page.get_by_role(
                    "button",
                    name="Try demo portfolio first (no files needed)",
                )
            ).to_be_visible()

            _seed_demo_portfolio(work_dir)
            page.reload(wait_until="domcontentloaded", timeout=120_000)
            page.wait_for_selector("text=Your wealth at a glance", timeout=120_000)
            expect(page.locator('[data-testid="stException"]')).to_have_count(0)
            page.get_by_role("tab", name="Portfolio").click()
            page.wait_for_selector("text=Money you put in", timeout=120_000)
            expect(page.locator('[data-testid="stException"]')).to_have_count(0)
            page.screenshot(path=str(ARTIFACTS / "first-time-step2-mobile.png"), full_page=True)

            page.get_by_role("tab", name="My Mutual Funds").click()
            page.wait_for_timeout(3000)
            page.screenshot(path=str(ARTIFACTS / "first-time-mf-tab-mobile.png"), full_page=True)

            desktop = browser.new_page(viewport={"width": 1440, "height": 1200})
            desktop.goto(base, wait_until="domcontentloaded", timeout=120_000)
            desktop.wait_for_selector("text=Your wealth at a glance", timeout=120_000)
            desktop.screenshot(path=str(ARTIFACTS / "first-time-desktop-home.png"), full_page=True)
            expect(desktop.locator('[data-testid="stException"]')).to_have_count(0)

            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=10)
    print(f"First-time user QA screenshots saved to {ARTIFACTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
