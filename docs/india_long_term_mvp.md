# India long-term research MVP

This module ranks Indian equities for further research. It does not place orders and its output is
not investment advice.

## Data contracts

The current universe provider downloads the latest Nifty 50, Nifty 100, or Nifty 200 constituent
file from the official NSE archive. The price provider uses `yfinance` for personal research and
normalizes daily observations into these columns:

`date, symbol, open, high, low, close, adj_close, volume`

The long-term scorer accepts one row per company. Percentage-like fields must be decimals: use
`0.18` for 18%, not `18`. Start with `examples/india_fundamentals_template.csv`.

## Commands

```powershell
python -m src.investing.cli universe --index "NIFTY 50" --output work/nifty50.csv

python -m src.investing.cli universe --index "NIFTY 50" `
  --database work/research.db --persist --effective-date 2024-03-31

python -m src.investing.cli prices RELIANCE INFY HDFCBANK `
  --start 2020-01-01 --end 2026-01-01 --output work/prices.csv

python -m src.investing.cli score examples/india_fundamentals_template.csv

python -m src.investing.cli filings INFY --period Quarterly --database work/research.db

python -m src.investing.cli filings INFY --period Quarterly `
  --database work/research.db --download-xbrl

python -m src.investing.cli filings INFY --period Quarterly `
  --database work/research.db --normalize-xbrl

python -m src.investing.cli fundamentals INFY --as-of 2024-05-31 `
  --database work/research.db --output work/infy-fundamentals.csv

python -m src.investing.cli fundamentals INFY --as-of 2024-05-31 `
  --database work/research.db --fetch-prices --prices-start 2023-01-01 `
  --prices-end 2024-06-01 --score --output work/infy-research.csv

python -m src.investing.cli fundamentals INFY --as-of 2024-05-31 `
  --database work/research.db --fetch-prices --prices-start 2023-01-01 `
  --prices-end 2025-06-01 --persist --benchmark-index "NIFTY 50"

python -m src.investing.cli walkforward INFY HDFCBANK `
  --as-of-dates 2023-05-31 2024-05-31 --database work/research.db `
  --fetch-prices --prices-start 2022-01-01 --prices-end 2025-06-01 `
  --benchmark-index "NIFTY 50" --persist --output work/walkforward.csv

python -m src.investing.cli walkforward INFY `
  --quarter-range-start 2024-04-01 --quarter-range-end 2025-03-31 `
  --cadence quarterly --database work/research.db `
  --fetch-prices --prices-start 2023-01-01 --prices-end 2025-06-01 `
  --benchmark-index "NIFTY 50" --benchmark-portfolio --historical-constituents `
  --summary --persist

python -m src.investing.cli filings HDFCLIFE --period Quarterly `
  --database work/research.db --download-xbrl --validate-insurance
```

The `filings` command needs no API key. It saves an immutable copy of each distinct NSE response
and normalized point-in-time metadata in SQLite. With `--download-xbrl`, it also downloads every
linked document not already present, archives the original bytes, and parses the facts. Repeating
either import does not duplicate rows.

Parsed facts retain the taxonomy namespace and concept, entity, reporting context, period,
dimensions, unit, decimals, raw value, and exact numeric text. This prevents a consolidated fact,
segment fact, quarterly duration, or balance-sheet instant from being mixed into the wrong
fundamental calculation. The tables are:

- `xbrl_documents`: immutable source bytes and document metadata;
- `filing_xbrl_documents`: filing-to-document lineage;
- `xbrl_facts`: context-rich facts ready for deterministic normalization.
- `canonical_financial_facts`: versioned mappings from source facts to stable statement metrics.

New XBRL downloads are normalized automatically. Use `--normalize-xbrl` to refresh mappings for
documents already stored after the mapping rules change. The current canonical layer supports:

- non-financial Ind AS companies;
- banks using the NSE `BANKING` taxonomy; and
- NBFCs using the NSE `NBFC_INDAS` taxonomy.

