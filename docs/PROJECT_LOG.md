# AI Investment Manager — Project Record

This file is the durable record of the project's goal, important decisions, implemented changes,
verification, and next milestones. Update it whenever behavior, architecture, data contracts, or
project direction changes.

## Product goal

Build a private, India-focused research assistant that helps a long-term investor identify
companies worth investigating. The initial investment horizon is three to five years.

The system should:

- rank Indian listed companies using transparent financial and valuation factors;
- explain why a company received its score and identify material risks;
- use information that was publicly available on the historical evaluation date;
- compare research results with an appropriate Nifty benchmark; and
- keep numerical calculations deterministic and auditable.

## Current non-goals

- Placing, modifying, or cancelling broker orders.
- Autonomous portfolio management.
- Intraday trading, options, futures, leverage, or high-frequency strategies.
- Guaranteed returns or exact share-price predictions.
- Allowing an LLM to calculate or override financial scores.

OpenAlgo remains a separate repository and is not required for the research-only phase.

## Product language

The application produces research classifications rather than personalized trade instructions:

- `Strong candidate`
- `Watchlist`
- `Caution`
- `Avoid`
- `Insufficient data`

These labels prioritize further research. They are not buy or sell recommendations.

## Architecture decisions

### 1. Extend FinRL-X without using its execution layer

The repository began as a fork of FinRL-X. The India research module lives in `src/investing/`
and does not import or call `src/trading/`. Existing Alpaca and execution code is left unchanged.

### 2. Keep data providers replaceable

Market data acquisition is separate from scoring. The initial providers are:

- `NiftyIndexUniverseProvider`: current Nifty 50, Nifty 100, or Nifty 200 constituents from
  official NSE/Nifty sources;
- `YFinancePriceProvider`: normalized historical prices for personal research and prototyping.

This boundary allows a broker or licensed data provider to replace `yfinance` later without
rewriting the scoring engine.

### 3. Start with deterministic scoring

The initial score is based on documented thresholds instead of an opaque trained model. Category
weights are:

| Category | Weight |
| --- | ---: |
| Business quality | 30% |
| Growth consistency | 25% |
| Financial strength | 20% |
| Valuation | 20% |
| Price discipline | 5% |

Missing metrics reduce the reported data coverage. A company with less than 60% coverage is not
ranked and receives `Insufficient data`.

### 4. Treat point-in-time correctness as mandatory

Historical evaluation must use the exchange filing timestamp, not merely the financial period end
date. Filing revisions must be retained. This prevents a backtest from using results before the
market could have known them.

### 5. Use AI for explanation, not arithmetic

An LLM may eventually summarize filings, describe score drivers, and list risks. Financial ratios,
scores, rankings, and backtest results remain deterministic.

## Implemented changes

### 2026-09-28 — India long-term research foundation

Added:

- `src/investing/providers.py`
  - downloads Nifty 50/100/200 constituent files;
  - retries temporary failures and uses a second official source;
  - normalizes NSE symbols;
  - downloads daily prices through `yfinance`;
  - returns long-form OHLCV data;
  - contains no brokerage or order operations.
- `src/investing/scoring.py`
  - scores quality, growth, financial strength, valuation, and volatility;
  - reports category scores and total data coverage;
  - rejects duplicate or blank symbols;
  - withholds rankings when data coverage is insufficient.
- `src/investing/cli.py`
  - `universe` command for current index constituents;
  - `prices` command for historical prices;
  - `score` command for normalized fundamentals;
  - concise errors for provider and input failures.
- `examples/india_fundamentals_template.csv`
  - documents the normalized scoring input columns and decimal percentage convention.
- `docs/india_long_term_mvp.md`
  - documents commands, data contracts, score interpretation, and the next data milestone.
- `tests/`
  - provider normalization and retry coverage;
  - malformed upstream-file handling;
  - price-response normalization;
  - ranking, missing-data, and duplicate-symbol behavior.
- `.gitignore`
  - ignores local `work/` outputs.
- `README.md`
  - identifies the fork's India-focused, research-only direction.

No existing trading or Alpaca module was modified. No commit or push was performed.

### 2026-09-28 — Point-in-time NSE filing metadata

Goal:

- Establish an auditable foundation for historical fundamentals without using future information.

Changes:

- Added `src/investing/filings.py`.
- Added an NSE financial-results client for quarterly and annual filing metadata.
- Added retry behavior and clear provider errors.
- Added timezone-aware parsing for filing, broadcast, and exchange-dissemination timestamps.
- Added SQLite storage with separate tables for immutable raw response snapshots and normalized
  filing metadata.
- Added deterministic filing keys, snapshot hashes, and idempotent imports.
- Added point-in-time queries that return only records publicly timestamped by the requested date.
- Retained legacy records whose publication time is unavailable, but excluded them from
  point-in-time queries.
- Added the `filings` CLI command. It requires no API key and does not connect to order execution.

Decisions:

- Preserve raw NSE responses so every normalized field remains auditable.
- Store timestamps in ISO 8601 with the `Asia/Kolkata` offset.
- Treat `-`, `NA`, `N/A`, `None`, and similar placeholders as missing values.
- Do not infer publication dates for legacy filings; an invented date would invalidate historical
  evaluation.
- Defer XBRL accounting-fact parsing until metadata storage and point-in-time semantics are proven.

### 2026-09-28 — NSE XBRL document and fact ingestion

Goal:

- Archive the financial statements linked from NSE filing metadata and expose auditable raw facts
  for automatic fundamentals calculations.

Changes:

- Added `src/investing/xbrl.py` with an NSE-only streaming downloader and deterministic parser.
- Added bounded downloads, retry handling, redirect host validation, ZIP instance discovery, and
  protections against oversized archives and XML external-entity documents.
- Preserved taxonomy namespaces, concepts, entities, duration/instant periods, dimensions, units,
  decimals, source text, and exact numeric text for every fact.
- Added immutable document storage, filing-to-document lineage, parsed fact storage, pending-link
  queries, idempotent ingestion, and concept queries to `FilingStore`.
- Added `--download-xbrl` to the `filings` command for end-to-end metadata and statement ingestion.
- Added deterministic tests for parsing, ZIP handling, retry and redirect safety, idempotent
  storage, fact queries, and DOCTYPE rejection.

Decisions:

- Store raw source bytes in SQLite so normalized calculations remain reproducible and auditable.
- Keep the first fact layer taxonomy-neutral. Fundamental formulas will use an explicit canonical
  mapping rather than silently assuming similarly named facts have the same meaning across banks,
  NBFCs, insurers, and non-financial companies.
- Preserve numeric values as exact decimal text instead of converting accounting amounts to
  binary floating point during ingestion.

Remaining work:

- Map taxonomy-specific concepts and contexts into canonical financial statements by company type.
- Calculate historical scoring inputs and connect them to prices and point-in-time ranking.

### 2026-09-28 — Canonical financial statement facts

Goal:

- Convert raw taxonomy concepts into stable statement metrics without losing source lineage or
  mixing primary company facts with segment facts.

Changes:

- Added `src/investing/fundamentals.py` with explicit concept mappings for non-financial Ind AS,
  `BANKING`, and `NBFC_INDAS` filings.
- Added canonical income statement, balance-sheet, cash-flow, and bank prudential metric names.
- Corrected NSE entity classification so code `B` maps to `bank` and code `F` maps to `nbfc`.
- Added versioned `canonical_financial_facts` storage linked to the original filing, document, and
  source fact order.
- New downloads now normalize automatically; `--normalize-xbrl` refreshes already archived data.
- Primary facts are identified only when the XBRL context has no dimensions. Dimensional facts are
  retained with `is_primary = 0` for future segment analysis.
- Added filtered canonical fact queries and canonical/primary fact counts.
- Fixed SQLite connection cleanup after a live Windows test exposed an open file handle.

Decisions:

- Keep mapping separate from ratio calculation. A mapped fact is source data, not an inferred
  fundamental.
- Skip concepts whose actual duration/instant context conflicts with the mapping contract.
- Do not coerce unsupported insurance filings into non-financial mappings. Raw documents can still
  be archived while canonical output remains empty until that taxonomy is validated.
- Map bank `CapitalAndLiabilities` to `total_assets` because it is the balance-sheet total under the
  banking taxonomy, while retaining the source concept for auditability.

Remaining work:

- Select revision-safe annual and quarterly canonical observations as of an evaluation timestamp.
- Calculate historical scoring inputs and connect them to prices and point-in-time ranking.

### 2026-09-28 — Point-in-time fundamental calculations

Goal:

- Calculate deterministic, company-type-appropriate fundamentals from canonical facts using only
  filings public by an evaluation timestamp.

Changes:

- Added `FundamentalCalculator` and versioned `FundamentalSnapshot` output.
- Added full-year context detection, three-year growth history, average balance-sheet denominators,
  revision selection, and consolidated-over-standalone preference.
- Added non-financial ROE, ROCE, operating margin, leverage, interest coverage, and free cash flow.
- Added bank ROE/ROA, pre-provision margin, pre-tax margin, gross NPA, and CET1 output without
  applying inappropriate industrial leverage or coverage formulas.
- Added NBFC ROE/ROA, pre-tax margin, growth, and funding leverage.
- Added `canonical_observations_as_of` and the `fundamentals --as-of` CLI command.
- Added source filing keys and calculation versions to every snapshot.
- Added support for legacy NSE documents that omit primary contexts or publish primary context
  dates inconsistent with their own reporting-period facts. Reconstructed contexts are marked with
  `context_inferred = 1`.
- Added schema migration for existing databases that predate precision and inferred-context fields.

Decisions:

- Require full-year duration contexts for annual ratios and CAGR calculations.
- Use average opening and closing equity/assets/capital employed for return ratios.
- Define project free cash flow as operating cash flow less absolute reported PPE and intangible
  capex. IFRS does not prescribe one mandatory free-cash-flow subtotal, so the convention is
  documented rather than presented as an accounting-standard measure.
