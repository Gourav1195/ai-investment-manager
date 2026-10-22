# Testing and CI

## Pytest

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -q
```

- **185+** unit/integration tests under `tests/`.
- Cloud Postgres integration: `tests/test_cloud_persistence.py::test_restart_simulation_with_postgres` uses `CI_POSTGRES_URL` in GitHub Actions (service container) or local Docker on port `55432`; skips if unavailable.

## Playwright E2E smoke

```bash
pip install -r requirements-dev.txt
python -m playwright install chromium

INVESTING_UI_RESEARCH_OFFLINE=1 streamlit run streamlit_app.py --server.port 8501 --server.headless true &
# wait for http://127.0.0.1:8501/_stcore/health
python scripts/e2e_ui_verify.py http://127.0.0.1:8501
```

**Script:** `scripts/e2e_ui_verify.py` — sidebar, Run research results, Saved research (`Snapshots`), My mutual funds, demo banner, collapse.

**Helpers:** `scripts/qa_streamlit_nav.py` — `click_sidebar_section()` uses internal section keys from `sidebar_nav.SIDEBAR_SECTIONS` (not always the display label).

**Screenshots (optional):** `scripts/capture_ui_screenshots.py <output-dir>`

**Legacy full tours:** `scripts/qa_*_playwright.py` — longer tab walks; prefer `e2e_ui_verify.py` for CI-style checks.

## GitHub Actions

Workflow: `.github/workflows/ci.yml` on `push` to `master` and on pull requests.

1. Postgres 16 service + `CI_POSTGRES_URL`
2. `pytest tests/ -q`
3. Streamlit + `e2e_ui_verify.py`

## Related docs

- `docs/E2E_QA_REPORT.md` — last QA summary template
- `docs/streamlit_cloud.md` — deploy notes
