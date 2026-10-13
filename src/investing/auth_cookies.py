"""Browser cookie helpers for remember-me auth (no third-party components)."""

from __future__ import annotations

import json
import logging

import streamlit as st

from .auth_remember import COOKIE_NAME, TOKEN_TTL_SECONDS

logger = logging.getLogger(__name__)


def read_remember_cookie() -> str | None:
    """Read the remember-me cookie via ``st.context.cookies`` (best-effort)."""

    try:
        value = st.context.cookies.get(COOKIE_NAME)
    except Exception:
        logger.debug("Could not read auth cookie from context", exc_info=True)
        return None
    if not value:
        return None
    return str(value)


def write_remember_cookie(token: str) -> None:
    """Set the remember-me cookie with a tiny inline script (best-effort)."""

    if not token:
        return
    try:
        name_json = json.dumps(COOKIE_NAME)
        token_json = json.dumps(token)
        st.html(
            f"""
<script>
(function () {{
  try {{
    var name = {name_json};
    var value = {token_json};
    var maxAge = {TOKEN_TTL_SECONDS};
    var secure = window.location.protocol === "https:" ? "; Secure" : "";
    var cookie = name + "=" + encodeURIComponent(value)
      + "; path=/; max-age=" + maxAge + "; SameSite=Lax" + secure;
    var targets = [document, window.parent && window.parent.document];
    for (var i = 0; i < targets.length; i++) {{
      var doc = targets[i];
      if (doc) doc.cookie = cookie;
    }}
  }} catch (e) {{}}
}})();
</script>
""",
            height=0,
        )
    except Exception:
        logger.debug("Could not inject remember-me cookie script", exc_info=True)
