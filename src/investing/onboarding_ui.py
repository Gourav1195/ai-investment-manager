"""Guided first-run experience for Zerodha portfolio upload."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from .app_preferences import AppPreferences
from .portfolio_dashboard_data import portfolio_has_data
from .portfolio_service import load_example_portfolio
from .portfolio_store import PortfolioStore
from .repo_bootstrap import repo_root
from .royal_theme import render_empty_state


GUIDE_SVG = repo_root() / "docs" / "assets" / "zerodha-console-export-guide.svg"


def render_first_run_wizard(
    portfolio_path: Path,
    prefs: AppPreferences,
    *,
    import_panel_renderer,
) -> bool:
    """Return True when step 1 is showing (no holdings yet)."""

    has_data = portfolio_path.exists() and portfolio_has_data(portfolio_path)
    if has_data:
        if not prefs.get_onboarding_complete():
            prefs.set_onboarding_complete(True)
        _render_step_two_banner()
        return False

    st.markdown(
        '<p class="royal-onboarding-badge">Step 1 of 2 — Add your Zerodha files</p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        "### Bring your portfolio here in a few clicks\n"
        "Download files from **Zerodha Console** on the web — no coding or API keys."
    )

    with st.expander("Where do I download these files in Console?", expanded=True):
        if GUIDE_SVG.exists():
            try:
                st.image(str(GUIDE_SVG), use_container_width=True)
            except Exception:
                st.caption("Picture guide skipped — follow the numbered steps below.")
        st.markdown(
            """
1. Log in to **[Zerodha Console](https://console.zerodha.com/)** (website, not the Kite app).
2. Click **Reports** on the left.
3. **Stocks you own** — *Reports → Holdings → Equity* → download **CSV** or **Excel**.
4. **Mutual funds** — *Reports → Holdings → Mutual funds* → download.
5. **Trade history** (optional) — *Reports → Tradebook* → choose dates → download (helps charts and annual return).

Upload below. You can start with only the equity file and add others later.
            """
        )

    st.button(
        "Try demo portfolio first (no files needed)",
        type="primary",
        use_container_width=True,
        key="onboarding_demo_portfolio",
        help="Sample Indian stocks and mutual funds — safe way to explore the app.",
        on_click=_load_demo_portfolio,
        args=(portfolio_path, prefs),
    )

    import_panel_renderer(portfolio_path, compact=True)
    render_empty_state(
        "📥",
        "Waiting for your files",
        "Tap the demo button above to preview instantly, or upload Console exports below.",
    )
    return True


def _load_demo_portfolio(portfolio_path: Path, prefs: AppPreferences) -> None:
    portfolio_path = Path(portfolio_path)
    portfolio_path.parent.mkdir(parents=True, exist_ok=True)
    store = PortfolioStore(portfolio_path)
    load_example_portfolio(store)
    prefs.set_onboarding_complete(True)


def maybe_auto_load_demo_for_qa(portfolio_path: Path, prefs: AppPreferences) -> None:
    import os

    if os.environ.get("INVESTING_AUTO_DEMO_PORTFOLIO", "").strip().lower() not in {
        "1",
        "true",
        "yes",
    }:
        return
    if portfolio_path.exists() and portfolio_has_data(portfolio_path):
        return
    _load_demo_portfolio(portfolio_path, prefs)


def _render_step_two_banner() -> None:
    st.markdown(
        '<p class="royal-onboarding-badge royal-onboarding-badge--done">'
        "Step 2 of 2 — Your portfolio is connected</p>",
        unsafe_allow_html=True,
    )
    st.success("Scroll down to see your holdings, charts, and fund comparisons.")
