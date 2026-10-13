"""Capture Streamlit sidebar and research page screenshots for QA artifacts."""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from qa_streamlit_nav import open_sidebar_if_collapsed


def _click_nav(page, label: str) -> None:
    open_sidebar_if_collapsed(page)
    sidebar = page.locator('section[data-testid="stSidebar"]')
    button = sidebar.locator("button").filter(has_text=label)
    if button.count():
        button.first.click()
        page.wait_for_timeout(2000)


def capture(url: str, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.goto(url, wait_until="networkidle", timeout=120_000)
        page.wait_for_timeout(3000)
        open_sidebar_if_collapsed(page)
        page.wait_for_timeout(800)
        page.screenshot(path=str(out_dir / "sidebar-expanded.png"), full_page=False)

        # Collapse sidebar via header control if present.
        collapse = page.locator('[data-testid="stSidebarCollapseButton"]')
        if collapse.count():
            collapse.first.click()
            page.wait_for_timeout(800)
            page.screenshot(path=str(out_dir / "sidebar-collapsed.png"), full_page=False)
            open_sidebar_if_collapsed(page)
            page.wait_for_timeout(600)

        _click_nav(page, "Run research")
        page.wait_for_timeout(1500)
        main = page.locator('[data-testid="stMain"]')
        run_btn = main.locator("button").filter(has_text="Run research")
        for candidate in run_btn.all():
            if candidate.is_visible():
                candidate.click()
                break
        page.wait_for_timeout(20000)
        page.screenshot(path=str(out_dir / "run-research-result.png"), full_page=True)
        browser.close()


if __name__ == "__main__":
    base = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/opt/cursor/artifacts/screenshots")
    capture("http://localhost:8501", base)
