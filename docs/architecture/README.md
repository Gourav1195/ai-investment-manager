# Developer architecture notes

Concise maps of non-obvious behavior in the **India investing Streamlit app** (`src/investing/`). User-facing guides stay in `docs/getting_started.md`, `docs/cloud_database.md`, and `docs/streamlit_cloud.md`.

| Topic | Doc |
|--------|-----|
| Demo vs personal portfolio | [portfolio_selection.md](portfolio_selection.md) |
| Cloud Postgres blobs | [cloud_persistence.md](cloud_persistence.md) |
| Login and remember-me | [auth.md](auth.md) |
| Research runs and snapshots | [research_pipeline.md](research_pipeline.md) |
| Tests and CI | [testing_ci.md](testing_ci.md) |

Entry points: `streamlit_app.py` → `src/investing/dashboard.py` (`main()`).
