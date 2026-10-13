"""Grouped sidebar navigation with one persistent active destination."""

from __future__ import annotations

import streamlit as st

NAV_GROUPS = (
    ("Your wealth", (
        ("Dashboard", ":material/dashboard:"),
        ("Portfolio", ":material/account_balance_wallet:"),
        ("My mutual funds", ":material/pie_chart:"),
        ("Top mutual funds", ":material/trending_up:"),
        ("MF peers", ":material/compare_arrows:"),
    )),
    ("Stock research", (
        ("Run research", ":material/search:"),
        ("Snapshots", ":material/history:"),
        ("Profile review", ":material/tune:"),
        ("Orchestration", ":material/account_tree:"),
    )),
    ("Workspace", (
        ("Import & backup", ":material/upload_file:"),
        ("About", ":material/info:"),
    )),
)

DISPLAY_LABELS = {
    "MF peers": "Compare funds",
    "Snapshots": "Saved research",
    "Profile review": "Scoring settings",
    "Orchestration": "Research runs",
}

# Preserve the existing routing labels and compatibility export.
SIDEBAR_SECTIONS = (
    "Dashboard", "Portfolio", "My mutual funds", "Top mutual funds", "MF peers",
    "Snapshots", "Profile review", "Orchestration", "Run research", "Import & backup", "About",
)
TOP_LEVEL_TABS = tuple(
    label for label in SIDEBAR_SECTIONS
    if label not in {"Run research", "Import & backup", "About"}
)

def _select_section(section: str) -> None:
    st.session_state["active_section"] = section

def render_sidebar_section_menu() -> str:
    """Render native keyboard-accessible buttons without nested scrolling."""
    if st.session_state.get("active_section") not in SIDEBAR_SECTIONS:
        st.session_state["active_section"] = "Dashboard"
    active = st.session_state["active_section"]
    with st.container(key="royal_navigation"):
        for group, items in NAV_GROUPS:
            st.markdown(
                f'<p class="royal-nav-group">{group}</p>', unsafe_allow_html=True
            )
            for label, icon in items:
                st.button(
                    DISPLAY_LABELS.get(label, label), icon=icon, key=f"nav_{label}",
                    type="primary" if active == label else "secondary",
                    use_container_width=True,
                    on_click=_select_section, args=(label,),
                    help=f"Current page: {label}" if active == label else None,
                )
    return active
