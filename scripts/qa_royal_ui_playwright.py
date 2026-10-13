#!/usr/bin/env python3
"""Playwright walkthrough of royal UI (desktop + mobile) on a Cloud-like Streamlit run."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ARTIFACTS = Path(os.environ.get("QA_SCREENSHOT_DIR", "/opt/cursor/artifacts/screenshots"))
PORT = int(os.environ.get("QA_STREAMLIT_PORT", "8521"))


def _start_streamlit(work_dir: Path) -> subprocess.Popen[bytes]:
    env = os.environ.copy()
    env["INVESTING_WORK_DIR"] = str(work_dir)
    env["INVESTING_UI_RESEARCH_OFFLINE"] = "1"
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


def _wait_healthy(base: str, process: subprocess.Popen[bytes]) -> None:
    for _ in range(45):
        try:
            import urllib.request

            urllib.request.urlopen(f"{base}/_stcore/health", timeout=2)
            return
        except Exception:
            if process.poll() is not None:
                stderr = (process.stderr.read() if process.stderr else b"").decode()
                raise RuntimeError(f"Streamlit exited early: {stderr}")
            time.sleep(1)
    raise RuntimeError("Streamlit did not become healthy")


sys.path.insert(0, str(ROOT / "scripts"))
from qa_streamlit_nav import click_sidebar_section as _nav_section  # noqa: E402


def _capture_sections(page, prefix: str) -> None:
    from src.investing.sidebar_nav import SIDEBAR_SECTIONS

    for label in SIDEBAR_SECTIONS:
        _nav_section(page, label)
        page.wait_for_timeout(1500)
        safe = label.lower().replace(" ", "-")
        page.screenshot(path=str(ARTIFACTS / f"{prefix}-nav-{safe}.png"), full_page=True)


def main() -> int:
    from playwright.sync_api import sync_playwright

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    work_dir = Path(tempfile.mkdtemp(prefix="royal-ui-qa-"))
    process = _start_streamlit(work_dir)
    base = f"http://127.0.0.1:{PORT}"
    try:
        _wait_healthy(base, process)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)

            desktop = browser.new_page(viewport={"width": 1440, "height": 1200})
            desktop.goto(base, wait_until="domcontentloaded", timeout=120_000)
            desktop.wait_for_selector("text=Menu", timeout=120_000)
            desktop.screenshot(path=str(ARTIFACTS / "royal-before-desktop-home.png"), full_page=True)
            _nav_section(desktop, "About")
            desktop.wait_for_timeout(1500)
            desktop.wait_for_selector("text=Privacy & safety", timeout=30_000)
            desktop.screenshot(path=str(ARTIFACTS / "royal-about-page-desktop.png"), full_page=True)
            _capture_sections(desktop, "royal-before-desktop")

            _nav_section(desktop, "Portfolio")
            desktop.get_by_role(
                "button",
                name="Try demo portfolio first (no files needed)",
            ).click()
            desktop.wait_for_timeout(5000)
            desktop.screenshot(path=str(ARTIFACTS / "royal-after-desktop-portfolio.png"), full_page=True)

            _nav_section(desktop, "Snapshots")
            desktop.get_by_role("button", name="Run research").first.click()
            desktop.wait_for_timeout(15000)
            desktop.screenshot(path=str(ARTIFACTS / "royal-after-desktop-research.png"), full_page=True)
            _capture_sections(desktop, "royal-after-desktop")

            mobile = browser.new_page(viewport={"width": 390, "height": 844})
            mobile.goto(base, wait_until="domcontentloaded", timeout=120_000)
            mobile.wait_for_selector("text=Menu", timeout=120_000)
            mobile.screenshot(path=str(ARTIFACTS / "royal-after-mobile-home.png"), full_page=True)
            _nav_section(mobile, "My mutual funds")
            mobile.wait_for_timeout(3000)
            mobile.screenshot(path=str(ARTIFACTS / "royal-after-mobile-mf.png"), full_page=True)

            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=10)
    print(f"Royal UI screenshots saved to {ARTIFACTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
