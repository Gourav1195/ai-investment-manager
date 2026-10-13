"""Shared Playwright helpers for sidebar section navigation."""

from __future__ import annotations

from src.investing.sidebar_nav import DISPLAY_LABELS, SIDEBAR_SECTIONS


def open_sidebar_if_collapsed(page) -> None:
    control = page.locator('[data-testid="collapsedControl"]')
    if control.count() and control.first.is_visible():
        control.first.click()
        page.wait_for_timeout(600)


def _button_label(section: str) -> str:
    return DISPLAY_LABELS.get(section, section)


def click_sidebar_section(page, label: str) -> None:
    if label not in SIDEBAR_SECTIONS:
        raise ValueError(f"Unknown section: {label}")
    open_sidebar_if_collapsed(page)
    sidebar = page.locator('section[data-testid="stSidebar"]')
    button_name = _button_label(label)
    content = sidebar.locator('[data-testid="stSidebarContent"]')
    content.evaluate("el => { el.scrollTop = 0; }")
    buttons = sidebar.get_by_role("button").filter(has_text=button_name)
    if buttons.count() == 0:
        buttons = sidebar.get_by_role("button", name=button_name)
    buttons.first.scroll_into_view_if_needed()
    buttons.first.evaluate("el => el.click()")
    page.wait_for_timeout(1500)
