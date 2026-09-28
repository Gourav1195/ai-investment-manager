"""Scheduled Nifty universe research orchestration."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Iterable, Iterator, Protocol

import pandas as pd

from .calibration import (
    CalibrationReport,
    analyze_universe_backtest,
    serialize_calibration_report,
)
from .constituents import (
    ConstituentHistoryStore,
    archive_current_constituents,
    resolve_portfolio_symbols,
)
from .explanations import ScoreExplainer
from .filings import FilingStore, IST
from .profile_store import ScoringProfileStore
from .providers import NiftyIndexUniverseProvider, YFinancePriceProvider, nifty_benchmark_symbol
from .research import (
    ResearchRecord,
    ResearchStore,
    SnapshotCadence,
    WalkForwardEvaluator,
    fiscal_quarter_end_dates,
)
from .scoring import LongTermScorer


ORCHESTRATION_STORE_VERSION = 2


class PriceHistory(Protocol):
    def fetch(self, symbols: Iterable[str], start: str, end: str) -> pd.DataFrame: ...


@dataclass(frozen=True)
class UniverseRunResult:
    run_key: str
    index_name: str
    as_of_dates: tuple[str, ...]
    symbols_requested: int
    symbols_evaluated: int
    records_persisted: int
    skipped_symbols: tuple[tuple[str, str], ...]
    archive_status: str
    calibration: CalibrationReport | None = None


class OrchestrationStore:
    """Persist universe orchestration run summaries."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def save_run(self, result: UniverseRunResult, *, benchmark_index: str, forward_days: int) -> None:
        created_at = datetime.now(tz=IST).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO research_orchestration_runs (
                    run_key,
                    index_name,
                    as_of_dates_json,
                    symbols_requested,
                    symbols_evaluated,
                    records_persisted,
                    skipped_symbols_json,
                    benchmark_index,
                    forward_days,
                    archive_status,
                    calibration_json,
                    store_version,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.run_key,
                    result.index_name,
                    json.dumps(list(result.as_of_dates)),
                    result.symbols_requested,
                    result.symbols_evaluated,
                    result.records_persisted,
                    json.dumps(list(result.skipped_symbols)),
                    benchmark_index,
                    forward_days,
                    result.archive_status,
                    (
                        serialize_calibration_report(result.calibration)
                        if result.calibration is not None
                        else None
                    ),
                    ORCHESTRATION_STORE_VERSION,
                    created_at,
                ),
            )

    def list_runs(self) -> pd.DataFrame:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM research_orchestration_runs
                ORDER BY created_at DESC
                """
            ).fetchall()
        return (
            pd.DataFrame([dict(row) for row in rows], columns=rows[0].keys())
            if rows
            else pd.DataFrame()
        )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS research_orchestration_runs (
                    run_key TEXT PRIMARY KEY,
                    index_name TEXT NOT NULL,
                    as_of_dates_json TEXT NOT NULL,
                    symbols_requested INTEGER NOT NULL,
                    symbols_evaluated INTEGER NOT NULL,
                    records_persisted INTEGER NOT NULL,
                    skipped_symbols_json TEXT NOT NULL,
                    benchmark_index TEXT NOT NULL,
                    forward_days INTEGER NOT NULL,
                    archive_status TEXT NOT NULL,
                    calibration_json TEXT,
                    store_version INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                """)
            columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(research_orchestration_runs)"
                )
            }
            if "calibration_json" not in columns:
                connection.execute(
                    "ALTER TABLE research_orchestration_runs "
                    "ADD COLUMN calibration_json TEXT"
                )


