"""Portfolio empty state helpers (no full-screen onboarding gate)."""

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


def render_portfolio_empty_state(portfolio_path: Path, prefs: AppPreferences) -> None:
    """Inline upload help on the Portfolio page — does not block the Dashboard."""

    st.markdown(
        "### Add your Zerodha holdings\n"
        "Download exports from **[Zerodha Console](https://console.zerodha.com/)** "
        "(Reports → Holdings) and upload below, or try the demo."
    )
    if GUIDE_SVG.exists():
        try:
            st.image(str(GUIDE_SVG), use_container_width=True)
        except Exception:
            pass

    st.button(
        "Try demo portfolio (sample data)",
        type="primary",
        use_container_width=True,
        key="portfolio_demo_button",
        on_click=_load_demo_portfolio,
        args=(portfolio_path, prefs),
    )

    from .portfolio_cloud_ui import render_portfolio_import_panel

    render_portfolio_import_panel(portfolio_path, compact=True)
    render_empty_state(
        "📥",
        "No holdings yet",
        "Use the demo button above or upload a Console export.",
    )


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


# Backward compatibility for tests/scripts that still import the old name.
def render_first_run_wizard(
    portfolio_path: Path,
    prefs: AppPreferences,
    *,
    import_panel_renderer,
) -> bool:
    render_portfolio_empty_state(portfolio_path, prefs)
    return True
