# Zerodha portfolio tracker (Windows)

This guide helps you track a personal Zerodha portfolio (stocks in **Kite**, mutual funds in
**Coin**) inside the India investing module. The tracker is **read-only**: it never places orders.

## What you need

- Windows 10 or 11 with Python 3.11+ installed
- This repository cloned locally
- Optional: a [Kite Connect](https://kite.trade/docs/connect/v3/) developer app for API sync

## 1. Set up Python

Open **PowerShell** in the project folder:

```powershell
cd C:\path\to\ai-investment-manager
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install pandas numpy requests yfinance streamlit pytest openpyxl
```

## 2. Export files from Zerodha Console (no API key)

1. Sign in to [Zerodha Console](https://console.zerodha.com/).
2. **Equity holdings** (Kite): Reports → Holdings → Download CSV (or Excel).
3. **Tradebook** (for XIRR): Reports → Tradebook → choose date range → Download CSV.
4. **Mutual fund holdings** (Coin): Reports → Mutual funds → Holdings → Download CSV.

Save the files somewhere convenient, for example `C:\Users\You\Downloads\`.

You can try the feature first with the anonymized samples in `examples\zerodha_portfolio\`.

## 3. Import into the local portfolio database

```powershell
mkdir work -Force

python -m src.investing.cli portfolio load-examples --database work\portfolio.db

# Or import your own Console exports:
python -m src.investing.cli portfolio import --kind equity-holdings `
  --database work\portfolio.db C:\Users\You\Downloads\holdings.csv

python -m src.investing.cli portfolio import --kind tradebook `
  --database work\portfolio.db --replace-trades C:\Users\You\Downloads\tradebook.csv

python -m src.investing.cli portfolio import --kind mf-holdings `
  --database work\portfolio.db C:\Users\You\Downloads\mf_holdings.csv
```

Check the summary in the terminal:

```powershell
python -m src.investing.cli portfolio show --database work\portfolio.db
```

## 4. Open the dashboard

```powershell
python -m src.investing.cli dashboard `
  --database work\research.db `
  --portfolio-database work\portfolio.db
```

Open the URL Streamlit prints (usually `http://localhost:8501`) and select the **Portfolio** tab.

The tab shows:

- Stocks and mutual funds separately, plus combined allocation
- Invested amount, current value, P&L, absolute return, and XIRR (when a tradebook is imported)
- Benchmark comparison (default **NIFTY 50**)
- Research score linkage for stocks when matching symbols exist in `work\research.db`

## 5. Optional: Kite Connect read-only sync

You need a Kite Connect app from Zerodha. Generate a **daily access token** using the standard
Kite login flow (documented on the Kite Connect site). This project only calls:

- `GET /portfolio/holdings` (equity)
- `GET /mf/holdings` (mutual funds)

### Configure credentials

**Option A — environment variables (PowerShell session):**

```powershell
$env:KITE_API_KEY = "your_api_key"
$env:KITE_ACCESS_TOKEN = "your_access_token_for_the_day"
```

**Option B — local file (gitignored):**

Copy `examples\kite.local.json.example` to `work\kite.local.json` and fill in values.

### Sync holdings

```powershell
python -m src.investing.cli portfolio sync-kite --database work\portfolio.db
```

Re-open or refresh the dashboard **Portfolio** tab.

## 6. Mutual fund peer comparison

Category peers use AMFI scheme categories and cached NAV history (mfapi.in). Load the scheme
master once, then refresh peer metrics from the dashboard or CLI:

```powershell
python -m src.investing.cli portfolio sync-mf-master --database work\portfolio.db

python -m src.investing.cli portfolio mf-peers --database work\portfolio.db `
  --sync-master --output work\mf-peer-summary.csv
```

In the dashboard **Portfolio** tab:

- Each held mutual fund shows 1Y / 3Y / 5Y CAGR, rolling 1Y median, category rank,
  percentile, category average, and top peers (Direct vs Regular and Growth vs IDCW are kept
  separate).
- Underperformers (bottom ~30% on 3Y CAGR vs category peers) are flagged.
- Use **Manual fund comparison** to pick any schemes side by side.

## Limitations

- Stock prices use `yfinance` (`.NS` symbols) for personal research, not live NSE ticks.
- Mutual fund NAVs use AMFI public data; scheme codes must be present in imports.
- XIRR uses tradebook cash flows plus current holdings value; MF purchases without a tradebook
  rely on average NAV in the holdings export.
- Benchmark history is approximated from equity trade history; mutual fund timing is not fully
  modeled in the benchmark chart.
- Kite access tokens expire daily; Console CSV import remains the reliable fallback.
- MF peer rankings depend on AMFI category labels and cached NAV coverage; the first peer run
  may take time while NAV histories download.
- mfapi.in and AMFI are unofficial public sources suitable for personal research.
