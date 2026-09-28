"""Command-line entry points for the India long-term research MVP."""

from __future__ import annotations

import argparse
from datetime import date, datetime, time
from pathlib import Path
import sys

import pandas as pd

from .calibration import analyze_universe_backtest, build_profile_version
from .constituent_expansion import (
    backfill_quarter_snapshots_from_changes,
    backfill_quarter_snapshots_from_intervals,
    download_nse_index_changes_csv,
    export_nse_changes_csv,
    import_wide_snapshots_csv,
    load_membership_intervals_csv,
    load_reconstitution_changes_csv,
)
from .constituents import (
    SUPPORTED_INDICES,
    ConstituentHistoryStore,
    archive_current_constituents,
    constituent_coverage,
    import_snapshots_csv,
    latest_fiscal_quarter_end,
)
from .orchestration import UniverseResearchOrchestrator, resolve_orchestration_dates
from .profile_store import ScoringProfileStore
from .scheduling import (
    QuarterlyResearchSchedule,
    quarterly_schedule_from_env,
    render_schedule_recipes,
    run_quarterly_research,
)
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
    universe.add_argument("--database", type=Path, default=Path("work/research.db"))
    universe.add_argument(
        "--persist",
        action="store_true",
        help="Record the downloaded constituent list for historical benchmarking",
    )
    universe.add_argument(
        "--effective-date",
        help="Membership effective date for --persist (ISO date, default today)",
    )

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
        "--historical-constituents",
        action="store_true",
        help="Use recorded Nifty constituent snapshots on or before each as-of date",
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
    walkforward.add_argument(
        "--profile-version",
        type=int,
        help="Score with a saved scoring profile version from the research database",
    )
    walkforward.add_argument(
        "--use-active-profile",
        action="store_true",
        help="Score with the activated scoring profile version",
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

    dashboard = subcommands.add_parser(
        "dashboard",
        help="Launch the Streamlit research dashboard for persisted snapshots",
    )
    dashboard.add_argument("--database", type=Path, default=Path("work/research.db"))
    dashboard.add_argument("--port", type=int, default=8501)

    constituents = subcommands.add_parser(
        "constituents",
        help="Manage historical Nifty constituent snapshots",
    )
    constituents_sub = constituents.add_subparsers(
        dest="constituents_command", required=True
    )
    constituents_list = constituents_sub.add_parser(
        "list", help="List recorded constituent snapshots"
    )
    constituents_list.add_argument("--database", type=Path, default=Path("work/research.db"))
    constituents_list.add_argument("--index")
    constituents_list.add_argument("--output", type=Path)

    constituents_import = constituents_sub.add_parser(
        "import", help="Import constituent snapshots from CSV"
    )
    constituents_import.add_argument("input", type=Path)
    constituents_import.add_argument(
        "--index", required=True, choices=["NIFTY 50", "NIFTY 100", "NIFTY 200"]
    )
    constituents_import.add_argument("--database", type=Path, default=Path("work/research.db"))
    constituents_import.add_argument(
        "--source", default="csv_import", help="Lineage label stored with each snapshot"
    )

    constituents_coverage = constituents_sub.add_parser(
        "coverage", help="Check constituent snapshot coverage for as-of dates"
    )
    constituents_coverage.add_argument(
        "--index", required=True, choices=["NIFTY 50", "NIFTY 100", "NIFTY 200"]
    )
    constituents_coverage.add_argument(
        "--dates", nargs="+", required=True, help="ISO as-of dates to check"
    )
    constituents_coverage.add_argument("--database", type=Path, default=Path("work/research.db"))
    constituents_coverage.add_argument("--output", type=Path)

    constituents_archive = constituents_sub.add_parser(
        "archive",
        help="Record current official Nifty constituents for the latest fiscal quarter-end",
    )
    constituents_archive.add_argument("--database", type=Path, default=Path("work/research.db"))
    constituents_archive.add_argument(
        "--index",
        default="NIFTY 50",
        choices=["NIFTY 50", "NIFTY 100", "NIFTY 200"],
    )
    constituents_archive.add_argument(
        "--all-indices",
        action="store_true",
        help="Archive NIFTY 50, NIFTY 100, and NIFTY 200 in one run",
    )
    constituents_archive.add_argument(
        "--effective-date",
        help="Membership effective date (ISO date, default latest fiscal quarter-end)",
    )
    constituents_archive.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing snapshot for the effective date",
    )

    constituents_import_intervals = constituents_sub.add_parser(
        "import-intervals",
        help="Import membership intervals and optionally backfill quarter-end snapshots",
    )
    constituents_import_intervals.add_argument("input", type=Path)
    constituents_import_intervals.add_argument(
        "--index", required=True, choices=["NIFTY 50", "NIFTY 100", "NIFTY 200"]
    )
    constituents_import_intervals.add_argument(
        "--database", type=Path, default=Path("work/research.db")
    )
    constituents_import_intervals.add_argument("--quarter-range-start")
    constituents_import_intervals.add_argument("--quarter-range-end")
    constituents_import_intervals.add_argument(
        "--force",
        action="store_true",
        help="Replace existing quarter-end snapshots during backfill",
    )

    constituents_import_wide = constituents_sub.add_parser(
        "import-wide",
        help="Import wide membership snapshots with one column per effective date",
    )
    constituents_import_wide.add_argument("input", type=Path)
    constituents_import_wide.add_argument(
        "--index", required=True, choices=["NIFTY 50", "NIFTY 100", "NIFTY 200"]
    )
    constituents_import_wide.add_argument("--database", type=Path, default=Path("work/research.db"))
    constituents_import_wide.add_argument(
        "--source", default="wide_csv_import", help="Lineage label stored with each snapshot"
    )
    constituents_import_wide.add_argument(
        "--force",
        action="store_true",
        help="Replace existing snapshots for imported effective dates",
    )

    constituents_backfill = constituents_sub.add_parser(
        "backfill",
        help="Backfill fiscal quarter-end snapshots from reconstitution changes",
    )
    constituents_backfill.add_argument(
        "--changes",
        type=Path,
        required=True,
        help="CSV of effective_date,symbol,action change events",
    )
    constituents_backfill.add_argument(
        "--index", required=True, choices=["NIFTY 50", "NIFTY 100", "NIFTY 200"]
    )
    constituents_backfill.add_argument("--database", type=Path, default=Path("work/research.db"))
    constituents_backfill.add_argument("--quarter-range-start", required=True)
    constituents_backfill.add_argument("--quarter-range-end", required=True)
    constituents_backfill.add_argument(
        "--anchor",
        choices=["current", "store"],
        default="current",
        help="Membership anchor used to replay historical changes",
    )
    constituents_backfill.add_argument(
        "--anchor-date",
        help="Anchor date for store replay (ISO date, default latest fiscal quarter-end)",
    )
    constituents_backfill.add_argument(
        "--force",
        action="store_true",
        help="Replace existing quarter-end snapshots during backfill",
    )

    constituents_fetch_changes = constituents_sub.add_parser(
        "fetch-changes",
        help="Download and normalize the official NSE inclusion/exclusion workbook",
    )
    constituents_fetch_changes.add_argument(
        "--index", required=True, choices=["NIFTY 50", "NIFTY 100", "NIFTY 200"]
    )
    constituents_fetch_changes.add_argument("output", type=Path)
    constituents_fetch_changes.add_argument(
        "--input",
        type=Path,
        help="Use a locally downloaded IndexInclExcl workbook instead of fetching from NSE",
    )
    constituents_fetch_changes.add_argument(
        "--sheet",
        help="Workbook sheet name override (default uses the index name)",
    )

    profiles = subcommands.add_parser(
        "profiles",
        help="Manage versioned scoring profile thresholds",
    )
    profiles_sub = profiles.add_subparsers(dest="profiles_command", required=True)
    profiles_list = profiles_sub.add_parser("list", help="List saved scoring profile versions")
    profiles_list.add_argument("--database", type=Path, default=Path("work/research.db"))
    profiles_list.add_argument("--output", type=Path)

    profiles_apply = profiles_sub.add_parser(
        "apply",
        help="Save a reviewed calibration as a new scoring profile version",
    )
    profiles_apply.add_argument(
        "--version", type=int, required=True, help="New profile version number"
    )
    profiles_apply.add_argument("--database", type=Path, default=Path("work/research.db"))
    profiles_apply.add_argument(
        "--input",
        type=Path,
        help="Reviewed threshold CSV from calibrate --report thresholds",
    )
    profiles_apply.add_argument(
        "--from-calibration",
        action="store_true",
        help="Build the profile from persisted research snapshots",
    )
    profiles_apply.add_argument(
        "--min-sample-size",
        type=int,
        default=5,
        help="Minimum observations required before replacing a metric threshold",
    )
    profiles_apply.add_argument(
        "--low-quantile", type=float, default=0.25, help="Lower quantile for calibration"
    )
    profiles_apply.add_argument(
        "--high-quantile", type=float, default=0.75, help="Upper quantile for calibration"
    )
    profiles_apply.add_argument(
        "--activate",
        action="store_true",
        help="Activate the new profile version after saving it",
    )

    profiles_activate = profiles_sub.add_parser(
        "activate", help="Activate a saved scoring profile version"
    )
    profiles_activate.add_argument("--version", type=int, required=True)
    profiles_activate.add_argument("--database", type=Path, default=Path("work/research.db"))

    calibrate = subcommands.add_parser(
        "calibrate",
        help="Analyze persisted universe backtests and suggest metric thresholds",
    )
    calibrate.add_argument("--database", type=Path, default=Path("work/research.db"))
    calibrate.add_argument(
        "--low-quantile", type=float, default=0.25, help="Lower quantile for suggestions"
    )
    calibrate.add_argument(
        "--high-quantile", type=float, default=0.75, help="Upper quantile for suggestions"
    )
    calibrate.add_argument(
        "--report",
        choices=["all", "buckets", "thresholds"],
        default="all",
        help="Which calibration tables to print",
    )
    calibrate.add_argument("--output", type=Path)

    orchestrate = subcommands.add_parser(
        "orchestrate",
        help="Run scheduled Nifty universe walk-forward research",
    )
    orchestrate.add_argument(
        "--index", default="NIFTY 50", choices=["NIFTY 50", "NIFTY 100", "NIFTY 200"]
    )
    orchestrate.add_argument("--database", type=Path, default=Path("work/research.db"))
    orchestrate.add_argument("--as-of-dates", nargs="+")
    orchestrate.add_argument("--quarter-range-start")
    orchestrate.add_argument("--quarter-range-end")
    orchestrate.add_argument("--prices-start", required=True)
    orchestrate.add_argument("--prices-end", required=True)
    orchestrate.add_argument(
        "--benchmark-index",
        default="NIFTY 50",
        choices=["NIFTY 50", "NIFTY 100", "NIFTY 200"],
    )
    orchestrate.add_argument("--forward-days", type=int, default=365)
    orchestrate.add_argument(
        "--cadence",
        default="quarterly",
        choices=["annual", "quarterly"],
    )
    orchestrate.add_argument(
        "--archive-constituents",
        action="store_true",
        help="Archive current Nifty membership before evaluation",
    )
    orchestrate.add_argument(
        "--historical-constituents",
        action="store_true",
        help="Use recorded constituent snapshots for portfolio benchmarking",
    )
    orchestrate.add_argument(
        "--benchmark-portfolio",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    orchestrate.add_argument("--persist", action="store_true", default=True)
    orchestrate.add_argument("--no-persist", action="store_false", dest="persist")
    orchestrate.add_argument("--explain", action="store_true")
    orchestrate.add_argument("--profile-version", type=int)
    orchestrate.add_argument("--use-active-profile", action="store_true")
    orchestrate.add_argument(
        "--max-symbols",
        type=int,
        help="Limit universe size for testing or partial runs",
    )

    schedule = subcommands.add_parser(
        "schedule",
        help="Recurring archive and orchestration schedule helpers",
    )
    schedule_sub = schedule.add_subparsers(dest="schedule_command", required=True)
    schedule_show = schedule_sub.add_parser(
        "show",
        help="Print cron and Task Scheduler recipes",
    )
    schedule_run = schedule_sub.add_parser(
        "run-quarterly",
        help="Archive constituents and run rolling quarterly orchestration",
    )
    for parser in (schedule_show, schedule_run):
        parser.add_argument("--database", type=Path, default=Path("work/research.db"))
        parser.add_argument(
            "--index",
            default="NIFTY 50",
            choices=["NIFTY 50", "NIFTY 100", "NIFTY 200"],
        )
        parser.add_argument(
            "--benchmark-index",
            default="NIFTY 50",
            choices=["NIFTY 50", "NIFTY 100", "NIFTY 200"],
        )
        parser.add_argument("--quarters", type=int, default=4)
        parser.add_argument("--price-lookback-years", type=int, default=3)
        parser.add_argument("--forward-days", type=int, default=365)
        parser.add_argument(
            "--archive-all-indices",
            action=argparse.BooleanOptionalAction,
            default=True,
        )
        parser.add_argument(
            "--archive-constituents",
            action=argparse.BooleanOptionalAction,
            default=True,
        )
        parser.add_argument(
            "--historical-constituents",
            action=argparse.BooleanOptionalAction,
            default=True,
        )
        parser.add_argument(
            "--use-active-profile",
            action=argparse.BooleanOptionalAction,
            default=True,
        )
        parser.add_argument(
            "--explain",
            action=argparse.BooleanOptionalAction,
            default=True,
        )
        parser.add_argument(
            "--persist",
            action=argparse.BooleanOptionalAction,
            default=True,
        )
    schedule_show.add_argument(
        "--project-root",
        default=".",
        help="Repository path used in generated scheduler commands",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "dashboard":
            return launch_dashboard(args.database, args.port)
        if args.command == "constituents":
            store = ConstituentHistoryStore(args.database)
            if args.constituents_command == "list":
                data = store.list_snapshots(args.index)
            elif args.constituents_command == "import":
                imported = import_snapshots_csv(
                    store,
                    args.input,
                    index_name=args.index,
                    source=args.source,
                )
                counts = store.counts()
                print(
                    f"Imported {imported} constituent snapshots from {args.input}. "
                    f"Total constituent snapshots: {counts['constituent_snapshots']}"
                )
                return 0
            elif args.constituents_command == "archive":
                effective_date = (
                    date.fromisoformat(args.effective_date)
                    if args.effective_date
                    else None
                )
                indices = list(SUPPORTED_INDICES) if args.all_indices else [args.index]
                results = []
                for index_name in indices:
                    provider = NiftyIndexUniverseProvider(index_name)
                    results.extend(
                        archive_current_constituents(
                            store,
                            provider,
                            effective_date=effective_date,
                            skip_existing=not args.force,
                        )
                    )
                for result in results:
                    print(
                        f"{result.index_name} {result.effective_date}: "
                        f"{result.status} ({result.symbol_count} symbols)"
                    )
                return 0
            elif args.constituents_command == "import-intervals":
                intervals = load_membership_intervals_csv(args.input)
                if not args.quarter_range_start or not args.quarter_range_end:
                    raise ValueError(
                        "import-intervals requires --quarter-range-start and "
                        "--quarter-range-end to backfill quarter-end snapshots"
                    )
                result = backfill_quarter_snapshots_from_intervals(
                    store,
                    args.index,
                    intervals,
                    quarter_range_start=date.fromisoformat(args.quarter_range_start),
                    quarter_range_end=date.fromisoformat(args.quarter_range_end),
                    skip_existing=not args.force,
                )
                print(
                    f"Backfilled {result.snapshots_written} quarter-end snapshots for "
                    f"{result.index_name} from {args.input}."
                )
                return 0
            elif args.constituents_command == "import-wide":
                imported = import_wide_snapshots_csv(
                    store,
                    args.input,
                    index_name=args.index,
                    source=args.source,
                    skip_existing=not args.force,
                )
                counts = store.counts()
                print(
                    f"Imported {imported} wide constituent snapshots from {args.input}. "
                    f"Total constituent snapshots: {counts['constituent_snapshots']}"
                )
                return 0
            elif args.constituents_command == "backfill":
                changes = load_reconstitution_changes_csv(args.changes)
                anchor_date = (
                    date.fromisoformat(args.anchor_date)
                    if args.anchor_date
                    else latest_fiscal_quarter_end()
                )
                if args.anchor == "current":
                    anchor_members = NiftyIndexUniverseProvider(args.index).symbols()
                else:
                    anchor_members = store.members_as_of(args.index, anchor_date)
                    if not anchor_members:
                        raise ValueError(
                            f"No stored constituent snapshot exists for {args.index} "
                            f"on or before {anchor_date.isoformat()}"
                        )
                result = backfill_quarter_snapshots_from_changes(
                    store,
                    args.index,
                    changes,
                    anchor_members=anchor_members,
                    anchor_date=anchor_date,
                    quarter_range_start=date.fromisoformat(args.quarter_range_start),
                    quarter_range_end=date.fromisoformat(args.quarter_range_end),
                    skip_existing=not args.force,
                )
                print(
                    f"Backfilled {result.snapshots_written} quarter-end snapshots for "
                    f"{result.index_name} using {args.changes} and anchor "
                    f"{anchor_date.isoformat()} ({args.anchor})."
                )
                return 0
            elif args.constituents_command == "fetch-changes":
                if args.input:
                    exported = export_nse_changes_csv(
                        args.input,
                        args.output,
                        index_name=args.index,
                        sheet_name=args.sheet,
                    )
                    source = args.input
                else:
                    exported = download_nse_index_changes_csv(
                        args.output,
                        index_name=args.index,
                    )
                    source = "NSE IndexInclExcl.xls"
                print(
                    f"Exported {exported} reconstitution events for {args.index} "
                    f"from {source} to {args.output}."
                )
                return 0
            else:
                dates = [date.fromisoformat(value) for value in args.dates]
                data = constituent_coverage(store, args.index, dates)
        elif args.command == "profiles":
            profile_store = ScoringProfileStore(args.database)
            if args.profiles_command == "list":
                versions = profile_store.list_versions()
                data = pd.DataFrame([item.__dict__ for item in versions])
            elif args.profiles_command == "activate":
                profile_store.activate(args.version)
                print(f"Activated scoring profile version {args.version}")
                return 0
            else:
                if args.input and args.from_calibration:
                    raise ValueError("Provide either --input or --from-calibration")
                if args.input:
                    suggestions = pd.read_csv(args.input)
                elif args.from_calibration:
                    snapshots = ResearchStore(args.database).list_snapshots()
                    if snapshots.empty:
                        raise ValueError(
                            "No persisted research snapshots are available for calibration"
                        )
                    suggestions = analyze_universe_backtest(
                        snapshots,
                        low_quantile=args.low_quantile,
                        high_quantile=args.high_quantile,
                    ).threshold_suggestions
                else:
                    raise ValueError("Provide --input or --from-calibration")
                profiles_by_entity = build_profile_version(
                    suggestions,
                    min_sample_size=args.min_sample_size,
                )
                inserted = profile_store.save_version(
                    args.version,
                    profiles_by_entity,
                    source=(
                        f"csv:{args.input.name}"
                        if args.input
                        else "calibration:research_snapshots"
                    ),
                )
                if args.activate:
                    profile_store.activate(args.version)
                print(
                    f"Saved scoring profile version {args.version} "
                    f"({inserted} metric thresholds)."
                )
                if args.activate:
                    print(f"Activated scoring profile version {args.version}")
                return 0
        elif args.command == "schedule":
            schedule = _quarterly_schedule_from_args(args)
            if args.schedule_command == "show":
                print(
                    render_schedule_recipes(
                        schedule,
                        project_root=args.project_root,
                    )
                )
                return 0
            if args.schedule_command == "run-quarterly":
                result = run_quarterly_research(schedule)
                print(
                    f"Quarterly schedule completed for {result.index_name}: evaluated "
                    f"{result.symbols_evaluated}/{result.symbols_requested} symbols; "
                    f"persisted {result.records_persisted} snapshots."
                )
                if result.skipped_symbols:
                    preview = ", ".join(
                        symbol for symbol, _message in result.skipped_symbols[:5]
                    )
                    print(f"Skipped examples: {preview}")
                return 0
        elif args.command == "orchestrate":
            as_of_dates = resolve_orchestration_dates(
                as_of_dates=args.as_of_dates,
                quarter_range_start=args.quarter_range_start,
                quarter_range_end=args.quarter_range_end,
            )
            result = UniverseResearchOrchestrator(database=args.database).run(
                index_name=args.index,
                as_of_dates=as_of_dates,
                prices_start=args.prices_start,
                prices_end=args.prices_end,
                benchmark_index=args.benchmark_index,
                forward_days=args.forward_days,
                snapshot_cadence=args.cadence,
                archive_constituents=args.archive_constituents,
                use_historical_constituents=args.historical_constituents,
                benchmark_portfolio=args.benchmark_portfolio,
                persist=args.persist,
                explain=args.explain,
                profile_version=args.profile_version,
                use_active_profile=args.use_active_profile,
                max_symbols=args.max_symbols,
            )
            print(
                f"Orchestrated {result.index_name}: evaluated "
                f"{result.symbols_evaluated}/{result.symbols_requested} symbols; "
                f"persisted {result.records_persisted} snapshots; "
                f"skipped {len(result.skipped_symbols)} symbols."
            )
            if result.skipped_symbols:
                preview = ", ".join(
                    symbol for symbol, _message in result.skipped_symbols[:5]
                )
                print(f"Skipped examples: {preview}")
            return 0
        elif args.command == "calibrate":
            snapshots = ResearchStore(args.database).list_snapshots()
            if snapshots.empty:
                raise ValueError(
                    "No persisted research snapshots are available for calibration"
                )
            report = analyze_universe_backtest(
                snapshots,
                low_quantile=args.low_quantile,
                high_quantile=args.high_quantile,
            )
            if args.report in {"all", "buckets"}:
                print("Score bucket report")
                print(report.score_buckets.to_string(index=False))
            if args.report in {"all", "thresholds"}:
                if args.report == "all":
                    print()
                print("Threshold suggestions")
                print(report.threshold_suggestions.to_string(index=False))
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                if args.report == "buckets":
                    report.score_buckets.to_csv(args.output, index=False)
                    print(f"Saved score bucket report to {args.output}")
                elif args.report == "thresholds":
                    report.threshold_suggestions.to_csv(args.output, index=False)
                    print(f"Saved threshold suggestions to {args.output}")
                else:
                    bucket_path = args.output.with_name(
                        f"{args.output.stem}-buckets{args.output.suffix}"
                    )
                    threshold_path = args.output.with_name(
                        f"{args.output.stem}-thresholds{args.output.suffix}"
                    )
                    report.score_buckets.to_csv(bucket_path, index=False)
                    report.threshold_suggestions.to_csv(threshold_path, index=False)
                    print(
                        f"Saved score bucket report to {bucket_path} and threshold "
                        f"suggestions to {threshold_path}"
                    )
            return 0
        if args.command == "universe":
            data = NiftyIndexUniverseProvider(args.index).fetch()
            if args.persist:
                effective_date = (
                    date.fromisoformat(args.effective_date)
                    if args.effective_date
                    else date.today()
                )
                constituent_store = ConstituentHistoryStore(args.database)
                snapshot_key = constituent_store.record_snapshot(
                    args.index,
                    data["symbol"].tolist(),
                    effective_date=effective_date,
                    source="nifty_official",
                )
                counts = constituent_store.counts()
                print(
                    f"Recorded {len(data)} {args.index} constituents effective "
                    f"{effective_date.isoformat()} (snapshot {snapshot_key[:8]}...). "
                    f"Total constituent snapshots: {counts['constituent_snapshots']}"
                )
                if args.output is None:
                    return 0
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
            evaluator = _build_evaluator(args)
            constituent_store = (
                ConstituentHistoryStore(args.database)
                if args.benchmark_portfolio or args.historical_constituents
                else None
            )
            records = evaluator.evaluate(
                args.symbols,
                as_of_dates,
                prices,
                benchmark_index=args.benchmark_index,
                forward_days=args.forward_days,
                snapshot_cadence=args.cadence,
                portfolio_symbols=portfolio_symbols,
                constituent_store=constituent_store,
                use_historical_constituents=args.historical_constituents,
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
                        records,
                        FilingStore(args.database),
                        research_store,
                        scorer=_build_scorer(args),
                    )
                    print(f"Persisted {explained} score explanations.")
            if args.explain and not args.persist:
                data = explanations_to_frame(
                    _explain_records(
                        records,
                        FilingStore(args.database),
                        scorer=_build_scorer(args),
                    )
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
                evaluator = _build_evaluator(args)
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
                        records,
                        FilingStore(args.database),
                        research_store,
                        scorer=_build_scorer(args),
                    )
                    print(f"Persisted {explained} score explanations.")
                    data = explanations_to_frame(
                        _explain_records(
                            records,
                            FilingStore(args.database),
                            scorer=_build_scorer(args),
                        )
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


def launch_dashboard(database: Path, port: int) -> int:
    import os
    import subprocess

    script = Path(__file__).resolve().parent / "dashboard.py"
    env = os.environ.copy()
    env["INVESTING_RESEARCH_DB"] = str(database.resolve())
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(script),
            "--server.port",
            str(port),
            "--server.headless",
            "true",
        ],
        env=env,
        check=False,
    )
    return int(completed.returncode)


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


def _quarterly_schedule_from_args(args: argparse.Namespace) -> QuarterlyResearchSchedule:
    defaults = quarterly_schedule_from_env()
    return QuarterlyResearchSchedule(
        database=args.database or defaults.database,
        index_name=args.index or defaults.index_name,
        benchmark_index=args.benchmark_index or defaults.benchmark_index,
        quarters=args.quarters if args.quarters is not None else defaults.quarters,
        price_lookback_years=(
            args.price_lookback_years
            if args.price_lookback_years is not None
            else defaults.price_lookback_years
        ),
        forward_days=args.forward_days if args.forward_days is not None else defaults.forward_days,
        archive_all_indices=args.archive_all_indices,
        archive_constituents=args.archive_constituents,
        historical_constituents=args.historical_constituents,
        use_active_profile=args.use_active_profile,
        explain=args.explain,
        persist=args.persist,
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


def _resolve_profile_version(args: argparse.Namespace) -> int | None:
    if getattr(args, "profile_version", None):
        return args.profile_version
    if getattr(args, "use_active_profile", False):
        store = ScoringProfileStore(args.database)
        version = store.active_version()
        if version is None:
            raise ValueError("No active scoring profile version is configured")
        return version
    return None


def _build_scorer(args: argparse.Namespace) -> LongTermScorer | None:
    version = _resolve_profile_version(args)
    if version is None:
        return None
    return LongTermScorer(
        profile_store=ScoringProfileStore(args.database),
        profile_version=version,
    )


def _build_evaluator(args: argparse.Namespace) -> WalkForwardEvaluator:
    scorer = _build_scorer(args)
    if scorer is None:
        return WalkForwardEvaluator(filing_store=FilingStore(args.database))
    return WalkForwardEvaluator(
        filing_store=FilingStore(args.database),
        scorer=scorer,
    )


def _explain_records(
    records,
    filing_store: FilingStore,
    *,
    scorer: LongTermScorer | None = None,
):
    explainer = ScoreExplainer(scorer=scorer or LongTermScorer())
    return [explainer.explain_record(record, filing_store) for record in records]


def _persist_explanations(
    records,
    filing_store: FilingStore,
    research_store: ResearchStore,
    *,
    scorer: LongTermScorer | None = None,
) -> int:
    explanations = _explain_records(records, filing_store, scorer=scorer)
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
