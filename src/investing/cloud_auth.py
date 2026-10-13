"""Optional password gate for hosted Streamlit deployments."""

from __future__ import annotations

import os

import streamlit as st

from .auth_cookies import read_remember_cookie, write_remember_cookie
from .auth_browser import render_browser_auth
from .auth_remember import (
    QUERY_PARAM,
    mint_remember_token,
    using_custom_signing_key,
    verify_remember_token,
    warn_if_default_signing_key,
)
from .cloud_persistence import is_cloud_persistence_configured, is_streamlit_community_cloud


def require_app_password() -> None:
    """Stop the app until the user enters ``APP_PASSWORD`` when configured."""

    if is_cloud_persistence_configured() and not _configured_password():
        st.error(
            "Cloud database is enabled (DATABASE_URL) but APP_PASSWORD is missing. "
            "Add APP_PASSWORD in Streamlit Settings → Secrets, then reboot the app."
        )
        st.stop()

    if is_streamlit_community_cloud() and not _configured_password():
        st.error(
            "This app is deployed on **Streamlit Community Cloud** without a login password. "
            "Portfolio and research data must not be public. "
            "Add **`APP_PASSWORD`** in **Settings → Secrets**, then reboot the app. "
            "Optionally add **`DATABASE_URL`** (Postgres) so data survives restarts — see **Storage & help**."
        )
        st.stop()

    expected = _configured_password()
    if not expected:
        return

    warn_if_default_signing_key()

    if st.session_state.get("app_password_ok"):
        token = st.session_state.get("_remember_token")
        if token:
            write_remember_cookie(token)
        render_browser_auth(token=token, clear=bool(st.session_state.get("_clear_remembered_auth")))
        return

    if _try_restore_remembered_session(expected):
        st.session_state["app_password_ok"] = True
        render_browser_auth(token=st.session_state.get("_remember_token"))
        return

    known = st.session_state.get("_wealth_browser_auth", {}).get("storage") or {}
    known_token = known.get("token")
    reject = bool(known_token and not _verify_token_safe(str(known_token), expected))
    storage = render_browser_auth(clear=reject)
    browser_token = storage.get("token") if storage else None
    if browser_token and _verify_token_safe(str(browser_token), expected):
        st.session_state["app_password_ok"] = True
        st.session_state["_remember_token"] = str(browser_token)
        st.rerun()

    st.subheader("Sign in")
    st.caption("Sign in to your private wealth dashboard. Your remembered session is restored automatically.")
    with st.form("app_password_form", clear_on_submit=False):
        entered = st.text_input("Password", type="password")
        remember = st.checkbox("Remember me for 30 days", value=True)
        submitted = st.form_submit_button("Continue")
    if submitted:
        if entered == expected:
            st.session_state["app_password_ok"] = True
            if remember:
                _persist_remember_token(expected)
                st.session_state["_clear_remembered_auth"] = False
            else:
                st.session_state.pop("_remember_token", None)
                st.session_state["_clear_remembered_auth"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    st.stop()


def _try_restore_remembered_session(expected: str) -> bool:
    query = st.query_params.get(QUERY_PARAM)
    if isinstance(query, list):
        query = query[0] if query else None
    if query and _verify_token_safe(str(query), expected):
        st.session_state["_remember_token"] = str(query)
        write_remember_cookie(str(query))
        del st.query_params[QUERY_PARAM]
        return True

    cookie_token = read_remember_cookie()
    if cookie_token and _verify_token_safe(cookie_token, expected):
        st.session_state["_remember_token"] = cookie_token
        return True
    return False


def _verify_token_safe(token: str, expected: str) -> bool:
    try:
        return verify_remember_token(token, expected)
    except Exception:
        return False


def _persist_remember_token(expected: str) -> None:
    try:
        token = mint_remember_token(expected)
    except Exception:
        return
    st.session_state["_remember_token"] = token


def _configured_password() -> str | None:
    try:
        value = st.secrets.get("APP_PASSWORD")
    except Exception:
        value = None
    if value:
        return str(value)
    env = os.environ.get("APP_PASSWORD", "").strip()
    return env or None
