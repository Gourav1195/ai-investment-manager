# E2E QA report (Streamlit wealth dashboard)

Date: 2026-10-13  
Branch: `cursor/sidebar-research-ui-a8a7`

## Automated checks

| Command | Purpose |
|---------|---------|
| `python -m pytest tests/ -q` | Unit and integration tests |
| `PYTHONPATH=scripts python scripts/e2e_ui_verify.py` | Playwright smoke: sidebar, Run/Saved research, My mutual funds (demo), persistence banners |
| `PYTHONPATH=scripts python scripts/capture_ui_screenshots.py <dir>` | Optional before/after screenshots |

CI runs pytest and `e2e_ui_verify.py` on every push/PR (`.github/workflows/ci.yml`).

## UI flows covered by `e2e_ui_verify.py`

- Sidebar brand aligned with collapse control (expanded + collapsed)
- **Run research** shows **Latest saved snapshots** after an offline run
- **Saved research** library copy
- **My mutual funds** on demo data (no crash)
- Demo portfolio banner on Dashboard when no personal uploads
- No legacy **Portfolio to view** demo/personal toggle

## Legacy Playwright scripts

`scripts/qa_*_playwright.py` are maintained for full tab tours and screenshots. Navigation helpers live in `scripts/qa_streamlit_nav.py` (button labels with Material icons). Prefer `e2e_ui_verify.py` for CI-style smoke tests.

## Streamlit secrets (hosted app)

| Secret | When |
|--------|------|
| `APP_PASSWORD` | **Always** on Streamlit Community Cloud |
| `DATABASE_URL` | Optional Postgres (Neon/Supabase) for data across restarts |
| `APP_AUTH_SIGNING_KEY` | Recommended for production remember-me signing |

See `docs/cloud_database.md`.
