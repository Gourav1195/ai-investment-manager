"""Always-visible sidebar section navigation."""

from __future__ import annotations

import streamlit as st

SIDEBAR_SECTIONS = (
    "Dashboard",
    "Portfolio",
    "My mutual funds",
    "Top mutual funds",
    "MF peers",
    "Snapshots",
    "Profile review",
    "Orchestration",
    "Run research",
    "Import & backup",
    "About",
)

# Legacy name used in tests (main views excluding utility pages).
TOP_LEVEL_TABS = tuple(
    label
    for label in SIDEBAR_SECTIONS
    if label not in {"Run research", "Import & backup", "About"}
)


def render_sidebar_section_menu() -> str:
    """Royal-styled radio menu; returns the selected section label."""

    st.markdown(
        '<p class="royal-sidebar-nav-title">Menu</p>',
        unsafe_allow_html=True,
    )
    return st.radio(
        "Main menu",
        options=list(SIDEBAR_SECTIONS),
        index=0,
        label_visibility="collapsed",
    )
