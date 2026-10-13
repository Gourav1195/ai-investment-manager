"""Shared Playwright helpers for sidebar section navigation."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.investing.sidebar_nav import DISPLAY_LABELS, SIDEBAR_SECTIONS


def open_sidebar_if_collapsed(page) -> None:
    sidebar = page.locator('[data-testid="stSidebar"]')
    if sidebar.count() and sidebar.get_attribute("aria-expanded") == "false":
        header_toggle = page.locator('[data-testid="stHeader"] button')
        if header_toggle.count() and header_toggle.first.is_visible():
            header_toggle.first.click()
            page.wait_for_timeout(700)
            return
    control = page.locator('[data-testid="collapsedControl"]')
    if control.count() and control.first.is_visible():
        control.first.click()
        page.wait_for_timeout(600)


def _button_label(section: str) -> str:
    return DISPLAY_LABELS.get(section, section)


def click_sidebar_section(page, section: str) -> None:
    if section not in SIDEBAR_SECTIONS:
        raise ValueError(f"Unknown section: {section}")
    open_sidebar_if_collapsed(page)
    sidebar = page.locator('section[data-testid="stSidebar"]')
    button_name = _button_label(section)
    content = sidebar.locator('[data-testid="stSidebarContent"]')
    content.evaluate("el => { el.scrollTop = 0; }")
    buttons = sidebar.locator("button").filter(has_text=button_name)
    page.wait_for_timeout(400)
    if buttons.count() == 0:
        buttons = sidebar.get_by_role("button", name=button_name)
    if buttons.count() == 0:
        raise RuntimeError(f"Sidebar button not found: {section} ({button_name})")
    target = buttons.first
    for candidate in buttons.all():
        if candidate.is_visible():
            target = candidate
            break
    target.scroll_into_view_if_needed()
    target.click()
    page.wait_for_timeout(2500)