Primary facts have no XBRL dimensions. Segment and other dimensional facts are retained in the
canonical table with `is_primary = 0`, so they cannot silently enter company-level calculations.
Insurance canonical facts and industry-specific fundamental ratios are supported when NSE
insurance XBRL taxonomies validate successfully.

## Fundamental calculation conventions

The `fundamentals` command uses only primary canonical facts whose filing timestamp is on or before
the requested `--as-of` cutoff. It prefers consolidated facts over standalone facts for the same
period and selects the latest public revision available at that time.

For non-financial companies it calculates:

- ROE = attributable net income / average opening and closing equity;
- ROCE = EBIT / average capital employed, where EBIT is profit before tax plus finance cost;
- operating margin = (profit before tax + finance cost - other income) / revenue;
- debt/equity and EBIT interest coverage;
- three-year revenue and earnings CAGR from full-year duration contexts; and
- free cash flow = operating cash flow - absolute reported PPE and intangible capex.

Banks use average equity/assets, pre-provision operating margin, pre-tax margin, NPA, and CET1
facts. NBFCs use average equity/assets, pre-tax margin, and funding leverage. Industrial ROCE and
interest coverage are deliberately not applied to banks.

ROE and ROA use average balance-sheet values, consistent with the CFA Institute's ratio treatment.
Free cash flow is explicitly labeled as this project's convention because IFRS does not define one
mandatory FCF subtotal; IAS 7 supplies the operating and investing cash-flow classifications used
by the calculation:

- https://rpc.cfainstitute.org/sites/default/files/-/media/documents/article/position-paper/cfa-leasing-paper.pdf
- https://www.ifrs.org/issued-standards/list-of-standards/ias-7-statement-of-cash-flows/

Some legacy NSE files omit primary contexts or publish inconsistent context dates. The parser
reconstructs only the standard primary context IDs from their explicit reporting-period facts and
marks affected source facts with `context_inferred = 1`.

Only HTTPS documents on approved NSE hosts are downloaded. Response and archive expansion sizes
are bounded, redirects are revalidated, and XML external entities/DOCTYPE declarations are
rejected.

## Score interpretation

The score is a research prioritization tool, not a price target:

- `Strong candidate`: score of at least 75
- `Watchlist`: score of at least 60
- `Caution`: score of at least 45
- `Avoid`: score below 45
- `Insufficient data`: fewer than 60% of factors are present

Category weights are 30% quality, 25% growth, 20% financial strength, 20% valuation, and 5%
price discipline. Every transform and threshold is defined in `src/investing/scoring.py`
and `src/investing/scoring_profiles.py`.

Industry profiles:

- `non_bank`: ROE, ROCE, operating margin, leverage, interest coverage, valuation, and
  volatility.
- `bank`: ROE, ROA, pre-provision operating margin, gross NPA, CET1, valuation, and
  volatility. Prudential ratios use percentage points (1.2% NPA -> `1.2`).
- `nbfc`: ROE, ROA, pre-tax margin, funding leverage, valuation, and volatility.
- `insurance`: ROE, ROA, profit margin on premiums, investment income ratio, premium
  growth, equity to assets, valuation, and volatility.

When `entity_type` is present on a fundamentals row or snapshot, the scorer applies the
matching profile automatically. Insurance premium growth is stored in `revenue_cagr_3y`
using life or general premium metrics from archived XBRL facts.

## Market join conventions

The `fundamentals` command can join point-in-time market metrics with `--prices` or
`--fetch-prices`. Use `--score` to rank enriched snapshots directly with `LongTermScorer`.

- Price: last adjusted close on or before the `--as-of` calendar date.
- Shares outstanding: attributable net income divided by basic EPS from the latest
  selected annual filing.
- P/E: price divided by basic EPS; left empty when EPS is not positive.
- P/B: market capitalization divided by book equity.
- Free-cash-flow yield: free cash flow divided by market capitalization.
- Volatility: annualized standard deviation of daily adjusted-close returns over up to
  252 trading days, requiring at least 120 observations.

## Walk-forward research

The `walkforward` command evaluates multiple `--as-of-dates`, joins point-in-time market
metrics, scores the cross-section, and compares each symbol's forward return with an
official Nifty benchmark.

