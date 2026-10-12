# E2E QA report (India investing module)

Date: 2026-10-12  
Branch: `cursor/e2e-qa-fixes-6eb3`  
Automated: `pytest` (126 tests), `scripts/qa_dashboard_playwright.py` (Playwright + screenshots)

## Bugs found and fixed

| Bug | Fix | Regression test |
|-----|-----|-----------------|
| Yahoo `^NSEI` benchmark failed when portfolio dates were timestamps (`00:00:00` in start/end) | `_yahoo_date_only()` in `providers.py`; align dates in `benchmark_comparison_series` | `tests/test_yahoo_date_normalization.py` |
| `streamlit run src/investing/dashboard.py` crashed (`ImportError` relative imports) | `dashboard_streamlit.py` entrypoint; CLI `dashboard` uses it | `tests/test_dashboard_streamlit_entry.py` |
| `pip install -r requirements.txt` failed on Python 3.12 (`finnhub` unavailable) | `requirements-core.txt` + optional `requirements-trading.txt`; finnhub removed from main requirements | Manual: `pip install -r requirements-core.txt` in QA |
| Playwright could not click Streamlit tabs | QA script uses `[data-testid="stTabs"]` scoped text clicks | `scripts/qa_dashboard_playwright.py` |

## Feature matrix

| Feature | How tested | Result |
|---------|------------|--------|
| `universe` | Live CLI → `work/qa/nifty50.csv` | Pass |
| `prices` | Covered by unit tests + yfinance normalization tests | Pass |
| `score` | Existing unit tests | Pass |
| `filings` / `fundamentals` / `walkforward` | Existing unit tests (no live NSE in this pass) | Pass (unit) |
| `explain` | Existing unit tests | Pass |
| `dashboard` | Playwright all tabs + profile activation UI | Pass |
| `portfolio load-examples` | CLI + Playwright seed | Pass |
| `portfolio import` CSV | `tests/test_zerodha_import.py` | Pass |
| `portfolio import` XLSX | `tests/test_portfolio_edge_cases.py` | Pass |
| `portfolio sync-mf-master` offline | `--input amfi_nav_sample.txt` → 4 rows | Pass |
| `portfolio sync-mf-master` online | Live integration (AMFI download) | Pass |
| `portfolio mf-peers` | Mock peers + live Parag Parikh `122639` integration | Pass |
| `portfolio sync-kite` | Mock HTTP server `tests/e2e/test_kite_mock_sync.py` | Pass |
| `portfolio show` empty DB | `tests/test_portfolio_edge_cases.py` | Pass |
| P&L hand calc | `tests/test_portfolio_analytics.py` (RELIANCE 10 × (2600−2450.5)) | Pass |
| XIRR | `tests/test_portfolio_analytics.py` + `test_mf_peer_comparison.py` | Pass |
| MF peers live | `tests/e2e/test_live_mf_integration.py` | Pass |
| Live yfinance `.NS` | `tests/test_yahoo_date_normalization.py` (benchmark series) | Pass |
| Benchmark comparison | Fixed timestamp date bug; live fetch in normalization test | Pass |
| `constituents` / `profiles` / `calibrate` / `orchestrate` / `schedule` | Existing unit tests + CLI `--help` smoke | Pass |
| Malformed CSV | `tests/test_portfolio_edge_cases.py` | Pass |
| Network failure (prices) | `portfolio_dashboard_data` falls back to cache; analytics swallows fetch errors | Pass (unit) |
| Fresh install | `requirements-core.txt` installs on Python 3.12 | Pass |

## Not fully exercised in this pass

| Item | Reason |
|------|--------|
| Live NSE `filings` / XBRL download | Slow, rate-limited; covered by existing unit tests with fixtures |
| Live `orchestrate` full universe | Requires long runtime and external data |
| SMTP/webhook notifications | Unit tests only |
| Kite Connect production API | Mock server only (no user tokens) |
| Manual MF multiselect interaction in Playwright | Screenshot captured; Streamlit multiselect automation is brittle |

## Screenshots

Saved under `/opt/cursor/artifacts/screenshots/`:

- `dashboard-tab-snapshots.png`
- `dashboard-tab-profile-review.png`
- `dashboard-tab-orchestration.png`
- `dashboard-tab-portfolio.png`
- `dashboard-profile-activation.png`
- `dashboard-mf-manual-compare.png`

## Commands to reproduce

```bash
PYTHONPATH=. python3 -m pytest tests -q
PYTHONPATH=. python3 scripts/qa_dashboard_playwright.py
PYTHONPATH=. python3 -m pytest tests/e2e/test_live_mf_integration.py -m integration -q
```
