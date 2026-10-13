"""Optional password gate for hosted Streamlit deployments."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import streamlit as st

from .auth_remember import (
    COOKIE_NAME,
    QUERY_PARAM,
    mint_remember_token,
    verify_remember_token,
)
from .cloud_persistence import is_cloud_persistence_configured


@st.cache_resource
def _cookie_manager():
    import extra_streamlit_components as stx

    return stx.CookieManager()


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

    if _try_restore_remembered_session(expected):
        st.session_state["app_password_ok"] = True
        return

    st.subheader("Sign in")
    st.caption("This app is private. Enter the password from Streamlit secrets.")
    with st.form("app_password_form", clear_on_submit=False):
        entered = st.text_input("Password", type="password")
        remember = st.checkbox("Remember me for 30 days", value=True)
        submitted = st.form_submit_button("Continue")
    if submitted:
        if entered == expected:
            st.session_state["app_password_ok"] = True
            if remember:
                _persist_remember_token(expected)
            st.rerun()
        else:
            st.error("Incorrect password.")
    st.stop()


def _try_restore_remembered_session(expected: str) -> bool:
    query = st.query_params.get(QUERY_PARAM)
    if isinstance(query, list):
        query = query[0] if query else None
    if query and verify_remember_token(str(query), expected):
        return True

    manager = _cookie_manager()
    cookies = manager.get_all()
    if cookies is None:
        if not st.session_state.get("_auth_cookie_probe_done"):
            st.session_state["_auth_cookie_probe_done"] = True
            st.rerun()
        return False

    token = cookies.get(COOKIE_NAME)
    if token and verify_remember_token(str(token), expected):
        return True
    return False


def _persist_remember_token(expected: str) -> None:
    token = mint_remember_token(expected)
    expires = datetime.now(tz=timezone.utc) + timedelta(days=30)
    manager = _cookie_manager()
    manager.set(
        COOKIE_NAME,
        token,
        expires_at=expires,
        key=f"set_{COOKIE_NAME}",
    )
    st.query_params[QUERY_PARAM] = token


def _configured_password() -> str | None:
    try:
        value = st.secrets.get("APP_PASSWORD")
    except Exception:
        value = None
    if value:
        return str(value)
    env = os.environ.get("APP_PASSWORD", "").strip()
    return env or None
