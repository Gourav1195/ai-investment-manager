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

### 2026-09-28 — Point-in-time market join and scorer integration

Goal:

- Calculate P/E, P/B, free-cash-flow yield, and volatility using only market data
  available on or before the evaluation timestamp, then feed complete snapshots into
  `LongTermScorer`.

Changes:

- Added `src/investing/market.py` with `MarketMetricsJoiner` and
  `snapshots_to_scorer_frame`.
- Extended `FundamentalSnapshot` with accounting inputs (`latest_net_income`,
  `basic_eps`, `book_equity`) and market outputs (`price`, `shares_outstanding`,
  `pe`, `pb`, `free_cash_flow_yield`, `volatility_1y`).
- `FundamentalCalculator` now captures EPS and book equity for share-count and
  valuation joins.
- Extended the `fundamentals` CLI with `--prices`, `--fetch-prices`,
  `--prices-start`, `--prices-end`, and `--score`.
- Added `FundamentalSnapshot.to_scorer_row()` for direct scorer integration.
- Added `tests/test_market_join.py`.

Decisions:

- Use the last adjusted close on or before the as-of calendar date for point-in-time
  pricing. Daily bars do not carry an exchange timestamp, so intraday cutoffs are
  not applied to price rows.
- Derive shares outstanding as attributable net income divided by basic EPS when
  both are present and the result is positive. P/E remains empty for non-positive
  EPS.
- Compute free-cash-flow yield as free cash flow divided by market capitalization.
- Annualize one-year volatility from up to 252 prior trading days of adjusted
  closes, requiring at least 120 observations.
- Leave valuation and volatility fields empty until a price join is requested,
  preserving accounting-only snapshots without lookahead bias.

Remaining work:

- Persist walk-forward snapshots and benchmark comparisons.
- Validate an insurance filing source and taxonomy separately.

### 2026-09-28 — Walk-forward persistence and Nifty benchmark comparison

Goal:

- Persist scored research snapshots across multiple evaluation dates and compare each
  symbol's forward return with an official Nifty benchmark.

Changes:

- Added `src/investing/research.py` with `WalkForwardEvaluator`, `ResearchStore`, and
  `ResearchRecord`.
- Added SQLite tables `research_evaluations` and `research_snapshots` for idempotent
  walk-forward persistence in the research database.
- Added `walkforward` CLI command for multi-date evaluation, benchmark comparison, and
  optional persistence.
- Extended `fundamentals` with `--persist`, `--benchmark-index`, and `--forward-days`.
- Added Nifty benchmark symbol mapping in `providers.py` and public return helpers in
  `market.py`.
- Fixed Yahoo index ticker handling so symbols such as `^NSEI` are not suffixed with
  `.NS`.
- Added `tests/test_walkforward.py` and `tests/test_market_returns.py`.

Decisions:

- Benchmark mapping uses Yahoo Finance index tickers: `^NSEI`, `^CNX100`, and
  `^CNX200`.
- Forward returns are measured from the last price on or before each as-of date through
  the same rule at `as_of + forward_days`.
- Excess return is stock forward return minus benchmark forward return; both may remain
  empty when price history does not cover the horizon.
- Re-running the same evaluation replaces prior rows for that evaluation key rather
  than duplicating them.

Remaining work:

- Validate an insurance filing source and taxonomy separately.
- Add quarterly historical snapshots and richer walk-forward reporting against a Nifty
  benchmark portfolio.

### 2026-09-28 — Insurance taxonomy validation and quarterly walk-forward reporting

Goal:

- Validate NSE insurance XBRL taxonomies separately from canonical scoring mappings and
  add quarterly walk-forward snapshots with equal-weight Nifty portfolio benchmarking.

Changes:

- Added `src/investing/insurance.py` with life and general insurance concept sets and
  `InsuranceTaxonomyValidator`.
- Extended `FilingStore` with `insurance_filings` and `filing_concepts` helpers.
- Added `filings --validate-insurance` for archived insurance concept coverage reports.
- Added `fiscal_quarter_end_dates`, `walkforward_report`, and equal-weight portfolio
  forward-return comparison in `research.py`.
- Extended walk-forward persistence with `snapshot_cadence`, portfolio benchmark columns, and
  SQLite schema migration to store version 2.
- Extended `walkforward` CLI with quarter-range generation, `--benchmark-portfolio`,
  `--cadence`, and `--summary`.
- Added `tests/test_insurance.py` and expanded walk-forward and market return tests.

Decisions:

- Insurance remains unsupported for `FundamentalCalculator`; validation only reports
  concept coverage and does not coerce insurers into non-financial mappings.