- Leave P/E, P/B, free-cash-flow yield, and volatility empty until a point-in-time price/share-count
  join is implemented. Using a current market price in a historical snapshot would create lookahead
  bias.

Remaining work:

- Add point-in-time market price, shares outstanding, and volatility inputs.
- Produce complete scorer rows automatically and persist walk-forward snapshots.

## Verification record

### 2026-09-28

- `python -m pytest tests -q`: **7 passed**.
- `python -m black --check src/investing tests`: **passed**.
- `python -m compileall -q src/investing`: **passed**.
- `git diff --check`: **passed**.
- Live Nifty 50 universe download: **50 constituents returned**.
- Live price smoke test: **14 daily rows returned for RELIANCE and INFY** for the selected range.
- Example score command: **completed successfully** and produced a `Watchlist` result.

The first NSE request timed out once. The provider was then updated with retry behavior, a fallback
source, and browser-compatible request headers; the repeated live check succeeded.

### 2026-09-28 — Filing importer verification

- `python -m pytest tests -q`: **11 passed**.
- `python -m black src/investing tests`: **passed; files unchanged after formatting**.
- Live `INFY` quarterly import: **144 normalized filings inserted**.
- Immediate repeated import: **0 new filings inserted**, confirming idempotency.
- Legacy missing-timestamp behavior: covered by a regression test and excluded from as-of results.
- A failed first live attempt wrote **0 raw and 0 normalized rows**, confirming transactional
  rollback on normalization errors.

### 2026-09-28 — XBRL importer verification

- `python -m pytest tests -q`: **16 passed**.
- `python -m black --check src/investing tests`: **passed after formatting**.
- `python -m compileall -q src/investing`: **passed**.
- `git diff --check`: **passed**.
- Live INFY NSE document smoke test: **36,326 bytes and 148 facts parsed**.
- Live fact checks returned quarterly revenue of `349150000000.00` INR and profit of
  `63580000000.00` INR for 2024-10-01 through 2024-12-31.

### 2026-09-28 — Canonical mapping verification

- `python -m pytest tests -q`: **21 passed**.
- `python -m black --check src/investing tests`: **passed**.
- `python -m compileall -q src/investing`: **passed**.
- `git diff --check`: **passed**.
- Live consolidated filing checks succeeded for `INFY` (`non_bank`), `HDFCBANK` (`bank`), and
  `BAJFINANCE` (`nbfc`).
- The three live documents produced **28**, **36**, and **36** primary canonical facts,
  respectively, with company-type-specific metrics.
- Temporary SQLite databases were removed successfully after connection lifecycle repair.

### 2026-09-28 — Fundamental calculation verification

- `python -m pytest tests -q`: **26 passed**.
- `python -m black --check src/investing tests`: **passed**.
- `python -m compileall -q src/investing`: **passed**.
- `git diff --check`: **passed**.
- Live four-year consolidated INFY calculation completed as of **2024-05-31** using filings for
  FY2021 through FY2024.
- The live snapshot selected FY2024 and calculated ROE, ROCE, operating margin, three-year revenue
  and earnings CAGR, leverage, coverage, and free cash flow with source filing keys.
- Live validation discovered two legacy NSE files with omitted primary contexts and two newer files
  with incorrect `FourD` context starts; both variants are now covered by parser repair tests.

## Data-source plan

### Prototype

- Universe: official Nifty constituent downloads.
- Prices: `yfinance`, restricted to private research/prototyping.
- Fundamentals: normalized CSV input until the NSE filing importer is complete.

### Intended production-quality research pipeline

- Official NSE quarterly and annual financial-result filings.
- Filing timestamps and revision history.
- Official annual reports and corporate disclosures.
- Adjusted price history with documented corporate-action handling.
- Optional licensed or broker data provider behind the existing provider interface.

## Next milestones

1. Join point-in-time prices and shares to calculate P/E, P/B, free-cash-flow yield, and volatility.
2. Feed complete calculated snapshots into the scorer and persist walk-forward results.
3. Validate an insurance filing source and taxonomy separately.
4. Add quarterly historical snapshots and walk-forward evaluation against a Nifty benchmark.
5. Add score explanations and risk summaries grounded in saved source documents.
6. Build a small research dashboard after the data and evaluation pipeline is trustworthy.

## Known limitations

- Valuation and price-discipline scoring inputs still require a point-in-time market-data join.
- The initial thresholds are general-purpose and are not yet calibrated by industry.
- `yfinance` is an unofficial personal-research source and should not become a commercial data
  dependency.
- Current index downloads describe today's membership; historical backtests will need historical
  constituent membership to avoid survivorship bias.
- The scorer is a prioritization baseline, not evidence that a company will outperform.

## Update template

Append future work under **Implemented changes** and **Verification record** using this structure:

```markdown
### YYYY-MM-DD — Short change title

Goal:

- What outcome the change was intended to achieve.

Changes:

- Files and observable behavior added or changed.

Decisions:

- Important choices and their reasons.

Verification:

- Exact commands run and their results.

Remaining work:

- Known limitations or the next safe step.
```
