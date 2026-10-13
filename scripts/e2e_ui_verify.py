"""End-to-end UI checks for sidebar, research, and portfolio flows."""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from qa_streamlit_nav import click_sidebar_section, open_sidebar_if_collapsed


def verify(url: str) -> None:
    errors: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.goto(url, wait_until="networkidle", timeout=120_000)
        page.wait_for_timeout(4500)

        open_sidebar_if_collapsed(page)
        brand = page.locator(".royal-sidebar-brand")
        collapse = page.locator('[data-testid="stSidebarCollapseButton"]')
        if not brand.count():
            errors.append("missing sidebar brand")
        if not collapse.count():
            errors.append("missing sidebar collapse control")
        elif brand.count():
            box_b = brand.first.bounding_box()
            box_c = collapse.first.bounding_box()
            if box_b and box_c:
                overlap = abs(box_b["y"] - box_c["y"]) < 40
                if not overlap:
                    errors.append(
                        f"brand y={box_b['y']:.0f} not aligned with collapse y={box_c['y']:.0f}"
                    )

        if page.get_by_text("Portfolio to view").count():
            errors.append("demo/my portfolio segmented control still visible")

        click_sidebar_section(page, "Run research")
        main = page.locator('[data-testid="stMain"]')
        run_btn = main.locator("button").filter(has_text="Run research")
        for candidate in run_btn.all():
            if candidate.is_visible():
                candidate.click()
                break
        page.wait_for_timeout(20000)
        if not page.get_by_text("Latest saved snapshots").count():
            errors.append("run research page missing latest snapshots section")
        if page.get_by_text("Evaluations").count() == 0:
            errors.append("run research page missing overview metrics after run")

        click_sidebar_section(page, "Snapshots")
        page.wait_for_timeout(1500)
        if not page.get_by_text("Your research library").count():
            errors.append("saved research page missing library description")

        click_sidebar_section(page, "My mutual funds")
        page.wait_for_timeout(2500)
        if page.get_by_text("Something went wrong", exact=False).count():
            errors.append("my mutual funds page crashed")
        if page.get_by_text("mutual fund charts", exact=False).count() == 0 and page.get_by_text(
            "No mutual fund holdings", exact=False
        ).count() == 0:
            errors.append("my mutual funds page did not render expected content")

        click_sidebar_section(page, "Dashboard")
        page.wait_for_timeout(1500)
        if not page.get_by_text("example data", exact=False).count():
            errors.append("dashboard missing demo/example data banner")

        collapse.first.click()
        page.wait_for_timeout(700)
        if page.locator('[data-testid="stSidebar"][aria-expanded="false"]').count() == 0:
            errors.append("sidebar did not collapse")

        browser.close()

    if errors:
        print("E2E FAILED:")
        for item in errors:
            print(f"  - {item}")
        sys.exit(1)
    print("E2E OK: sidebar, research flows, and demo portfolio banner verified")


if __name__ == "__main__":
    verify(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8501")