- Life versus general insurance taxonomy is inferred from observed concept overlap.
- Quarterly history uses Indian fiscal quarter-end as-of dates (Jun/Sep/Dec/Mar).
- Portfolio benchmarking uses an equal-weight average of current Nifty constituent
  forward returns; this is a research comparison aid and still inherits current-membership
  survivorship limitations.

Remaining work:

- Promote validated insurance mappings into canonical facts after live taxonomy review.
- Add score explanations and risk summaries grounded in saved source documents.

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

### 2026-09-28 — Score explanation verification

- `python -m pytest tests -q`: **50 passed**.
- Score drivers, risk flags, filing lineage, and explanation persistence covered by
  `tests/test_explanations.py`.

### 2026-09-28 — Research dashboard verification

- `python -m pytest tests -q`: **53 passed**.
- Dashboard overview, filters, snapshot summary, and explanation detail covered by
  `tests/test_dashboard.py`.

### 2026-09-28 — Insurance canonical mapping verification

- `python -m pytest tests -q`: **46 passed**.
- Life and general insurance canonical mappings and filing-store normalization covered by
  expanded insurance and canonical fundamentals tests.

### 2026-09-28 — Insurance and quarterly walk-forward verification

- `python -m pytest tests -q`: **44 passed**.
- Insurance taxonomy validation, fiscal quarter date generation, portfolio benchmark
  reporting, and persistence migration covered by new and expanded tests.

### 2026-09-28 — Walk-forward verification

- `python -m pytest tests -q`: **38 passed**.
- Walk-forward scoring, benchmark excess returns, idempotent SQLite persistence, and
  Nifty benchmark symbol mapping covered by new tests.

### 2026-09-28 — Market join verification

- `python -m pytest tests -q`: **31 passed**.
- Point-in-time price selection, valuation ratios, volatility, and direct scorer
  integration covered by `tests/test_market_join.py`.

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

### 2026-09-28 — Insurance canonical fact mappings

Goal:

- Promote validated life and general insurance XBRL concepts into canonical facts without
  coercing insurers into non-financial mappings.

Changes:

- Added `INSURANCE_COMMON_MAPPINGS`, `LIFE_INSURANCE_MAPPINGS`, and
  `GENERAL_INSURANCE_MAPPINGS` in `fundamentals.py`.
- Extended `CanonicalFactMapper` to support `insurance` with life versus general taxonomy
  inference from archived facts.
- Bumped `MAPPING_VERSION` to 3 so insurance normalization is versioned separately.
- Added canonical normalization coverage in `tests/test_insurance.py` and mapping tests in
  `tests/test_canonical_fundamentals.py`.
- Ignored local `graphify-out/` artifacts in `.gitignore`.

Decisions:

- Insurance canonical mapping uses the same life versus general concept overlap rule as
  taxonomy validation.
- `FundamentalCalculator` remains insurance-agnostic until insurer-specific ratio rules are
  defined; canonical facts are available for audit and future scoring work.

Remaining work:

- Add score explanations and risk summaries grounded in saved source documents.

### 2026-09-28 — Grounded score explanations and risk summaries

Goal:

- Explain deterministic research scores and surface material risks using saved NSE
  filing metadata, without letting an LLM calculate or override scores.

Changes:

- Added `src/investing/explanations.py` with `ScoreExplainer` and `ResearchExplanation`.
- Added top score-driver summaries from weighted metric contributions and deterministic
  risk flags for leverage, valuation, volatility, growth, and data coverage.
- Extended `FilingStore.filing_summaries` to ground explanations in archived filing
  metadata and XBRL links.
- Added `FundamentalSnapshot.from_record` for explaining persisted research snapshots.
- Persisted explanations in `research_explanations` (research store version 3).
- Added `explain` CLI command plus `--explain` on `fundamentals` and `walkforward`.
- Added `tests/test_explanations.py`.

Decisions:

- Explanations are template-based and deterministic; they cite source filing keys and
  NSE metadata only.
- The `explain` command reads persisted snapshots with `--from-store`; fresh research
  runs can persist explanations alongside snapshots via `--explain`.

Remaining work:

- Build a small research dashboard after the data and evaluation pipeline is trustworthy.

### 2026-09-28 — Research dashboard

Goal:

- Provide a local UI for browsing persisted research snapshots, benchmark comparisons,
  and grounded score explanations without recalculating scores.

Changes:

- Added `src/investing/dashboard_data.py` with testable data-loading helpers.
- Added `src/investing/dashboard.py` Streamlit app for overview metrics, filters,
  snapshot tables, category charts, and explanation detail.
- Added `dashboard` CLI command to launch Streamlit against the research database.
- Extended `ResearchStore.list_evaluations` for evaluation-level browsing.
- Added `tests/test_dashboard.py`.

Decisions:

