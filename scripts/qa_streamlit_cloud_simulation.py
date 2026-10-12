#!/usr/bin/env python3
"""Simulate Streamlit Cloud: fresh deps, foreign cwd, streamlit_app.py, Playwright."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = Path(os.environ.get("QA_SCREENSHOT_DIR", "/opt/cursor/artifacts/screenshots"))
PORT = int(os.environ.get("QA_STREAMLIT_PORT", "8520"))


def _start_streamlit(work_dir: Path) -> subprocess.Popen[bytes]:
    env = os.environ.copy()
    env["INVESTING_WORK_DIR"] = str(work_dir)
    env["INVESTING_UI_RESEARCH_OFFLINE"] = "1"
    env.pop("INVESTING_PORTFOLIO_DB", None)
    env.pop("INVESTING_RESEARCH_DB", None)
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


def main() -> int:
    from playwright.sync_api import sync_playwright

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    work_dir = Path(tempfile.mkdtemp(prefix="streamlit-cloud-qa-"))
    process = _start_streamlit(work_dir)
    base = f"http://127.0.0.1:{PORT}"
    try:
        for _ in range(45):
            try:
                import urllib.request

                urllib.request.urlopen(f"{base}/_stcore/health", timeout=2)
                break
            except Exception:
                if process.poll() is not None:
                    stderr = (process.stderr.read() if process.stderr else b"").decode()
                    raise RuntimeError(f"Streamlit exited early: {stderr}")
                time.sleep(1)
        else:
            raise RuntimeError("Streamlit did not become healthy")

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1200})
            page.goto(base, wait_until="domcontentloaded", timeout=120_000)
            page.wait_for_selector("text=Your wealth at a glance", timeout=120_000)

            def click_tab(label: str) -> None:
                page.get_by_role("tab", name=label).click()

            click_tab("Portfolio")
            page.wait_for_timeout(2000)
            page.screenshot(
                path=str(ARTIFACTS / "cloud-portfolio-step1-guide.png"),
                full_page=True,
            )
            page.get_by_role(
                "button",
                name="Try demo portfolio first (no files needed)",
            ).click()
            page.wait_for_timeout(8000)
            page.screenshot(
                path=str(ARTIFACTS / "cloud-portfolio-after-demo.png"),
                full_page=True,
            )

            sample = ROOT / "examples/zerodha_portfolio/equity_holdings.example.csv"
            page.locator('input[type="file"]').first.set_input_files(str(sample))
            page.wait_for_timeout(4000)
            page.screenshot(
                path=str(ARTIFACTS / "cloud-portfolio-after-upload.png"),
                full_page=True,
            )

            click_tab("Stock Research")
            page.wait_for_timeout(500)
            page.get_by_role("tab", name="Snapshots").click()
            page.wait_for_timeout(1000)
            page.screenshot(path=str(ARTIFACTS / "cloud-tab-snapshots-empty.png"), full_page=True)
            page.get_by_role("button", name="Run research").first.click()
            page.wait_for_timeout(15000)
            page.screenshot(path=str(ARTIFACTS / "cloud-tab-snapshots-after-research.png"), full_page=True)

            page.get_by_role("tab", name="Profile review").click()
            page.wait_for_timeout(2000)
            page.screenshot(path=str(ARTIFACTS / "cloud-tab-profile.png"), full_page=True)

            page.get_by_role("tab", name="Orchestration runs").click()
            page.wait_for_timeout(1000)
            page.screenshot(path=str(ARTIFACTS / "cloud-tab-orchestration.png"), full_page=True)

            click_tab("Top Mutual Funds")
            page.wait_for_timeout(2000)
            page.screenshot(path=str(ARTIFACTS / "cloud-tab-top-mf.png"), full_page=True)

            click_tab("My Mutual Funds")
            page.wait_for_timeout(5000)
            page.screenshot(path=str(ARTIFACTS / "cloud-portfolio-mf-charts.png"), full_page=True)
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=10)
    print(f"Cloud simulation screenshots saved to {ARTIFACTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
