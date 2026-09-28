"""Command-line entry points for the India long-term research MVP."""

from __future__ import annotations

import argparse
from datetime import datetime, time
from pathlib import Path
import sys

import pandas as pd

from .filings import FilingStore, IST, NseFinancialResultsClient
from .fundamentals import FundamentalCalculator
from .providers import (
    DataProviderError,
    NiftyIndexUniverseProvider,
    YFinancePriceProvider,
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

    fundamentals = subcommands.add_parser(
        "fundamentals", help="Calculate point-in-time fundamentals from archived XBRL"
    )
    fundamentals.add_argument("symbols", nargs="+", help="NSE symbols such as INFY")
    fundamentals.add_argument(
        "--as-of", required=True, help="ISO date or timezone-aware datetime cutoff"
    )
    fundamentals.add_argument("--database", type=Path, default=Path("work/research.db"))
    fundamentals.add_argument("--output", type=Path)
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
            return 0
        else:
            as_of = _parse_as_of(args.as_of)
            store = FilingStore(args.database)
            calculator = FundamentalCalculator()
            data = pd.DataFrame(
                [
                    calculator.calculate(
                        store.canonical_observations_as_of(symbol, as_of),
                        symbol=symbol,
                        as_of=as_of,
                    ).to_record()
                    for symbol in args.symbols
                ]
            )
    except (DataProviderError, OSError, ValueError, pd.errors.ParserError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    if getattr(args, "output", None):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        data.to_csv(args.output, index=False)
        print(f"Saved {len(data)} rows to {args.output}")
    else:
        print(data.to_string(index=False))
    return 0


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