- The dashboard is read-only and uses persisted SQLite research data only.
- Streamlit is launched via the existing project dependency rather than a new web stack.
- Score explanations are shown when present; the UI does not regenerate them on load.

### 2026-09-28 — Industry scoring profiles and historical Nifty constituents

Goal:

- Apply entity-type-specific scorer thresholds and support point-in-time Nifty portfolio
  benchmarking using recorded constituent snapshots.

Changes:

- Added `src/investing/scoring_profiles.py` with `non_bank`, `bank`, and `nbfc` metric
  thresholds.
- Updated `LongTermScorer` to score rows by `entity_type` when present.
- Extended `FundamentalSnapshot.to_scorer_row()` with industry-specific metric mappings.
- Added `src/investing/constituents.py` with `ConstituentHistoryStore` and
  `resolve_portfolio_symbols`.
- Extended walk-forward evaluation to resolve portfolio membership per as-of date.
- Added `universe --persist` and walk-forward `--historical-constituents`.
- Added `tests/test_scoring_profiles.py` and `tests/test_constituents.py`.

Decisions:

- Bank prudential ratios remain percentage points in scorer inputs to match NSE XBRL
  reporting conventions.
- Historical constituent snapshots are stored in the research SQLite database and selected
  with latest-on-or-before semantics per as-of date.
- When no historical snapshot exists, portfolio benchmarking falls back to current Nifty
  membership.

### 2026-09-28 — Insurance fundamental ratios and scorer integration

Goal:

- Calculate insurer-specific fundamentals from validated XBRL canonical facts and score
  them with an insurance industry profile.

Changes:

- Extended `FundamentalCalculator` with insurance premium-base detection, premium CAGR,
  ROA, profit margin on premiums, investment income ratio, and equity to assets.
- Added `INSURANCE_METRICS` to `scoring_profiles.py` and insurance mappings in
  `FundamentalSnapshot.to_scorer_row()`.
- Persisted insurance ratios in `research_snapshots` (store version 4).
- Bumped `CALCULATION_VERSION` to 2.
- Expanded insurance and scoring profile tests.

Decisions:

- Life versus general premium metrics follow the same concept overlap rule as taxonomy
  validation and canonical mapping.
- Premium growth is stored in `revenue_cagr_3y` so walk-forward and explanation flows
  remain entity-agnostic.

### 2026-09-28 — Constituent import and universe calibration

Goal:

- Expand historical constituent coverage beyond single-date `universe --persist` and
  analyze persisted Nifty universe backtests to review industry threshold settings.

Changes:

- Added CSV import and as-of coverage reporting in `constituents.py`.
- Added `src/investing/calibration.py` with score bucket reports and quantile-based
  threshold suggestions by `entity_type`.
- Added `constituents` CLI (`list`, `import`, `coverage`) and `calibrate` CLI command.
- Added `tests/test_calibration.py` and expanded constituent tests.

Decisions:

- Calibration is read-only and never mutates `scoring_profiles.py` automatically.
- Threshold suggestions use cross-sectional quantiles from persisted snapshots; score
  bucket reports group by `research_view`.
- Constituent CSV import uses long format (`effective_date`, `symbol`) for auditable
  historical membership expansion.

### 2026-09-28 — Scheduled constituent archival and versioned scoring profiles

Goal:

- Automate recurring Nifty constituent archival and apply reviewed calibration output as
  explicit, activatable scoring profile versions.

Changes:

- Added `constituents archive` for fiscal quarter-end membership recording with skip-if-exists
  semantics suitable for cron jobs.
- Added `src/investing/profile_store.py` with `ScoringProfileStore` for versioned thresholds.
- Added `profiles` CLI (`list`, `apply`, `activate`) and `build_profile_version` calibration
  merge helper.
- Extended `LongTermScorer` with optional `profile_store` / `profile_version` resolution.
- Added walk-forward `--profile-version` and `--use-active-profile` flags.
- Added `tests/test_profile_store.py` and expanded constituent archive tests.

Decisions:

- Built-in thresholds remain baseline version 1; persisted profile versions start at 2+.
- Profile application requires an explicit version number and optional `--activate` step.
- Metrics with insufficient sample size keep their current thresholds during profile apply.

Remaining work:

- None for this milestone; see **Next milestones** below.

### 2026-09-28 — Universe orchestration and profile review dashboard

Goal:

- Automate full Nifty universe walk-forward research runs and surface profile calibration
  review in the research dashboard.

Changes:

- Added `src/investing/orchestration.py` with `UniverseResearchOrchestrator`,
  `OrchestrationStore`, and `resolve_orchestration_dates`.
- Added `orchestrate` CLI for quarter-range or explicit as-of date universe runs with optional
  constituent archival, persistence, explanations, and active profile resolution.
