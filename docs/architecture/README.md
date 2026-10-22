# Developer architecture notes

Concise maps of non-obvious behavior in the **India investing Streamlit app** (`src/investing/`). User-facing guides stay in `docs/getting_started.md`, `docs/cloud_database.md`, and `docs/streamlit_cloud.md`.

| Topic | Doc |
|--------|-----|
| Demo vs personal portfolio | [portfolio_selection.md](portfolio_selection.md) |
| Cloud Postgres blobs | [cloud_persistence.md](cloud_persistence.md) |
| Login and remember-me | [auth.md](auth.md) |
| Research runs and snapshots | [research_pipeline.md](research_pipeline.md) |
| Tests and CI | [testing_ci.md](testing_ci.md) |
| Financial goals | [portfolio_goals.md](portfolio_goals.md) |
| SIP calendar inference | [sip_calendar.md](sip_calendar.md) |
| Concentration & CSV export | [concentration_and_export.md](concentration_and_export.md) |
| Per-stock XIRR | [equity_holding_xirr.md](equity_holding_xirr.md) |
| SIP changes & overrides | [sip_change_detection.md](sip_change_detection.md) |
| MF stock overlap | [mf_stock_overlap.md](mf_stock_overlap.md) |
| CAMS / KFintech CAS | [cas_import.md](cas_import.md) |

Entry points: `streamlit_app.py` → `src/investing/dashboard.py` (`main()`).
