"""Command-line entry points for the India long-term research MVP."""

from __future__ import annotations

import argparse
from datetime import date, datetime, time
from pathlib import Path
import sys

import pandas as pd

from .filings import FilingStore, IST, NseFinancialResultsClient
from .explanations import ScoreExplainer, explanations_to_frame
from .fundamentals import FundamentalCalculator, FundamentalSnapshot
from .insurance import InsuranceTaxonomyValidator
from .market import MarketJoinError, MarketMetricsJoiner, snapshots_to_scorer_frame
from .providers import (
    DataProviderError,
    NiftyIndexUniverseProvider,
    YFinancePriceProvider,
    nifty_benchmark_symbol,
)
from .research import (
    ResearchStore,
    WalkForwardEvaluator,
    _snapshot_key,
    fiscal_quarter_end_dates,
    records_to_frame,
    walkforward_report,
)
from .scoring import LongTermScorer
from .xbrl import NseXbrlClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Research Indian equities without placing trades."
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    universe = subcommands.add_parser(
        "universe", help="Download current Nifty constituents"
    )
    universe.add_argument(
        "--index", default="NIFTY 50", choices=["NIFTY 50", "NIFTY 100", "NIFTY 200"]
    )
    universe.add_argument("--output", type=Path)

    prices = subcommands.add_parser("prices", help="Download historical daily prices")
    prices.add_argument(
        "symbols", nargs="+", help="NSE symbols such as RELIANCE and INFY"
    )
    prices.add_argument("--start", required=True)
    prices.add_argument("--end", required=True)
    prices.add_argument("--output", type=Path, required=True)

    score = subcommands.add_parser("score", help="Rank a normalized fundamentals CSV")
    score.add_argument("input", type=Path)
    score.add_argument("--output", type=Path)

    filings = subcommands.add_parser(
        "filings", help="Import NSE financial-result filing metadata"
    )
    filings.add_argument("symbol", help="NSE symbol such as INFY")
    filings.add_argument(
        "--period", default="Quarterly", choices=["Quarterly", "Annual"]
    )
    filings.add_argument("--database", type=Path, default=Path("work/research.db"))
    filings.add_argument(
        "--download-xbrl",
        action="store_true",
        help="Archive and parse linked NSE XBRL documents not already stored",
    )
    filings.add_argument(
        "--normalize-xbrl",
        action="store_true",
        help="Refresh canonical statement mappings for archived XBRL facts",
    )
    filings.add_argument(
        "--validate-insurance",
        action="store_true",
        help="Validate archived insurance XBRL concepts without canonical mapping",
    )

    fundamentals = subcommands.add_parser(
        "fundamentals", help="Calculate point-in-time fundamentals from archived XBRL"
    )
    fundamentals.add_argument("symbols", nargs="+", help="NSE symbols such as INFY")
    fundamentals.add_argument(
        "--as-of", required=True, help="ISO date or timezone-aware datetime cutoff"
    )
    fundamentals.add_argument("--database", type=Path, default=Path("work/research.db"))
    fundamentals.add_argument(
        "--prices",
        type=Path,
        help="CSV of historical daily prices to join for valuation metrics",
    )
    fundamentals.add_argument(
        "--fetch-prices",
        action="store_true",
        help="Download prices for the requested symbols before joining market metrics",
    )
    fundamentals.add_argument(
        "--prices-start",
        help="Start date for --fetch-prices (required with --fetch-prices)",
    )
    fundamentals.add_argument(
        "--prices-end",
        help="End date for --fetch-prices (required with --fetch-prices)",
    )
    fundamentals.add_argument(
        "--score",
        action="store_true",
        help="Score the enriched snapshots with LongTermScorer",
    )
    fundamentals.add_argument(
        "--persist",
        action="store_true",
        help="Save scored research snapshots to the research database",
    )
    fundamentals.add_argument(
        "--benchmark-index",
        default="NIFTY 50",
        choices=["NIFTY 50", "NIFTY 100", "NIFTY 200"],
    )
    fundamentals.add_argument(
        "--forward-days",
        type=int,
        default=365,
        help="Forward return horizon used for benchmark comparison",
    )
    fundamentals.add_argument(
        "--explain",
        action="store_true",
        help="Include deterministic score explanations when persisting research",
    )
    fundamentals.add_argument("--output", type=Path)

    walkforward = subcommands.add_parser(
        "walkforward",
        help="Run point-in-time research across multiple as-of dates",
    )
    walkforward.add_argument("symbols", nargs="+", help="NSE symbols such as INFY")
    walkforward.add_argument(
        "--as-of-dates",
        nargs="+",
        help="ISO dates or datetimes to evaluate",
    )
    walkforward.add_argument(
        "--quarter-range-start",
        help="Generate fiscal quarter-end as-of dates starting here (ISO date)",
    )
    walkforward.add_argument(
        "--quarter-range-end",
        help="Generate fiscal quarter-end as-of dates ending here (ISO date)",
    )
    walkforward.add_argument(
        "--cadence",
        default="annual",
        choices=["annual", "quarterly"],
        help="Label persisted snapshots; use with quarter range for quarterly history",
    )
    walkforward.add_argument("--database", type=Path, default=Path("work/research.db"))
    walkforward.add_argument(
        "--prices",
        type=Path,
        help="CSV of historical daily prices including benchmark index prices",
    )
    walkforward.add_argument(
        "--fetch-prices",
        action="store_true",
        help="Download prices for the requested symbols and benchmark index",
    )
    walkforward.add_argument(
        "--prices-start",
        help="Start date for --fetch-prices (required with --fetch-prices)",
    )
    walkforward.add_argument(
        "--prices-end",
        help="End date for --fetch-prices (required with --fetch-prices)",
    )
    walkforward.add_argument(
        "--benchmark-index",
        default="NIFTY 50",
        choices=["NIFTY 50", "NIFTY 100", "NIFTY 200"],
    )
    walkforward.add_argument(
        "--forward-days",
        type=int,
        default=365,
        help="Forward return horizon used for benchmark comparison",
    )
    walkforward.add_argument(
        "--benchmark-portfolio",
        action="store_true",
        help="Compare forward returns with an equal-weight Nifty constituent portfolio",
    )
    walkforward.add_argument(
        "--persist",
        action="store_true",
        help="Save walk-forward snapshots to the research database",
    )
    walkforward.add_argument(
        "--summary",
        action="store_true",
        help="Print a compact benchmark comparison report",
    )
    walkforward.add_argument(
        "--explain",
        action="store_true",
        help="Attach deterministic score explanations grounded in source filings",
    )
    walkforward.add_argument("--output", type=Path)

    explain = subcommands.add_parser(
        "explain",
        help="Explain a research score using saved source filing metadata",
    )
    explain.add_argument("symbol", help="NSE symbol such as INFY")
    explain.add_argument(
        "--as-of", required=True, help="ISO date or timezone-aware datetime cutoff"
    )
    explain.add_argument("--database", type=Path, default=Path("work/research.db"))
    explain.add_argument(
        "--from-store",
        action="store_true",
        help="Explain a persisted research snapshot instead of recomputing",
    )
    explain.add_argument(
        "--persist",
        action="store_true",
        help="Save the explanation to the research database",
    )
    explain.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "universe":
            data = NiftyIndexUniverseProvider(args.index).fetch()
        elif args.command == "prices":
            data = YFinancePriceProvider().fetch(args.symbols, args.start, args.end)
        elif args.command == "score":
            data = LongTermScorer().score(pd.read_csv(args.input))
        elif args.command == "filings":
            records = NseFinancialResultsClient().fetch(args.symbol, args.period)
            store = FilingStore(args.database)
            inserted = store.ingest(
                records, request_symbol=args.symbol, request_period=args.period
            )
            parsed_documents = 0
            parsed_facts = 0
            normalized_facts = 0
            if args.download_xbrl:
                client = NseXbrlClient()
                pending = store.pending_xbrl(symbol=args.symbol, period=args.period)
                for filing in pending:
                    download = client.fetch(filing["xbrl_url"])
                    parsed_facts += store.ingest_xbrl(filing["filing_key"], download)
                    parsed_documents += 1
            if args.normalize_xbrl:
                normalized_facts = store.normalize_xbrl(
                    symbol=args.symbol, period=args.period
                )
            counts = store.counts()
            print(
                f"Fetched {len(records)} records; inserted {inserted} new filings into "
                f"{args.database}. Total normalized filings: "
                f"{counts['normalized_filings']}"
            )
            if args.download_xbrl:
                xbrl_counts = store.xbrl_counts()
                print(
                    f"Archived {parsed_documents} XBRL documents and parsed "
                    f"{parsed_facts} facts. Total linked documents: "
                    f"{xbrl_counts['linked_filings']}; total facts: "
                    f"{xbrl_counts['facts']}"
                )
            if args.download_xbrl or args.normalize_xbrl:
                canonical_counts = store.canonical_counts()
                refresh_message = (
                    f"Canonical mappings refreshed: {normalized_facts}. "
                    if args.normalize_xbrl
                    else ""
                )
                print(
                    refresh_message
                    + f"Total canonical facts: {canonical_counts['canonical_facts']}; "
                    f"primary statement facts: {canonical_counts['primary_facts']}"
                )
            if args.validate_insurance:
                reports = InsuranceTaxonomyValidator().validate_symbol(
                    store, args.symbol
                )
                data = pd.DataFrame([report.to_record() for report in reports])
                if getattr(args, "output", None):
                    args.output.parent.mkdir(parents=True, exist_ok=True)
                    data.to_csv(args.output, index=False)
                    print(f"Saved {len(data)} rows to {args.output}")
                else:
                    print(data.to_string(index=False))
                return 0
            return 0
        elif args.command == "walkforward":
            as_of_dates = _resolve_as_of_dates(args)
            portfolio_symbols = _resolve_portfolio_symbols(args)
            prices = _load_walkforward_prices(args, portfolio_symbols)
            evaluator = WalkForwardEvaluator(filing_store=FilingStore(args.database))
            records = evaluator.evaluate(
                args.symbols,
                as_of_dates,
                prices,
                benchmark_index=args.benchmark_index,
                forward_days=args.forward_days,
                snapshot_cadence=args.cadence,
                portfolio_symbols=portfolio_symbols,
            )
            if args.persist:
                research_store = ResearchStore(args.database)
                inserted = research_store.save_records(records)
                counts = research_store.counts()
                print(
                    f"Persisted {inserted} research snapshots. "
                    f"Total evaluations: {counts['evaluations']}; "
                    f"total snapshots: {counts['snapshots']}"
                )
                if args.explain:
                    explained = _persist_explanations(
                        records, FilingStore(args.database), research_store
                    )
                    print(f"Persisted {explained} score explanations.")
            if args.explain and not args.persist:
                data = explanations_to_frame(
                    _explain_records(records, FilingStore(args.database))
                )
            else:
                data = (
                    walkforward_report(records)
                    if args.summary
                    else records_to_frame(records)
                )
        elif args.command == "explain":
            as_of = _parse_as_of(args.as_of)
            filing_store = FilingStore(args.database)
            research_store = ResearchStore(args.database)
            if args.from_store:
                snapshots = research_store.list_snapshots(
                    symbol=args.symbol, as_of=as_of.isoformat()
                )
                if snapshots.empty:
                    raise ValueError(
                        f"No persisted research snapshot exists for {args.symbol} "
                        f"as of {as_of.date().isoformat()}"
                    )
                row = snapshots.iloc[0]
                snapshot = FundamentalSnapshot.from_record(row)
                explanation = ScoreExplainer().explain_snapshot(
                    snapshot,
                    overall_score=_optional_float(row.get("overall_score")),
                    research_view=_optional_text(row.get("research_view")),
                    data_coverage=_optional_float(row.get("data_coverage")),
                    filing_store=filing_store,
                )
                explanations = [explanation]
            else:
                raise ValueError(
                    "Fresh explanation requires a persisted snapshot; run fundamentals "
                    "or walkforward with --persist first, then explain --from-store"
                )
            if args.persist:
                snapshot_key = str(snapshots.iloc[0]["snapshot_key"])
                evaluation_key = str(snapshots.iloc[0]["evaluation_key"])
                research_store.save_explanations(
                    [
                        (
                            snapshot_key,
                            evaluation_key,
                            explanations[0].to_record(),
                        )
                    ]
                )
            data = explanations_to_frame(explanations)
        else:
            as_of = _parse_as_of(args.as_of)
            if args.persist:
                if not (args.fetch_prices or args.prices):
                    raise ValueError(
                        "--persist requires market prices via --prices or --fetch-prices"
                    )
                prices = _load_fundamentals_prices(args)
                evaluator = WalkForwardEvaluator(filing_store=FilingStore(args.database))
                records = evaluator.evaluate(
                    args.symbols,
                    [as_of],
                    prices,
                    benchmark_index=args.benchmark_index,
                    forward_days=args.forward_days,
                )
                research_store = ResearchStore(args.database)
                inserted = research_store.save_records(records)
                counts = research_store.counts()
                print(
                    f"Persisted {inserted} research snapshots. "
                    f"Total evaluations: {counts['evaluations']}; "
                    f"total snapshots: {counts['snapshots']}"
                )
                if args.explain:
                    explained = _persist_explanations(
                        records, FilingStore(args.database), research_store
                    )
                    print(f"Persisted {explained} score explanations.")
                    data = explanations_to_frame(
                        _explain_records(records, FilingStore(args.database))
                    )
                else:
                    data = records_to_frame(records)
            else:
                store = FilingStore(args.database)
                calculator = FundamentalCalculator()
                snapshots = [
                    calculator.calculate(
                        store.canonical_observations_as_of(symbol, as_of),
                        symbol=symbol,
                        as_of=as_of,
                    )
                    for symbol in args.symbols
                ]
                if args.fetch_prices or args.prices:
                    prices = _load_fundamentals_prices(args)
                    joiner = MarketMetricsJoiner()
                    snapshots = [
                        joiner.join(snapshot, prices) for snapshot in snapshots
                    ]
                if args.score:
                    data = LongTermScorer().score(snapshots_to_scorer_frame(snapshots))
                else:
                    data = pd.DataFrame(
                        [snapshot.to_record() for snapshot in snapshots]
                    )
    except (
        DataProviderError,
        MarketJoinError,
        OSError,
        ValueError,
        pd.errors.ParserError,
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    if getattr(args, "output", None):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        data.to_csv(args.output, index=False)
        print(f"Saved {len(data)} rows to {args.output}")
    else:
        print(data.to_string(index=False))
    return 0


def _load_fundamentals_prices(args: argparse.Namespace) -> pd.DataFrame:
    if args.fetch_prices:
        if not args.prices_start or not args.prices_end:
            raise ValueError(
                "--fetch-prices requires both --prices-start and --prices-end"
            )
        return YFinancePriceProvider().fetch(
            args.symbols, args.prices_start, args.prices_end
        )
    if args.prices:
        return pd.read_csv(args.prices)
    raise ValueError("Provide --prices or --fetch-prices to join market metrics")


def _resolve_as_of_dates(args: argparse.Namespace) -> list[datetime]:
    if args.quarter_range_start and args.quarter_range_end:
        return fiscal_quarter_end_dates(
            date.fromisoformat(args.quarter_range_start),
            date.fromisoformat(args.quarter_range_end),
        )
    if args.as_of_dates:
        return [_parse_as_of(value) for value in args.as_of_dates]
    raise ValueError(
        "Provide --as-of-dates or both --quarter-range-start and --quarter-range-end"
    )


def _resolve_portfolio_symbols(args: argparse.Namespace) -> list[str] | None:
    if not getattr(args, "benchmark_portfolio", False):
        return None
    return NiftyIndexUniverseProvider(args.benchmark_index).symbols()


def _load_walkforward_prices(
    args: argparse.Namespace, portfolio_symbols: list[str] | None
) -> pd.DataFrame:
    if args.fetch_prices:
        if not args.prices_start or not args.prices_end:
            raise ValueError(
                "--fetch-prices requires both --prices-start and --prices-end"
            )
        symbols = list(
            dict.fromkeys(
                [
                    *args.symbols,
                    nifty_benchmark_symbol(args.benchmark_index),
                    *(portfolio_symbols or []),
                ]
            )
        )
        return YFinancePriceProvider().fetch(
            symbols, args.prices_start, args.prices_end
        )
    if args.prices:
        return pd.read_csv(args.prices)
    raise ValueError("Provide --prices or --fetch-prices for walk-forward research")


def _explain_records(records, filing_store: FilingStore):
    explainer = ScoreExplainer()
    return [explainer.explain_record(record, filing_store) for record in records]


def _persist_explanations(records, filing_store: FilingStore, research_store: ResearchStore) -> int:
    explanations = _explain_records(records, filing_store)
    items = [
        (
            _snapshot_key(record.evaluation_key, record.snapshot.symbol),
            record.evaluation_key,
            explanation.to_record(),
        )
        for record, explanation in zip(records, explanations)
    ]
    return research_store.save_explanations(items)


def _optional_float(value) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _optional_text(value) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def _parse_as_of(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("as-of must be an ISO date or datetime") from exc
    if "T" not in value and " " not in value:
        parsed = datetime.combine(parsed.date(), time.max)
    return parsed.replace(tzinfo=IST) if parsed.tzinfo is None else parsed


if __name__ == "__main__":
    raise SystemExit(main())