- Benchmark indices: `NIFTY 50` (`^NSEI`), `NIFTY 100` (`^CNX100`), `NIFTY 200`
  (`^CNX200`).
- Forward return horizon: `--forward-days` (default `365`).
- Persistence: `--persist` writes to `research_evaluations` and `research_snapshots` in
  the SQLite research database. Re-running the same evaluation replaces prior rows.

Output columns include `forward_return`, `benchmark_forward_return`, and
`excess_forward_return` for auditability. These are evaluation metrics and do not feed
back into the scorer.

## Insurance taxonomy validation

Validated life and general insurance taxonomies now map into `canonical_financial_facts`
when `--normalize-xbrl` runs on archived insurance filings. Use:

```powershell
python -m src.investing.cli filings HDFCLIFE --period Quarterly `
  --database work/research.db --download-xbrl --validate-insurance
```

The validator reports life versus general insurance concept coverage and missing core
facts. Canonical normalization uses the same taxonomy split. The `fundamentals` command
calculates ROE, ROA, profit margin on premiums, investment income ratio, premium CAGR,
and equity to assets for validated insurance filings.

## Quarterly walk-forward reporting

Use `--quarter-range-start` and `--quarter-range-end` to generate Indian fiscal quarter-end
as-of dates. Add `--benchmark-portfolio` to compare each symbol against an equal-weight
Nifty constituent portfolio and `--summary` for a compact report.

Record historical membership with `universe --persist --effective-date`, import a CSV with
`constituents import`, or check coverage with `constituents coverage`. Enable
`--historical-constituents` on walk-forward runs. The evaluator uses the latest recorded
constituent snapshot on or before each as-of date, falling back to current membership when
no snapshot exists.

### Long-format snapshot CSV

```csv
effective_date,symbol
2024-03-31,RELIANCE
2024-03-31,INFY
```

### Membership intervals

Use half-open `[valid_from, valid_to)` intervals to backfill fiscal quarter-end snapshots:

```powershell
python -m src.investing.cli constituents import-intervals `
  examples/nifty50_membership_intervals.example.csv --index "NIFTY 50" `
  --database work/research.db --quarter-range-start 2024-03-31 `
  --quarter-range-end 2024-09-30
```

### Wide membership matrix

```powershell
python -m src.investing.cli constituents import-wide `
  examples/nifty50_membership_wide.example.csv --index "NIFTY 50" `
  --database work/research.db
```

### Reconstitution change backfill

Download or normalize the official NSE inclusion/exclusion workbook, then replay changes
backward from current membership:

```powershell
python -m src.investing.cli constituents fetch-changes --index "NIFTY 50" `
  work/nifty50-changes.csv

python -m src.investing.cli constituents backfill --index "NIFTY 50" `
  --changes work/nifty50-changes.csv --anchor current `
  --quarter-range-start 2018-04-01 --quarter-range-end 2025-06-30 `
  --database work/research.db
```

If `fetch-changes` cannot read the legacy `.xls` workbook locally, download
`IndexInclExcl.xls` from NSE and pass `--input IndexInclExcl.xls`.

## Universe calibration

After persisting walk-forward research across a Nifty universe, analyze score buckets and
review industry threshold suggestions:

```powershell
python -m src.investing.cli calibrate --database work/research.db

python -m src.investing.cli calibrate --database work/research.db `
  --report thresholds --output work/threshold-suggestions.csv
```

The `calibrate` command does not change scores automatically. It reports how research views
correlated with forward returns and suggests poor/strong metric bounds from cross-sectional
snapshot distributions by `entity_type`.

## Scheduled constituent archival

Record the current official Nifty membership for the latest fiscal quarter-end. Safe to run
from cron because existing snapshots are skipped unless `--force` is used:

```powershell
python -m src.investing.cli constituents archive --all-indices `
  --database work/research.db
```

## Versioned scoring profiles

After reviewing calibration output, save and activate a new profile version explicitly:

```powershell
python -m src.investing.cli calibrate --database work/research.db `
  --report thresholds --output work/threshold-suggestions.csv

