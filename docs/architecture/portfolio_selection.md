# Portfolio selection (demo vs real)

**Code:** `src/investing/portfolio_start.py`, `src/investing/onboarding_ui.py`, `src/investing/dashboard.py`

## Rule

There is **no UI toggle** between “demo” and “my portfolio”. The app picks one SQLite file per request based on whether the user has **real** data.

## Databases

| File | Role |
|------|------|
| `{work_dir}/portfolio.db` | Personal DB — Zerodha uploads, Kite sync, user data |
| `{work_dir}/demo_portfolio.db` | Isolated example holdings (`source = example`) |

`work_dir` comes from `default_work_dir()` in `src/investing/repo_bootstrap.py` (overridable via `INVESTING_WORK_DIR`).

## Detection

- `has_real_personal_data(personal_path)` — true if equity or MF holdings exist with any row whose `source` is not `"example"` (or `source` column missing).
- `using_demo_portfolio(personal_path)` — negation of the above.
- `selected_portfolio_path(personal_path, work_dir)` — returns `personal_path` when real data exists; otherwise ensures demo DB exists (`_load_demo_portfolio` in `onboarding_ui.py`) and returns `demo_portfolio.db`.

## UI

- `render_demo_data_banner()` — main-canvas banner when `using_demo_portfolio()` on wealth sections (`dashboard.py`).
- `render_get_started_actions()` / `render_start_setup()` — upload and Kite connect on Dashboard; uploads always target **personal** `portfolio.db`.
- Real imports call `_clear_legacy_demo_data()` in `portfolio_service.py` so example rows are removed when the user uploads.

## Tests

- `tests/test_portfolio_start_auth.py` — path selection, no personal file created when demo is used.
