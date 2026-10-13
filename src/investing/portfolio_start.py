"""Starting-page portfolio choice, with a separate default demo."""
from __future__ import annotations
from pathlib import Path
import streamlit as st
from .app_preferences import AppPreferences
from .onboarding_ui import _load_demo_portfolio
from .portfolio_dashboard_data import portfolio_has_data

def choose_personal_portfolio(mode: str = "upload") -> None:
    st.session_state["portfolio_source"] = "My portfolio"
    st.session_state["home_setup"] = mode
    st.session_state["active_section"] = "Dashboard"

def _source_changed() -> None:
    source = st.session_state["home_portfolio_source"] or st.session_state["portfolio_source"]
    st.session_state["home_portfolio_source"] = source
    st.session_state["portfolio_source"] = source
    if st.session_state["portfolio_source"] == "Demo portfolio":
        st.session_state.pop("home_setup", None)

def portfolio_source(personal_path: Path) -> str:
    if "portfolio_source" not in st.session_state:
        has_personal_data = False
        if personal_path.exists():
            from .portfolio_store import PortfolioStore
            store = PortfolioStore(personal_path)
            has_personal_data = any(
                not frame.empty and frame["source"].ne("example").any()
                for frame in (store.list_equity_holdings(), store.list_mf_holdings())
            )
        st.session_state["portfolio_source"] = (
            "My portfolio" if has_personal_data
            else "Demo portfolio"
        )
    return st.session_state["portfolio_source"]

def selected_portfolio_path(personal_path: Path, work_dir: Path) -> Path:
    if portfolio_source(personal_path) == "My portfolio":
        return personal_path
    demo_path = work_dir / "demo_portfolio.db"
    if not demo_path.exists() or not portfolio_has_data(demo_path):
        _load_demo_portfolio(demo_path, AppPreferences(work_dir / "demo_prefs.json"))
    return demo_path

def render_start_choices(personal_path: Path) -> None:
    source = portfolio_source(personal_path)
    st.session_state["home_portfolio_source"] = source
    st.segmented_control(
        "Portfolio to view", ["Demo portfolio", "My portfolio"],
        key="home_portfolio_source", on_change=_source_changed,
    )
    left, right = st.columns(2)
    left.button("Upload my portfolio", icon=":material/upload_file:",
                type="primary", width="stretch", key="home_upload",
                on_click=choose_personal_portfolio, args=("upload",))
    right.button("Connect Zerodha", icon=":material/link:", width="stretch",
                 key="home_connect", on_click=choose_personal_portfolio, args=("connect",))
    st.caption("Explore the demo, or add your own holdings. Your files are kept separate from the demo.")

def render_start_setup(personal_path: Path) -> None:
    mode = st.session_state.get("home_setup")
    if not mode and not (personal_path.exists() and portfolio_has_data(personal_path)):
        mode = "upload"
    if mode == "upload":
        from .portfolio_cloud_ui import render_portfolio_import_panel
        with st.expander("Upload your portfolio", expanded=st.session_state.get("home_setup") == "upload"):
            render_portfolio_import_panel(personal_path, compact=True)
    elif mode == "connect":
        render_connect_portfolio(personal_path)

def render_connect_portfolio(personal_path: Path) -> None:
    from .kite_config import KiteCredentials
    from .portfolio_service import sync_kite_holdings
    from .portfolio_store import PortfolioStore
    st.markdown("**Connect your Zerodha holdings**")
    st.caption("Read-only connection using Kite Connect. It cannot place trades. You need your Kite API key and current access token; uploading Console files works without them.")
    with st.form("home_kite_connect", clear_on_submit=True):
        api_key = st.text_input("Kite API key", type="password")
        access_token = st.text_input("Kite access token", type="password")
        st.caption("Credentials are used for this sync and are not saved to files or the cloud database.")
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
            st.error("Could not connect. Check your key and current access token, or upload Console files instead. Existing holdings were kept.")
            return
        st.session_state["portfolio_source"] = "My portfolio"
        st.session_state.pop("home_setup", None)
        st.session_state["portfolio_notice"] = f"Connected: loaded {counts[0]} stock holdings and {counts[1]} mutual fund holdings."
        st.rerun()


def use_demo_portfolio() -> None:
    st.session_state["portfolio_source"] = "Demo portfolio"
    st.session_state.pop("home_setup", None)
    st.session_state["active_section"] = "Dashboard"
