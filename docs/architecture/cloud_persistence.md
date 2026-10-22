# Cloud persistence (Postgres blobs)

**Code:** `src/investing/cloud_persistence.py`, `src/investing/cloud_persistence_ui.py`, `src/investing/dashboard.py`

## Purpose

On Streamlit Community Cloud, local disk under `work/` is ephemeral. Optional Postgres stores three blobs:

| Blob key | Local file |
|----------|------------|
| `research_db` | `research.db` |
| `portfolio_db` | `portfolio.db` |
| `ui_prefs` | `ui_prefs.json` |

Table: `investing_app_blobs` (see `_SCHEMA_SQL` in `cloud_persistence.py`).

## Configuration

- Secret / env: **`DATABASE_URL`** — resolved by `resolve_database_url()` (Streamlit `st.secrets` then `os.environ`).
- `normalize_database_url()` — `postgres://` / `postgresql://` → `postgresql+psycopg2://`; appends `sslmode=require` for non-local hosts when missing.
- Nested secret dicts supported (`url`, `connection_string`, or `postgres` section).

Passwords are **never** logged; errors use `_safe_database_target()` (host/port/db only). User-facing text uses `format_cloud_error()`.

## Session lifecycle

`sync_session_cloud_data(work_dir)` (`dashboard.py` calls this early in `_run_dashboard()`):

1. If no `DATABASE_URL` → `PersistenceMode.LOCAL`.
2. First run per session: `pull_cloud_blobs()` — download remote blobs when newer than local; sets `_cloud_pulled`.
3. On file hash change: `push_cloud_blobs()` — upsert blobs.

Modes:

| Mode | Meaning |
|------|---------|
| `LOCAL` | No cloud URL configured |
| `CLOUD` | Pull/push OK |
| `CLOUD_DEGRADED` | Connection or push failed; app keeps using local SQLite |

## UI banners

- **Sidebar:** `render_data_persistence_badge()` inside **Storage & help** (`cloud_persistence_ui.py`).
- **Main canvas:** `render_main_persistence_banner()` — `CLOUD_DEGRADED` → `st.error` with diagnostic details; on Streamlit Cloud with `LOCAL` → `st.warning` about ephemeral storage (`is_streamlit_community_cloud()` checks `STREAMLIT_RUNTIME_ENVIRONMENT=cloud`).

## Tests

- `tests/test_cloud_persistence.py` — URL normalization, degraded URL, restart simulation (uses `CI_POSTGRES_URL` in GitHub Actions or Docker locally).

User guide: `docs/cloud_database.md`.
