"""Always-visible sidebar section navigation."""

from __future__ import annotations

import streamlit as st

SIDEBAR_SECTIONS = (
    "Wealth at a glance",
    "Portfolio",
    "My Mutual Funds",
    "Top Mutual Funds",
    "Snapshots",
    "Profile review",
    "Orchestration runs",
    "About",
)

# Legacy name used in tests and docs (main views excluding About).
TOP_LEVEL_TABS = SIDEBAR_SECTIONS[:-1]


def render_sidebar_section_menu() -> str:
    """Royal-styled radio menu; returns the selected section label."""

    st.markdown(
        '<p class="royal-sidebar-nav-title">Go to</p>',
        unsafe_allow_html=True,
    )
    return st.radio(
        "Main menu",
        options=list(SIDEBAR_SECTIONS),
        label_visibility="collapsed",
    )
