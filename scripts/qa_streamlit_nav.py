"""Shared Playwright helpers for sidebar section navigation."""

from __future__ import annotations


def open_sidebar_if_collapsed(page) -> None:
    control = page.locator('[data-testid="collapsedControl"]')
    if control.count() and control.first.is_visible():
        control.first.click()
        page.wait_for_timeout(600)


def click_sidebar_section(page, label: str) -> None:
    open_sidebar_if_collapsed(page)
    sidebar = page.locator('section[data-testid="stSidebar"]')
    content = sidebar.locator('[data-testid="stSidebarContent"]')
    content.evaluate("el => { el.scrollTop = 0; }")
    radio = sidebar.get_by_role("radio", name=label, exact=True)
    if radio.count() and radio.is_checked():
        page.wait_for_timeout(400)
        return
    radio_box = sidebar.locator('[data-testid="stRadio"]')
    radio_box.evaluate(
        """(el, label) => {
          const target = [...el.querySelectorAll('p')].find(
            (node) => node.textContent === label
          );
          if (target) target.scrollIntoView({ block: 'center' });
        }""",
        label,
    )
    radio_box.evaluate(
        """(el, label) => {
          const target = [...el.querySelectorAll('p')].find(
            (node) => node.textContent === label
          );
          if (target) target.click();
        }""",
        label,
    )
    page.wait_for_timeout(2000)
