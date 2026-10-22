#!/usr/bin/env python3
# Legacy full-dashboard tour. For CI smoke tests use scripts/e2e_ui_verify.py instead.
"""Drive the Streamlit dashboard in a real browser and save tab screenshots."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = Path(os.environ.get("QA_SCREENSHOT_DIR", "/opt/cursor/artifacts/screenshots"))
PORT = int(os.environ.get("QA_STREAMLIT_PORT", "8510"))


def _seed_databases(work: Path) -> None:
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    subprocess.run(
        [
            sys.executable,
            "-m",
            "src.investing.cli",
            "portfolio",
            "load-examples",
            "--database",
            str(work / "portfolio.db"),
        ],
        cwd=ROOT,
        env=env,
        check=True,
    )
    subprocess.run(
        [
            sys.executable,
            "-m",
            "src.investing.cli",
            "portfolio",
            "sync-mf-master",
            "--database",
            str(work / "portfolio.db"),
            "--input",
            str(ROOT / "examples/zerodha_portfolio/amfi_nav_sample.txt"),
        ],
        cwd=ROOT,
        env=env,
        check=True,
    )
    research = work / "research.db"
    if not research.exists():
        from tests.test_dashboard import _seed_research_store

        _seed_research_store(research)


def _start_streamlit(work: Path) -> subprocess.Popen[bytes]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    env["INVESTING_PORTFOLIO_DB"] = str(work / "portfolio.db")
    env["INVESTING_RESEARCH_DB"] = str(work / "research.db")
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
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main() -> int:
    from playwright.sync_api import sync_playwright

    work = ROOT / "work" / "qa-e2e"
    work.mkdir(parents=True, exist_ok=True)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    _seed_databases(work)
    process = _start_streamlit(work)
    base = f"http://127.0.0.1:{PORT}"
    try:
        for _ in range(30):
            try:
                import urllib.request

                urllib.request.urlopen(f"{base}/_stcore/health", timeout=2)
                break
            except Exception:
                time.sleep(1)
        else:
            raise RuntimeError("Streamlit did not become healthy")

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1200})
            page.goto(base, wait_until="domcontentloaded", timeout=120_000)
            page.wait_for_selector("text=India Long-Term Research Dashboard", timeout=120_000)
            page.wait_for_timeout(3000)

            def click_tab(label: str) -> None:
                tablist = page.locator('[data-testid="stTabs"]')
                tablist.get_by_text(label, exact=True).click()

            tabs = [
                ("snapshots", "Snapshots"),
                ("profile-review", "Profile review"),
                ("orchestration", "Orchestration runs"),
                ("portfolio", "Portfolio"),
            ]
            for slug, label in tabs:
                click_tab(label)
                page.wait_for_timeout(2000)
                if label == "Portfolio":
                    refresh = page.locator("label").filter(
                        has_text="Refresh live prices and NAVs"
                    )
                    if refresh.count():
                        refresh.click()
                    page.wait_for_timeout(500)
                page.screenshot(path=str(ARTIFACTS / f"dashboard-tab-{slug}.png"), full_page=True)

            click_tab("Profile review")
            page.wait_for_timeout(800)
            if page.get_by_text("Activate candidate profile").count():
                page.locator("label").filter(
                    has_text="I reviewed the threshold diff"
                ).first.click()
            page.screenshot(
                path=str(ARTIFACTS / "dashboard-profile-activation.png"),
                full_page=True,
            )

            click_tab("Portfolio")
            page.wait_for_timeout(800)
            manual = page.get_by_text("Manual fund comparison")
            if manual.count():
                manual.scroll_into_view_if_needed()
            page.screenshot(
                path=str(ARTIFACTS / "dashboard-mf-manual-compare.png"),
                full_page=True,
            )
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=10)
    print(f"Saved screenshots under {ARTIFACTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