class UniverseResearchOrchestrator:
    """Run walk-forward research across a Nifty index universe."""

    def __init__(
        self,
        *,
        database: str | Path,
        universe_provider: NiftyIndexUniverseProvider | None = None,
        price_provider: PriceHistory | None = None,
        filing_store: FilingStore | None = None,
    ) -> None:
        self.database = Path(database)
        self.universe_provider = universe_provider
        self.price_provider = price_provider or YFinancePriceProvider()
        self.filing_store = filing_store or FilingStore(self.database)
        self.research_store = ResearchStore(self.database)
        self.constituent_store = ConstituentHistoryStore(self.database)
        self.profile_store = ScoringProfileStore(self.database)
        self.orchestration_store = OrchestrationStore(self.database)

    def run(
        self,
        *,
        index_name: str = "NIFTY 50",
        as_of_dates: list[datetime],
        prices_start: str,
        prices_end: str,
        benchmark_index: str = "NIFTY 50",
        forward_days: int = 365,
        snapshot_cadence: SnapshotCadence = "quarterly",
        archive_constituents: bool = False,
        use_historical_constituents: bool = True,
        benchmark_portfolio: bool = True,
        persist: bool = True,
        explain: bool = False,
        profile_version: int | None = None,
        use_active_profile: bool = False,
        max_symbols: int | None = None,
    ) -> UniverseRunResult:
        if not as_of_dates:
            raise ValueError("At least one as-of date is required")

        provider = self.universe_provider or NiftyIndexUniverseProvider(index_name)
        symbols = provider.symbols()
        if max_symbols is not None:
            symbols = symbols[:max_symbols]
        if not symbols:
            raise ValueError(f"No symbols were returned for {index_name}")

        archive_status = "skipped"
        if archive_constituents:
            archive_results = archive_current_constituents(
                self.constituent_store,
                provider,
            )
            archive_status = ",".join(result.status for result in archive_results)

        portfolio_symbols = provider.symbols() if benchmark_portfolio else []
        price_symbols = _price_symbols(
            symbols,
            benchmark_index=benchmark_index,
            portfolio_symbols=portfolio_symbols,
            as_of_dates=as_of_dates,
            constituent_store=self.constituent_store,
            use_historical=use_historical_constituents,
        )
        prices = self.price_provider.fetch(price_symbols, prices_start, prices_end)

        scorer = _build_scorer(
            self.profile_store,
            profile_version=profile_version,
            use_active_profile=use_active_profile,
        )
        evaluator = WalkForwardEvaluator(
            filing_store=self.filing_store,
            scorer=scorer or LongTermScorer(),
        )

        records: list[ResearchRecord] = []
        skipped: list[tuple[str, str]] = []
        for symbol in symbols:
            try:
                records.extend(
                    evaluator.evaluate(
                        [symbol],
                        as_of_dates,
                        prices,
                        benchmark_index=benchmark_index,
                        forward_days=forward_days,
                        snapshot_cadence=snapshot_cadence,
                        portfolio_symbols=portfolio_symbols,
                        constituent_store=self.constituent_store,
                        use_historical_constituents=use_historical_constituents,
                    )
                )
            except ValueError as exc:
                skipped.append((symbol, str(exc)))

        records_persisted = 0
        if persist and records:
            records_persisted = self.research_store.save_records(records)
            if explain:
                explainer = ScoreExplainer(scorer=scorer or LongTermScorer())
                items = []
                for record in records:
                    explanation = explainer.explain_record(record, self.filing_store)
                    from .research import _snapshot_key

                    items.append(
                        (
                            _snapshot_key(record.evaluation_key, record.snapshot.symbol),
                            record.evaluation_key,
                            explanation.to_record(),
                        )
                    )
                self.research_store.save_explanations(items)

        calibration = None
        if records_persisted:
            snapshots = self.research_store.list_snapshots()
            run_snapshots = _snapshots_for_run(snapshots, as_of_dates)
            if not run_snapshots.empty:
                calibration = analyze_universe_backtest(run_snapshots)

        result = UniverseRunResult(
            run_key=_run_key(index_name, as_of_dates, symbols),
            index_name=index_name.strip().upper(),
            as_of_dates=tuple(sorted(as_of.isoformat() for as_of in as_of_dates)),
            symbols_requested=len(symbols),
            symbols_evaluated=len({record.snapshot.symbol for record in records}),
            records_persisted=records_persisted,
            skipped_symbols=tuple(skipped),
            archive_status=archive_status,
            calibration=calibration,
        )
        self.orchestration_store.save_run(
            result,
            benchmark_index=benchmark_index,
            forward_days=forward_days,
        )
        return result


def resolve_orchestration_dates(
    *,
    as_of_dates: list[str] | None = None,
    quarter_range_start: str | None = None,
    quarter_range_end: str | None = None,
) -> list[datetime]:
    if quarter_range_start and quarter_range_end:
        return fiscal_quarter_end_dates(
            date.fromisoformat(quarter_range_start),
            date.fromisoformat(quarter_range_end),
        )
    if as_of_dates:
        return [_parse_as_of(value) for value in as_of_dates]
    raise ValueError(
        "Provide --as-of-dates or both --quarter-range-start and --quarter-range-end"
    )


def _price_symbols(
    symbols: list[str],
    *,
    benchmark_index: str,
    portfolio_symbols: list[str],
    as_of_dates: list[datetime],
    constituent_store: ConstituentHistoryStore,
    use_historical: bool,
) -> list[str]:
    resolved_portfolio: list[str] = []
    if portfolio_symbols:
        for as_of in as_of_dates:
            members, _source = resolve_portfolio_symbols(
                benchmark_index=benchmark_index,
                as_of=as_of.date(),
                store=constituent_store,
                use_historical=use_historical,
                fallback_symbols=portfolio_symbols,
            )
            resolved_portfolio.extend(members)
    return list(
        dict.fromkeys(
            [
                *symbols,
                nifty_benchmark_symbol(benchmark_index),
                *resolved_portfolio,
            ]
        )
    )


def _build_scorer(
    profile_store: ScoringProfileStore,
    *,
    profile_version: int | None,
    use_active_profile: bool,
) -> LongTermScorer | None:
    version = profile_version
    if version is None and use_active_profile:
        version = profile_store.active_version()
        if version is None:
            raise ValueError("No active scoring profile version is configured")
    if version is None:
        return None
    return LongTermScorer(profile_store=profile_store, profile_version=version)


def _parse_as_of(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        from datetime import time

        if "T" not in value and " " not in value:
            parsed = datetime.combine(parsed.date(), time.max)
        parsed = parsed.replace(tzinfo=IST)
    return parsed.astimezone(IST)


def _snapshots_for_run(
    snapshots: pd.DataFrame,
    as_of_dates: list[datetime],
) -> pd.DataFrame:
    if snapshots.empty:
        return snapshots
    normalized_dates = {_normalize_as_of_date(as_of.isoformat()) for as_of in as_of_dates}
    frame = snapshots.copy()
    frame["_as_of_key"] = frame["as_of"].map(_normalize_as_of_date)
    return frame[frame["_as_of_key"].isin(normalized_dates)].drop(columns="_as_of_key")


def _normalize_as_of_date(value: object) -> str:
    text = str(value).strip()
    if "T" in text:
        return text.split("T", 1)[0]
    return text


def _run_key(index_name: str, as_of_dates: list[datetime], symbols: list[str]) -> str:
    payload = "|".join(
        [
            index_name.strip().upper(),
            ",".join(sorted(as_of.isoformat() for as_of in as_of_dates)),
            ",".join(sorted(symbols)),
        ]
    )
    return sha256(payload.encode("utf-8")).hexdigest()
