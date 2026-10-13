"""Auto-select demo vs personal portfolio (no user toggle)."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from .app_preferences import AppPreferences
from .onboarding_ui import _load_demo_portfolio
from .portfolio_dashboard_data import portfolio_has_data
from .portfolio_store import PortfolioStore

DEMO_BANNER_TEXT = (
    "Showing example data — upload your Zerodha files in **Import & backup**."
)


def has_real_personal_data(personal_path: Path) -> bool:
    """True when the personal database has uploads, Kite sync, or other non-demo data."""

    if not personal_path.exists():
        return False
    store = PortfolioStore(personal_path)
    for frame in (store.list_equity_holdings(), store.list_mf_holdings()):
        if frame.empty:
            continue
        if "source" not in frame.columns:
            return True
        if frame["source"].ne("example").any():
            return True
    return False


def using_demo_portfolio(personal_path: Path) -> bool:
    return not has_real_personal_data(personal_path)


def selected_portfolio_path(personal_path: Path, work_dir: Path) -> Path:
    if has_real_personal_data(personal_path):
        return personal_path
    demo_path = work_dir / "demo_portfolio.db"
    if not demo_path.exists() or not portfolio_has_data(demo_path):
        _load_demo_portfolio(demo_path, AppPreferences(work_dir / "demo_prefs.json"))
    return demo_path


def render_demo_data_banner() -> None:
    st.markdown(
        '<p class="royal-demo-banner">'
        "Showing example data — upload your Zerodha files in Import &amp; backup."
        "</p>",
        unsafe_allow_html=True,
    )


def choose_personal_portfolio(mode: str = "upload") -> None:
    st.session_state["home_setup"] = mode
    st.session_state["active_section"] = "Dashboard"


def render_get_started_actions() -> None:
    """Upload / connect shortcuts on Dashboard (no demo vs personal switch)."""

    left, right = st.columns(2)
    left.button(
        "Upload my portfolio",
        icon=":material/upload_file:",
        type="primary",
        use_container_width=True,
        key="home_upload",
        on_click=choose_personal_portfolio,
        args=("upload",),
    )
    right.button(
        "Connect Zerodha",
        icon=":material/link:",
        use_container_width=True,
        key="home_connect",
        on_click=choose_personal_portfolio,
        args=("connect",),
    )
    st.caption(
        "Example data is shown until you add real holdings. Uploads stay separate from the demo database."
    )


def render_start_setup(personal_path: Path) -> None:
    mode = st.session_state.get("home_setup")
    if mode == "upload":
        from .portfolio_cloud_ui import render_portfolio_import_panel

        with st.expander("Upload your portfolio", expanded=True):
            render_portfolio_import_panel(personal_path, compact=True)
    elif mode == "connect":
        render_connect_portfolio(personal_path)


def render_connect_portfolio(personal_path: Path) -> None:
    from .kite_config import KiteCredentials
    from .portfolio_service import sync_kite_holdings
    from .portfolio_store import PortfolioStore

    st.markdown("**Connect your Zerodha holdings**")
    st.caption(
        "Read-only connection using Kite Connect. It cannot place trades. "
        "You need your Kite API key and current access token; uploading Console files works without them."
    )
    with st.form("home_kite_connect", clear_on_submit=True):
        api_key = st.text_input("Kite API key", type="password")
        access_token = st.text_input("Kite access token", type="password")
        st.caption(
            "Credentials are used for this sync and are not saved to files or the cloud database."
        )
        submitted = st.form_submit_button("Connect & load holdings", type="primary")
    if submitted:
        if not api_key.strip() or not access_token.strip():
            st.error("Enter both the API key and access token, or choose Upload my portfolio.")
            return
        try:
            with st.spinner("Loading your holdings from Zerodha…"):
                counts = sync_kite_holdings(
                    PortfolioStore(personal_path),
                    credentials=KiteCredentials(api_key.strip(), access_token.strip()),
                )
        except Exception:
            st.error(
                "Could not connect. Check your key and current access token, "
                "or upload Console files instead. Existing holdings were kept."
            )
            return
        st.session_state.pop("home_setup", None)
        st.session_state["portfolio_notice"] = (
            f"Connected: loaded {counts[0]} stock holdings and {counts[1]} mutual fund holdings."
        )
        st.rerun()
