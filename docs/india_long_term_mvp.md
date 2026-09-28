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
Insurance remains explicit and unsupported until its filing source and taxonomy are validated.

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
price discipline. Every transform and threshold is defined in `src/investing/scoring.py`.

## Next data milestone

Join point-in-time price and share-count data to calculate P/E, P/B, free-cash-flow yield, and price
volatility, then feed the complete snapshots directly into `LongTermScorer`.
