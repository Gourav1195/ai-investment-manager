# Authentication and remember-me

**Code:** `src/investing/cloud_auth.py`, `src/investing/auth_remember.py`, `src/investing/auth_cookies.py`, `src/investing/auth_browser.py`

## APP_PASSWORD gate

`require_app_password()` runs at the start of `dashboard.main()` after page config.

| Environment | Behavior |
|-------------|----------|
| Local dev, no `APP_PASSWORD` | Gate skipped — app runs open |
| `DATABASE_URL` set, no `APP_PASSWORD` | **Hard stop** — cloud DB requires a login password |
| Streamlit Community Cloud, no `APP_PASSWORD` | **Hard stop** — public deploy must not expose holdings |
| `APP_PASSWORD` set | Login form until `st.session_state["app_password_ok"]` |

Password source: `st.secrets["APP_PASSWORD"]` or `APP_PASSWORD` env (`_configured_password()`).

## Remember-me

- Tokens: `auth_remember.py` — HMAC-signed payload (`mint_remember_token` / `verify_remember_token`).
- Signing key: **`APP_AUTH_SIGNING_KEY`** in secrets or env; if unset, key is derived from `APP_PASSWORD` (weaker).
- `warn_if_default_signing_key()` — one `st.warning` per session when custom key is missing and password auth is active.
- Browser bridge: `auth_browser.py` (localStorage / cookie); server cookie: `auth_cookies.py`.

## Streamlit Cloud detection

`is_streamlit_community_cloud()` in `cloud_persistence.py` — `STREAMLIT_RUNTIME_ENVIRONMENT == "cloud"`.

## Tests

- `tests/test_portfolio_start_auth.py` — remember token restore
- `tests/test_cloud_auth_deploy.py` — blocks SCC without password

Secrets checklist: `docs/cloud_database.md`.
