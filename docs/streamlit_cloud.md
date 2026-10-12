# Streamlit Community Cloud deployment

## Recommended app settings

| Setting | Value |
|---------|--------|
| **Repository** | `Gourav1195/ai-investment-manager` (or your fork) |
| **Branch** | `master` |
| **Main file path** | `streamlit_app.py` |
| **Python version** | **3.12** or **3.13** (3.14 when available in the UI; app deps support 3.12–3.14) |

Do **not** use `src/investing/dashboard_streamlit.py` as the main file unless you cannot change it;
`streamlit_app.py` at the repo root fixes `sys.path` for Cloud.

## Dependencies

Streamlit Cloud runs:

```bash
pip install -r requirements.txt
```

That file is intentionally **lightweight** (pandas, streamlit, yfinance, openpyxl, etc.).  
Heavy FinRL / trading packages are in `requirements-trading.txt`.  
Dev tools are in `requirements-dev.txt`.

## Secrets (optional password)

In the app → **Settings → Secrets**, add:

```toml
APP_PASSWORD = "your-private-password"
```

When `APP_PASSWORD` is set, users must enter it before the dashboard loads.  
Leave unset for a public demo.

Optional paths (usually not needed on Cloud):

```toml
INVESTING_WORK_DIR = "/mount/path"  # defaults to repo/work/
```

## First visit (no databases)

The **Portfolio** tab shows:

- **Load anonymized example portfolio** (bundled demo CSVs; no personal data)
- Upload widgets for equity holdings, tradebook, and MF holdings (CSV/XLSX)

Research tabs stay empty until you run CLI research locally and upload a `research.db`
(or use the demo after loading examples).

## Local check (simulates Cloud cwd)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd /tmp
streamlit run /path/to/repo/streamlit_app.py
```

Automated check (Playwright, foreign cwd, empty `work/`):

```bash
pip install -r requirements-dev.txt
python -m playwright install chromium
PYTHONPATH=. python scripts/qa_streamlit_cloud_simulation.py
```

## Runtime note

Target **Python 3.12–3.14**. Pick the version in the Streamlit Cloud UI (3.12 or 3.13 recommended until 3.14 is listed).
Dependencies in `requirements.txt` are chosen to stay compatible across that range.
