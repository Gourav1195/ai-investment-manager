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

## Secrets

### Optional password (public demo)

```toml
APP_PASSWORD = "your-private-password"
```

When `APP_PASSWORD` is set, users must enter it before the dashboard loads.
Check **Remember me for 30 days** to stay signed in (signed cookie plus browser-storage restoration; legacy URL tokens are migrated and removed — never stores the plain password).
Optional `APP_AUTH_SIGNING_KEY` in secrets strengthens cookie signing (recommended for production).
Leave `APP_PASSWORD` unset for a public demo.

### Optional cloud database (data survives restarts)

On Community Cloud, local disk is ephemeral. To keep portfolio, research, profile, and UI
preferences across reboots, add a free Postgres URL from Neon or Supabase:

```toml
DATABASE_URL = "postgresql://USER:PASSWORD@HOST/DATABASE?sslmode=require"
APP_PASSWORD = "required-when-using-cloud-database"
```

Step-by-step guide: [`docs/cloud_database.md`](cloud_database.md). The app shows a banner when
cloud save is active.

Optional paths (usually not needed on Cloud):

```toml
INVESTING_WORK_DIR = "/mount/path"  # defaults to repo/work/
```

## First visit (no databases)

Everything runs in the browser—no command line required.

1. Open **Dashboard**. Demo is selected automatically until you add real holdings. Choose **Upload my portfolio** or **Connect Zerodha** to add yours.
2. Use **Portfolio** for holdings and returns; **My mutual funds** for fund charts.
3. Open **Top mutual funds**, click **Refresh fund list**, pick a category, then **Load rankings**.
4. Stock research is optional: choose **Run research**, then review **Saved research**.
5. Use **Import & backup** to upload files or download a backup. The app owner can configure
   `DATABASE_URL` using [the cloud database guide](cloud_database.md).

For a plain-English walkthrough, see [Getting started](getting_started.md).

## Wealth dashboard navigation

The navy-and-gold sidebar groups **Your wealth**, **Stock research**, and **Workspace**.
The selected page stays highlighted during interactions. There is one outer sidebar scroll,
with all destinations available; the navigation has no small inner scrolling list.
Personalisation, storage status and the glossary sit below navigation. Pages open directly
on their content; only Dashboard shows the welcome and wealth summary.

Streamlit **1.52 or later** is required for the built-in cookie script. Remember-me tokens
are signed and saved as browser cookies after login. Existing signed URL tokens are migrated
to cookies and removed from the address bar; new logins do not put credentials in URLs.

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
