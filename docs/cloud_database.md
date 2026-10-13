# Cloud database (persist data on Streamlit Community Cloud)

On Streamlit Community Cloud, the app’s local disk is **temporary**. When the app restarts or redeploys, files under `work/` (portfolio database, research database, your name, NAV cache) are lost unless you use a backup or **cloud persistence**.

This app supports an optional **Postgres** backend (Neon or Supabase free tier). You only configure it with Streamlit **Secrets** — nothing database-related is stored in the public GitHub repo.

## Secrets to set

In **Streamlit Cloud → your app → Settings → Secrets**, add:

```toml
DATABASE_URL = "postgresql://USER:PASSWORD@HOST/DATABASE?sslmode=require"
APP_PASSWORD = "a-strong-private-password"
```

| Secret | Required when | Purpose |
|--------|----------------|---------|
| `DATABASE_URL` | Optional | Postgres connection string from Neon or Supabase. When set, the app loads and saves your data there automatically. |
| `APP_PASSWORD` | **Required** if `DATABASE_URL` is set | Stops strangers from opening your app and reading your portfolio. |

Do **not** commit these values to GitHub or share them in chat logs.

## Step-by-step (Neon)

1. Go to [https://neon.tech](https://neon.tech) and create a free account.
2. Create a **new project** (any region close to you).
3. On the project dashboard, open **Connection details** and copy the **connection string** (Postgres).
4. In Streamlit Cloud, open your app → **Settings** → **Secrets**.
5. Paste the template above: put the connection string in `DATABASE_URL`, and choose a private `APP_PASSWORD`.
6. Click **Save**, then **Reboot app** (or trigger a redeploy).
7. Open the app, sign in with `APP_PASSWORD`, and open **Storage & help** in the sidebar and check: **“Your data is saved in the cloud”**.
8. Upload a sample portfolio or run research once. Reboot the app again — your data should still be there.

## Step-by-step (Supabase)

1. Go to [https://supabase.com](https://supabase.com) and create a project.
2. Open **Project Settings → Database** and copy the **URI** connection string (mode: Session or Transaction).
3. Use the same Secrets block as above in Streamlit Cloud.
4. Save, reboot, and confirm the cloud status under **Storage & help**.

## Without cloud database

If you do **not** set `DATABASE_URL`, the app keeps using local **SQLite** files (fine for your laptop). On Streamlit Cloud you will see **“Temporary session”** — use **Import & backup** in the sidebar to download `.db` backups between sessions.

## Troubleshooting

- **Wrong connection string:** the app shows a warning and falls back to temporary local storage until `DATABASE_URL` is fixed.
- **Missing `APP_PASSWORD` with cloud enabled:** the app will not start until you add a password in secrets.
- **Still empty after reboot:** make sure you saved secrets and rebooted; upload data or run research **after** the cloud banner appears.

## Technical note

The app stores three blobs in Postgres (`research.db`, `portfolio.db`, `ui_prefs.json`). Your normal workflow is unchanged; sync runs on each app session when `DATABASE_URL` is set.