- Extended `dashboard.py` with **Profile review** and **Orchestration runs** tabs.
- Extended `dashboard_data.py` with `calibration_report`, `profile_versions`, and
  `orchestration_runs`.
- Added `tests/test_orchestration.py` and expanded `tests/test_dashboard.py`.

Decisions:

- Orchestration skips symbols without fundamentals rather than failing the whole run.
- Run summaries persist to `research_orchestration_runs` for cron-friendly audit trails.
- Profile review in the dashboard is read-only; activation still uses the `profiles` CLI.

Verification:

- `python -m pytest tests -q`: **76 passed**.

Remaining work:

- Add optional run notifications when orchestration completes with skipped symbols.

### 2026-09-28 — Research scheduling recipes

Goal:

- Document and automate recurring constituent archival plus quarterly universe orchestration
  for cron and Windows Task Scheduler.

Changes:

- Added `src/investing/scheduling.py` with rolling quarter windows, env-based schedule
  configuration, and `run_quarterly_research`.
- Added `schedule show` and `schedule run-quarterly` CLI commands.
- Added `scripts/india-research-quarterly.ps1`, `scripts/india-research-quarterly.sh`, and
  `scripts/india-research-quarterly.env.example`.
- Added `docs/india_research_scheduling.md`.
- Added `tests/test_scheduling.py`.

Decisions:

- Wrapper scripts delegate to the CLI so scheduling logic stays testable in Python.
- `schedule run-quarterly` archives constituents before orchestration but does not pass
  `--archive-constituents` to orchestrate to avoid duplicate archive attempts.
- Generated cron examples use calendar-quarter triggers; operators should adjust for IST and
  data availability.

Verification:

- `python -m pytest tests -q`: **81 passed**.

### 2026-09-28 — Historical constituent expansion

Goal:

- Expand point-in-time Nifty membership coverage beyond single-date archives and manual
  long-format CSV imports.

Changes:

- Added `src/investing/constituent_expansion.py` for membership intervals, wide snapshot
  matrices, reconstitution change replay, and NSE workbook normalization.
- Added `constituents import-intervals`, `import-wide`, `backfill`, and `fetch-changes`
  CLI commands.
- Added example interval, wide, and change CSV files under `examples/`.
- Added `tests/test_constituent_expansion.py`.

Decisions:

- Membership intervals use half-open `[valid_from, valid_to)` semantics.
- Change backfill replays official add/remove events backward from a current or stored anchor.
- NSE workbook parsing is best-effort; local `--input` fallback is supported when `.xls`
  engines are unavailable.

Verification:

- `python -m pytest tests -q`: **87 passed**.

### 2026-09-28 — Orchestration notifications

Goal:

- Alert operators when scheduled universe orchestration skips symbols without failing the
  full run.

Changes:

- Added `src/investing/orchestration_notifications.py` with webhook, file, and SMTP email
  delivery.
- Added `--notify`, `--notify-webhook`, `--notify-output`, and `--notify-email-to` flags to
  `orchestrate` and `schedule run-quarterly`.
- Documented notification environment variables in `scripts/india-research-quarterly.env.example`
  and `docs/india_research_scheduling.md`.
- Added `tests/test_orchestration_notifications.py`.

Decisions:

- Default notification mode is `never` until a delivery channel is configured; configuring a
  channel defaults to `skipped`.
- Notifications are best-effort and do not change orchestration persistence behavior.

Verification:

- `python -m pytest tests -q`: **92 passed**.

## Next milestones

1. Review persisted orchestration calibration output in the dashboard profile tab after each
   scheduled run.

### 2026-09-28 — Profile store and archive verification

- `python -m pytest tests -q`: **72 passed**.
- Constituent archive idempotency, profile save/activate, and scorer profile resolution
  covered by new tests.

### 2026-09-28 — Constituent and calibration verification

- `python -m pytest tests -q`: **68 passed**.
- Constituent CSV import, coverage reporting, score bucket analysis, and threshold
  suggestions covered by new tests.

### 2026-09-28 — Insurance scoring verification

- `python -m pytest tests -q`: insurance calculator, scorer profile, and persistence
  covered by expanded tests.

### 2026-09-28 — Industry scoring and constituent verification

- `python -m pytest tests -q`: **60 passed**.
- Industry profile selection, bank scoring thresholds, constituent snapshot lookup, and
  per-as-of portfolio resolution covered by new tests.

## Known limitations

- Threshold suggestions are advisory until manually reviewed and versioned in
  `scoring_profiles.py`.
- Portfolio benchmarking falls back to current Nifty membership when no historical constituent
  snapshot exists for an as-of date.
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