python -m src.investing.cli profiles apply --version 2 `
  --input work/threshold-suggestions.csv --database work/research.db --activate

python -m src.investing.cli walkforward INFY --as-of-dates 2024-05-31 `
  --database work/research.db --fetch-prices --prices-start 2023-01-01 `
  --prices-end 2025-06-01 --use-active-profile --persist
```

Built-in thresholds remain version 1 (`BASELINE_PROFILE_VERSION`). Saved profile versions
override the scorer only when `--profile-version` or `--use-active-profile` is supplied.

## Score explanations

Deterministic explanations are available after a persisted research snapshot exists:

```powershell
python -m src.investing.cli fundamentals INFY --as-of 2024-05-31 `
  --database work/research.db --fetch-prices --prices-start 2023-01-01 `
  --prices-end 2025-06-01 --persist --explain

python -m src.investing.cli explain INFY --as-of 2024-05-31 `
  --database work/research.db --from-store
```

Explanations list the strongest score drivers, material risk flags, and the NSE filing
metadata behind the underlying fundamental snapshot. They do not recalculate scores.

## Research dashboard

Launch a local Streamlit dashboard over persisted research snapshots:

```powershell
python -m src.investing.cli dashboard --database work/research.db
```

The dashboard reads `research_evaluations`, `research_snapshots`, `research_explanations`,
and `research_orchestration_runs` from the SQLite research database. It shows overview counts,
filterable snapshot tables, category scores, benchmark comparisons, grounded score
explanations, profile version review, and orchestration run history. It does not place trades
or recalculate scores.

## Universe orchestration

Run walk-forward research across an entire Nifty index in one command. Suitable for cron or
Task Scheduler after constituent archival:

```powershell
python -m src.investing.cli constituents archive --all-indices `
  --database work/research.db

python -m src.investing.cli orchestrate --index "NIFTY 50" `
  --quarter-range-start 2024-04-01 --quarter-range-end 2025-03-31 `
  --prices-start 2023-01-01 --prices-end 2025-06-01 `
  --database work/research.db --archive-constituents `
  --historical-constituents --use-active-profile --explain --persist
```

The orchestrator evaluates each symbol independently, skips symbols without fundamentals,
persists snapshots (and optional explanations), records a run summary, and refreshes calibration
metrics for dashboard profile review. Use `--max-symbols` for partial test runs.

## Scheduled research workflows

Recurring archive and orchestration recipes live in
[`docs/india_research_scheduling.md`](india_research_scheduling.md).

```powershell
python -m src.investing.cli schedule show --database work/research.db

python -m src.investing.cli schedule run-quarterly --database work/research.db

powershell -NoProfile -ExecutionPolicy Bypass -File scripts\india-research-quarterly.ps1
```

Copy `scripts/india-research-quarterly.env.example` to configure database paths, index
selection, and feature flags for cron or Task Scheduler wrappers.

## Orchestration notifications

Universe runs can optionally notify operators when symbols are skipped:

```powershell
python -m src.investing.cli orchestrate --index "NIFTY 50" `
  --quarter-range-start 2024-04-01 --quarter-range-end 2025-03-31 `
  --prices-start 2023-01-01 --prices-end 2025-06-01 `
  --database work/research.db --notify skipped `
  --notify-webhook https://example.com/hooks/orchestration
```

See [`docs/india_research_scheduling.md`](india_research_scheduling.md) for file and SMTP
configuration via environment variables.

The **Profile review** tab now includes the latest orchestration run calibration summary:
score buckets, threshold suggestions, skipped-symbol counts, and a reminder to apply reviewed
profiles with `profiles apply --activate`. Older runs without persisted calibration are
recomputed from matching snapshots.

Compare profile versions before activation in the dashboard **Profile review** tab or via CLI:

```powershell
python -m src.investing.cli profiles diff --base-version 1 --compare-version 2 `
  --database work/research.db --changed-only --against-calibration
```

The diff table shows poor/strong threshold changes by entity type. When an orchestration run is
selected above, the dashboard also flags candidate thresholds that do not match calibration
suggestions.

## Next data milestone

Add one-click profile activation from the dashboard after diff review.
