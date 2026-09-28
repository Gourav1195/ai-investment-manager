# India research scheduling

This guide documents recurring workflows for constituent archival and full Nifty universe
walk-forward orchestration. The commands are idempotent where possible and safe to run from
cron or Windows Task Scheduler.

## Quick start

Copy the example environment file and run the quarterly workflow:

```powershell
copy scripts\india-research-quarterly.env.example scripts\india-research-quarterly.env

powershell -NoProfile -ExecutionPolicy Bypass -File scripts\india-research-quarterly.ps1
```

On Linux or macOS:

```bash
cp scripts/india-research-quarterly.env.example scripts/india-research-quarterly.env
chmod +x scripts/india-research-quarterly.sh
./scripts/india-research-quarterly.sh
```

The wrapper scripts call:

```powershell
python -m src.investing.cli schedule run-quarterly
```

That command:

1. archives Nifty constituent membership when enabled;
2. resolves the latest four Indian fiscal quarter-end as-of dates;
3. runs `orchestrate` across the selected index with historical constituents and the active
   scoring profile when configured;
4. persists snapshots, explanations, and an orchestration run summary.

## Show generated recipes

Print copy-paste cron and Task Scheduler commands for the current machine:

```powershell
python -m src.investing.cli schedule show --database work/research.db
```

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `INVESTING_RESEARCH_DB` | `work/research.db` | SQLite research database path |
| `INVESTING_INDEX` | `NIFTY 50` | Universe index for orchestration |
| `INVESTING_BENCHMARK_INDEX` | `NIFTY 50` | Benchmark index symbol |
| `INVESTING_QUARTERS` | `4` | Rolling fiscal quarter-ends to evaluate |
| `INVESTING_PRICE_LOOKBACK_YEARS` | `3` | Price history before the first as-of date |
| `INVESTING_FORWARD_DAYS` | `365` | Forward-return evaluation window |
| `INVESTING_ARCHIVE_ALL_INDICES` | `true` | Archive Nifty 50/100/200 before orchestration |
| `INVESTING_ARCHIVE_CONSTITUENTS` | `true` | Run constituent archival step |
| `INVESTING_HISTORICAL_CONSTITUENTS` | `true` | Use recorded membership for benchmarking |
| `INVESTING_USE_ACTIVE_PROFILE` | `true` | Apply the active scoring profile version |
| `INVESTING_EXPLAIN` | `true` | Persist score explanations |
| `INVESTING_PERSIST` | `true` | Persist research snapshots |

## Linux cron

Run on the first day of each calendar quarter after market data is likely available:

```cron
15 6 1 */3 * cd /path/to/ai-investment-manager && python -m src.investing.cli constituents archive --all-indices --database work/research.db
30 6 1 */3 * cd /path/to/ai-investment-manager && python -m src.investing.cli schedule run-quarterly --database work/research.db
```

Or use the shell wrapper for the orchestration step:

```cron
30 6 1 */3 * cd /path/to/ai-investment-manager && ./scripts/india-research-quarterly.sh
```

## Windows Task Scheduler

Create a task that runs every three months on day 1 at 06:30:

```powershell
schtasks /Create /TN "IndiaResearchQuarterly" /SC MONTHLY /MO 3 /D 1 /ST 06:30 `
  /TR "powershell -NoProfile -ExecutionPolicy Bypass -File C:\path\to\ai-investment-manager\scripts\india-research-quarterly.ps1" `
  /F
```

Set the task's **Start in** directory to the repository root if you use relative database paths.

## Manual split workflow

When you want explicit control over each step:

```powershell
python -m src.investing.cli constituents archive --all-indices --database work/research.db

python -m src.investing.cli orchestrate --index "NIFTY 50" `
  --quarter-range-start 2024-09-30 --quarter-range-end 2025-06-30 `
  --prices-start 2021-09-30 --prices-end 2026-07-30 `
  --database work/research.db --historical-constituents `
  --use-active-profile --explain --persist
```

Use `schedule show` to print the rolling quarter and price windows for the current date.

## Operational notes

- Constituent archival skips existing fiscal quarter-end snapshots unless `--force` is used.
- Orchestration skips symbols without fundamentals instead of failing the full run.
- Review skipped symbols and orchestration history in the dashboard **Orchestration runs** tab.
- Activate reviewed calibration output with `profiles apply` before enabling
  `INVESTING_USE_ACTIVE_PROFILE=true`.

## Orchestration notifications

Optional notifications fire when a universe run skips symbols (default once a channel is
configured):

```powershell
python -m src.investing.cli orchestrate --index "NIFTY 50" `
  --quarter-range-start 2024-04-01 --quarter-range-end 2025-03-31 `
  --prices-start 2023-01-01 --prices-end 2025-06-01 `
  --database work/research.db --notify skipped `
  --notify-output work/orchestration-notifications.log
```

Supported channels:

- file append via `INVESTING_NOTIFY_OUTPUT` or `--notify-output`
- webhook POST via `INVESTING_NOTIFY_WEBHOOK_URL` or `--notify-webhook`
- SMTP email via `INVESTING_NOTIFY_EMAIL_TO` and `INVESTING_SMTP_*`

Set `INVESTING_NOTIFY_ON=always` to notify on every successful run, or `never` to disable
notifications even when webhook or email settings are present.
