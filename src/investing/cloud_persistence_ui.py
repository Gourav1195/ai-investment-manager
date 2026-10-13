"""In-app cloud database guide and status badge."""

from __future__ import annotations

import streamlit as st

from .cloud_persistence import PersistenceMode, PersistenceState, is_cloud_persistence_configured

CLOUD_GUIDE_MARKDOWN = """
### Save your data across Streamlit restarts (optional)

Streamlit Community Cloud wipes its disk when the app restarts. You can keep your
portfolio, research, profile, and name in a **free cloud database** instead.

**What you need:** a free Postgres database from [Neon](https://neon.tech) or
[Supabase](https://supabase.com), and two entries in **Streamlit Cloud → Settings → Secrets**.

#### Step 1 — Create a free database

1. Sign up at **Neon** (or Supabase) and create a new project.
2. Open the project’s **connection** or **database** settings.
3. Copy the **connection string** (it looks like  
   `postgresql://user:password@host/dbname?sslmode=require`).

#### Step 2 — Add Streamlit secrets

In your app on [share.streamlit.io](https://share.streamlit.io), open **Settings → Secrets** and paste:

```toml
DATABASE_URL = "postgresql://YOUR_USER:YOUR_PASSWORD@YOUR_HOST/YOUR_DB?sslmode=require"
APP_PASSWORD = "choose-a-private-password-you-share-only-with-family"
```

- **`DATABASE_URL`** — the connection string from step 1 (keep it secret).
- **`APP_PASSWORD`** — required when using cloud storage so only people with the password can open the app.

Click **Save**, then use **Reboot app** (or redeploy).

#### Step 3 — Confirm

When the app loads, you should see **“Your data is saved in the cloud”** near the top.
Upload a portfolio or run research once; after a reboot, your data should still be there.

**Fallback:** you can still use **Import & backup → Save or restore your data** to download `.db` files anytime.
"""


def render_cloud_database_guide(*, expanded: bool = False) -> None:
    with st.expander("Keep my data after a restart (cloud database)", expanded=expanded):
        st.markdown(CLOUD_GUIDE_MARKDOWN)


def render_data_persistence_badge(state: PersistenceState) -> None:
    if state.mode == PersistenceMode.LOCAL:
        st.markdown(
            '<p class="royal-persistence-badge royal-persistence-temp">'
            "Temporary session: data resets when the app restarts on Streamlit Cloud. "
            "Open <strong>Import & backup</strong> in the menu for cloud database steps."
            "</p>",
            unsafe_allow_html=True,
        )
        return

    if state.mode == PersistenceMode.CLOUD_DEGRADED:
        detail = state.message or "Cloud save is unavailable; using local files for now."
        st.markdown(
            f'<p class="royal-persistence-badge royal-persistence-warn">'
            f"⚠️ {detail}"
            "</p>",
            unsafe_allow_html=True,
        )
        return

    st.markdown(
        '<p class="royal-persistence-badge royal-persistence-cloud">'
        "☁️ Your data is saved in the cloud — portfolio, research, profile, and preferences "
        "survive app restarts."
        "</p>",
        unsafe_allow_html=True,
    )


def render_sidebar_persistence_hint() -> None:
    if is_cloud_persistence_configured():
        st.caption("Cloud database is configured via secrets.")
    else:
        st.caption("Tip: add DATABASE_URL in Streamlit secrets to keep data after restarts.")
