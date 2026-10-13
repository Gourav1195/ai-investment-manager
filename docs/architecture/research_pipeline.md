# Research pipeline (UI and storage)

**Code:** `src/investing/ui_research.py`, `src/investing/orchestration.py`, `src/investing/research.py`, `src/investing/dashboard.py`, `src/investing/dashboard_data.py`

## Two UI surfaces

| Sidebar section | Internal key | Role |
|-----------------|--------------|------|
| **Run research** | `Run research` | Trigger a batch run; show **Latest saved snapshots** on the same page after data exists (`dashboard.py` → `_render_research_snapshots`) |
| **Saved research** | `Snapshots` | Browse/filter all persisted snapshots (`_render_snapshots_tab`) |

Display label “Saved research” is mapped in `sidebar_nav.py` (`DISPLAY_LABELS`).

## Run flow (browser)

1. `render_run_research_controls()` — universe select + button (`ui_research.py`).
2. `run_ui_research()` — prices (Yahoo or offline demo), `UniverseResearchOrchestrator.run()` with `persist=True`.
3. Results written to **`research.db`** via `ResearchStore` (`research.py`).
4. Page reruns; `store` reloads and renders overview metrics + `snapshot_summary_frame()` + detail expander.

Offline / CI: `INVESTING_UI_RESEARCH_OFFLINE=1` forces demo prices and demo fundamentals.

## Data model (simplified)

- Walk-forward evaluations produce `ResearchRecord` rows (scores, forward returns, benchmarks).
- Snapshots and explanations are queryable through `ResearchStore` and helpers in `dashboard_data.py` (`filter_options`, `snapshot_detail`, `overview_metrics`, etc.).

## Scoring profiles / versions

- Long-term scores use `LongTermScorer` (`scoring.py`) with optional **profile version** from `profile_store.py`.
- Orchestrator accepts `profile_version` (`orchestration.py`); CLI calibration can build versions (`calibration.py`, `build_profile_version`).
- UI **Scoring settings** (`Profile review` / `Snapshots` section key `Profile review`) — `profile_versions`, diff, activate via `activate_scoring_profile()` in `dashboard.py`.

## Orchestration log

**Research runs** sidebar section (`Orchestration`) lists batch orchestration metadata (`orchestration_runs()` in `dashboard_data.py`) — related but separate from single UI “Run research” batches.

## Tests

- `tests/test_ui_research.py` — offline persist
- `tests/test_walkforward.py`, `tests/test_dashboard.py` — store and filters
