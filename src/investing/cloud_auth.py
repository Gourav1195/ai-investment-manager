"""Optional password gate for hosted Streamlit deployments."""

from __future__ import annotations

import os

import streamlit as st

from .cloud_persistence import is_cloud_persistence_configured


def require_app_password() -> None:
    """Stop the app until the user enters ``APP_PASSWORD`` when configured."""

    if is_cloud_persistence_configured() and not _configured_password():
        st.error(
            "Cloud database is enabled (DATABASE_URL) but APP_PASSWORD is missing. "
            "Add APP_PASSWORD in Streamlit Settings → Secrets, then reboot the app."
        )
        st.stop()

    expected = _configured_password()
    if not expected:
        return
    if st.session_state.get("app_password_ok"):
        return
    st.title("Sign in")
    st.caption("This app is private. Enter the password from Streamlit secrets.")
    entered = st.text_input("Password", type="password", key="app_password_input")
    if st.button("Continue", key="app_password_submit"):
        if entered == expected:
            st.session_state["app_password_ok"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    st.stop()


def _configured_password() -> str | None:
    try:
        value = st.secrets.get("APP_PASSWORD")
    except Exception:
        value = None
    if value:
        return str(value)
    env = os.environ.get("APP_PASSWORD", "").strip()
    return env or None
