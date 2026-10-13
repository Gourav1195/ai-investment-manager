"""Browser persistence bridge for signed tokens when proxy cookies are unavailable."""
from __future__ import annotations

import streamlit as st
from streamlit.components.v2 import component
from .auth_remember import COOKIE_NAME, TOKEN_TTL_SECONDS

AUTH_BROWSER_JS = """
export default function({ data, setStateValue }) {
  let token = null;
  let storageAvailable = false;
  const name = data.name;
  try {
    if (data.clear) window.localStorage.removeItem(name);
    else if (data.token) window.localStorage.setItem(name, data.token);
    token = window.localStorage.getItem(name);
    storageAvailable = true;
  } catch (_) {}
  // Work only with the app document; parent frames can be cross-origin.
  try {
    if (data.clear || data.token) {
      const value = data.clear ? "" : encodeURIComponent(data.token);
      const maxAge = data.clear ? 0 : data.ttl;
      const secure = window.location.protocol === "https:" ? "; Secure" : "";
      document.cookie = name + "=" + value + "; path=/; max-age=" + maxAge
        + "; SameSite=Lax" + secure;
    }
    const pair = document.cookie.split(";").map(x => x.trim()).find(x => x.startsWith(name + "="));
    if (!token && pair) token = decodeURIComponent(pair.substring(name.length + 1));
  } catch (_) {}
  const value = { token: data.clear ? null : token, available: storageAvailable || !!token };
  if (JSON.stringify(value) !== JSON.stringify(data.known)) setStateValue("storage", value);
}
"""

_auth_browser = component("wealth_browser_auth", js=AUTH_BROWSER_JS)

def render_browser_auth(*, token: str | None = None, clear: bool = False) -> dict | None:
    known = st.session_state.get("_wealth_browser_auth", {}).get("storage")
    result = _auth_browser(
        key="_wealth_browser_auth", height=0,
        data={"name": COOKIE_NAME, "ttl": TOKEN_TTL_SECONDS,
              "token": token, "clear": clear, "known": known},
        on_storage_change=lambda: None,
    )
    storage = getattr(result, "storage", None)
    return storage if isinstance(storage, dict) else None
