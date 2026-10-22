# Getting started with your wealth dashboard

You can use this app from your browser. You do not need Python, database settings, or the command line.

## Try it first

1. Open **Dashboard**. If you have not uploaded files or connected Zerodha, the app shows **example data** automatically (with a banner). Add real holdings via **Import & backup** or the upload buttons on Dashboard.
2. Open **Portfolio** to see stocks, mutual funds, invested amounts and profit or loss.
3. Open **My mutual funds** for fund charts, or **Compare funds** to compare funds in the same category.

## Add your own holdings

1. Open Zerodha Console and download your stock and mutual fund holdings as CSV or Excel files.
2. On Dashboard click **Upload my portfolio**, then upload each file into its matching box.
3. Optionally upload your trade history. It helps calculate annual returns and portfolio history.
4. Return to **Dashboard** or **Portfolio** to see your investments.

A holdings upload replaces the holdings of that type. A trade-history upload replaces the previous
trade history, so upload the full period you want to analyse. Download a backup first if you want
to keep the previous version. Example data lives in a separate demo database until you upload real holdings; uploads replace example data in your personal database.

## Find and compare funds

Open **Top mutual funds** and click **Refresh fund list** the first time. Choose a category,
plan and return period, then **Load rankings**. Refresh the list about once a week.
An annual return of 12% means the fund grew by about 12% per year over that period.
Past returns do not promise future returns.

## Understand your numbers

- **Total value**: the estimated value of your holdings using available prices.
- **Profit or loss**: value minus what you invested.
- **Annual return (XIRR)**: a yearly return that considers when money was invested.
- **A dash**: a number is unavailable; it does not mean zero.
- **Compare funds**: other mutual funds in the same category.

Portfolio opens with saved values. Click **Update prices & charts** for fresh market data.
Prices and charts depend on available data and may be out of date. Open **Storage & help**
in the sidebar for the glossary and your storage status.

## Keep a backup

Open **Import & backup** to download your portfolio and research backups. If cloud saving is
unavailable, keep a backup after important changes. On a hosted app, local files can disappear
after a restart. On your laptop, local files remain until removed. Ask the app owner to set up
cloud saving; you do not need to change technical settings yourself.

The app uses one shared workspace. People with its password see the same holdings; there are
no separate personal accounts. It reads files and public data and does not place trades.

## Optional stock research

You can ignore this group when you only want to track holdings. **Run research** creates scores,
**Saved research** shows saved results, **Scoring settings** manages scoring rules, and **Research runs**
shows research-run history. Scores help organise research and are not buy or sell instructions.


## Connect instead of uploading

Choose **Connect Zerodha** on Dashboard. The read-only connection needs a Kite Connect API key
and a current access token. Credentials are used for that sync and are not saved to files or the
cloud database. If you do not have them, use **Upload my portfolio** with Console exports.
This connection loads stock and fund holdings; trade history still comes from your Console export.

## Stay signed in

Leave **Remember me for 30 days** selected when you sign in. A signed token is stored in your
browser and verified again after refresh. Cookies and browser storage are supported; the password
itself is never saved. Clearing browser data, changing the app password or token expiry requires
another sign-in. Private browsing or blocked browser storage can prevent persistence.


Connected Coin holdings retain their broker ISIN and last available value. Fund-history and peer
charts require a numeric AMFI scheme code; a unique match in the cached fund list is used when
available. Stock and fund quantities are not sent to public fund-data services.
