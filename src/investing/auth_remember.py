"""Signed remember-me tokens for APP_PASSWORD (no plain password in cookies)."""

from __future__ import annotations

import hashlib
import hmac
import os
import time


TOKEN_VERSION = "1"
TOKEN_TTL_SECONDS = 30 * 24 * 60 * 60
COOKIE_NAME = "investing_remember"
QUERY_PARAM = "investing_auth"


def using_custom_signing_key() -> bool:
    try:
        import streamlit as st

        if st.secrets.get("APP_AUTH_SIGNING_KEY"):
            return True
    except Exception:
        pass
    return bool(os.environ.get("APP_AUTH_SIGNING_KEY", "").strip())


def warn_if_default_signing_key() -> None:
    """Surface once per session when remember-me uses the derived fallback key."""

    if using_custom_signing_key():
        return
    try:
        import streamlit as st
    except Exception:
        return
    if st.session_state.get("_warned_default_signing_key"):
        return
    st.session_state["_warned_default_signing_key"] = True
    st.warning(
        "**APP_AUTH_SIGNING_KEY** is not set. “Remember me” tokens use a key derived from your "
        "login password. For production (especially Streamlit Cloud), add a long random "
        "`APP_AUTH_SIGNING_KEY` in **Settings → Secrets** so session cookies are signed independently."
    )


def _signing_key(password: str) -> bytes:
    try:
        import streamlit as st

        extra = st.secrets.get("APP_AUTH_SIGNING_KEY")
    except Exception:
        extra = None
    if extra:
        return str(extra).encode("utf-8")
    env = os.environ.get("APP_AUTH_SIGNING_KEY", "").strip()
    if env:
        return env.encode("utf-8")
    digest = hashlib.sha256(f"investing-remember-v1:{password}".encode("utf-8")).digest()
    return digest


def _password_tag(password: str, key: bytes) -> str:
    return hmac.new(key, password.encode("utf-8"), hashlib.sha256).hexdigest()[:32]


def mint_remember_token(password: str, *, ttl_seconds: int = TOKEN_TTL_SECONDS) -> str:
    key = _signing_key(password)
    expires = int(time.time()) + ttl_seconds
    tag = _password_tag(password, key)
    body = f"{TOKEN_VERSION}.{expires}.{tag}"
    signature = hmac.new(key, body.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{body}.{signature}"


def verify_remember_token(token: str, password: str) -> bool:
    if not token or not password:
        return False
    parts = token.split(".")
    if len(parts) != 4:
        return False
    version, expires_s, tag, signature = parts
    if version != TOKEN_VERSION:
        return False
    try:
        expires = int(expires_s)
    except ValueError:
        return False
    if expires < int(time.time()):
        return False
    key = _signing_key(password)
    body = f"{version}.{expires_s}.{tag}"
    expected_sig = hmac.new(key, body.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected_sig):
        return False
    return hmac.compare_digest(tag, _password_tag(password, key))
