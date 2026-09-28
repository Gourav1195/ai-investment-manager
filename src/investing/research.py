"""Walk-forward research evaluation, persistence, and benchmark comparison."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable, Iterator, Literal, Mapping, Protocol

import pandas as pd

from .constituents import ConstituentHistoryStore, resolve_portfolio_symbols
from .filings import FilingStore, IST
from .fundamentals import CALCULATION_VERSION, FundamentalCalculator, FundamentalSnapshot
from .market import (
    MARKET_JOIN_VERSION,
    MarketMetricsJoiner,
    equal_weight_portfolio_forward_return,
    forward_return,
    snapshots_to_scorer_frame,
)
from .providers import nifty_benchmark_symbol
from .scoring import LongTermScorer

RESEARCH_STORE_VERSION = 4
DEFAULT_FORWARD_DAYS = 365
SnapshotCadence = Literal["annual", "quarterly"]
FISCAL_QUARTER_ENDS = ((6, 30), (9, 30), (12, 31), (3, 31))


@dataclass(frozen=True)
class ResearchRecord:
    evaluation_key: str
    as_of: str
    benchmark_index: str
    benchmark_symbol: str
    forward_days: int
    snapshot: FundamentalSnapshot
    overall_score: float | None = None
    research_view: str | None = None
    rank: int | None = None
    data_coverage: float | None = None
    quality_score: float | None = None
    growth_score: float | None = None
    financial_strength_score: float | None = None
    valuation_score: float | None = None
    price_discipline_score: float | None = None
    forward_return: float | None = None
    benchmark_forward_return: float | None = None
    excess_forward_return: float | None = None
    snapshot_cadence: SnapshotCadence = "annual"
    portfolio_symbols: tuple[str, ...] = ()
    portfolio_forward_return: float | None = None
    excess_portfolio_forward_return: float | None = None

    def to_row(self) -> dict[str, Any]:
        row = self.snapshot.to_record()
        row.update(
            {
                "evaluation_key": self.evaluation_key,
                "benchmark_index": self.benchmark_index,
                "benchmark_symbol": self.benchmark_symbol,
                "forward_days": self.forward_days,
                "snapshot_cadence": self.snapshot_cadence,
                "portfolio_symbols": ";".join(self.portfolio_symbols),
                "overall_score": self.overall_score,
                "research_view": self.research_view,
                "rank": self.rank,
                "data_coverage": self.data_coverage,
                "quality_score": self.quality_score,
                "growth_score": self.growth_score,
                "financial_strength_score": self.financial_strength_score,
                "valuation_score": self.valuation_score,
                "price_discipline_score": self.price_discipline_score,
                "forward_return": self.forward_return,
                "benchmark_forward_return": self.benchmark_forward_return,
                "excess_forward_return": self.excess_forward_return,
                "portfolio_forward_return": self.portfolio_forward_return,
                "excess_portfolio_forward_return": self.excess_portfolio_forward_return,
            }
        )
        return row


class PriceHistory(Protocol):
    def fetch(self, symbols: Iterable[str], start: str, end: str) -> pd.DataFrame: ...


class WalkForwardEvaluator:
    """Evaluate, score, and benchmark multiple symbols across as-of dates."""

    def __init__(
        self,
        *,
        filing_store: FilingStore,
        calculator: FundamentalCalculator | None = None,
        joiner: MarketMetricsJoiner | None = None,
        scorer: LongTermScorer | None = None,
    ) -> None:
        self.filing_store = filing_store
        self.calculator = calculator or FundamentalCalculator()
        self.joiner = joiner or MarketMetricsJoiner()
        self.scorer = scorer or LongTermScorer()

    def evaluate(
        self,
        symbols: list[str],
        as_of_dates: list[datetime],
        prices: pd.DataFrame,
        *,
        benchmark_index: str = "NIFTY 50",
        forward_days: int = DEFAULT_FORWARD_DAYS,
        snapshot_cadence: SnapshotCadence = "annual",
        portfolio_symbols: list[str] | None = None,
        constituent_store: ConstituentHistoryStore | None = None,
        use_historical_constituents: bool = False,
    ) -> list[ResearchRecord]:
        if not symbols:
            raise ValueError("At least one symbol is required")
        if not as_of_dates:
            raise ValueError("At least one as-of date is required")
        if forward_days < 1:
            raise ValueError("forward_days must be at least 1")

        benchmark_symbol = nifty_benchmark_symbol(benchmark_index)
        normalized_symbols = _normalize_symbols(symbols)
        fallback_portfolio = (
            _normalize_symbols(portfolio_symbols) if portfolio_symbols else []
        )
        records: list[ResearchRecord] = []

        for as_of in sorted(as_of_dates):
            normalized_portfolio, _membership_source = resolve_portfolio_symbols(
                benchmark_index=benchmark_index,
                as_of=as_of.date(),
                store=constituent_store,
                use_historical=use_historical_constituents,
                fallback_symbols=fallback_portfolio,
            )
            evaluation_key = _evaluation_key(
                as_of=as_of,
                symbols=normalized_symbols,
                benchmark_index=benchmark_index,
                forward_days=forward_days,
                snapshot_cadence=snapshot_cadence,
                portfolio_symbols=normalized_portfolio,
            )
            snapshots = self._build_snapshots(normalized_symbols, as_of, prices)
            score_lookup = self._score_lookup(snapshots)
            benchmark_forward = forward_return(
                prices,
                benchmark_symbol,
                as_of,
                forward_days=forward_days,
            )
            portfolio_forward = (
                equal_weight_portfolio_forward_return(
                    prices,
                    normalized_portfolio,
                    as_of,
                    forward_days=forward_days,
                )
                if normalized_portfolio
                else None
            )
            for snapshot in snapshots:
                score_row = score_lookup.get(snapshot.symbol, {})
                stock_forward = forward_return(
                    prices,
                    snapshot.symbol,
                    as_of,
                    forward_days=forward_days,
                )
                excess = (
                    stock_forward - benchmark_forward
                    if stock_forward is not None and benchmark_forward is not None
                    else None
                )
                excess_portfolio = (
                    stock_forward - portfolio_forward
                    if stock_forward is not None and portfolio_forward is not None
                    else None
                )
                records.append(
                    ResearchRecord(
                        evaluation_key=evaluation_key,
                        as_of=snapshot.as_of,
                        benchmark_index=benchmark_index.strip().upper(),
                        benchmark_symbol=benchmark_symbol,
                        forward_days=forward_days,
                        snapshot_cadence=snapshot_cadence,
                        portfolio_symbols=tuple(normalized_portfolio),
                        snapshot=snapshot,
                        overall_score=_optional_float(score_row.get("overall_score")),
                        research_view=_optional_text(score_row.get("research_view")),
                        rank=_optional_int(score_row.get("rank")),
                        data_coverage=_optional_float(score_row.get("data_coverage")),
                        quality_score=_optional_float(score_row.get("quality_score")),
                        growth_score=_optional_float(score_row.get("growth_score")),
                        financial_strength_score=_optional_float(
                            score_row.get("financial_strength_score")
                        ),
                        valuation_score=_optional_float(score_row.get("valuation_score")),
                        price_discipline_score=_optional_float(
                            score_row.get("price_discipline_score")
                        ),
                        forward_return=stock_forward,
                        benchmark_forward_return=benchmark_forward,
                        excess_forward_return=excess,
                        portfolio_forward_return=portfolio_forward,
                        excess_portfolio_forward_return=excess_portfolio,
                    )
                )
        return records

    def _build_snapshots(
        self,
        symbols: list[str],
        as_of: datetime,
        prices: pd.DataFrame,
    ) -> list[FundamentalSnapshot]:
        snapshots: list[FundamentalSnapshot] = []
        for symbol in symbols:
            snapshot = self.calculator.calculate(
                self.filing_store.canonical_observations_as_of(symbol, as_of),
                symbol=symbol,
                as_of=as_of,
            )
            snapshots.append(self.joiner.join(snapshot, prices))
        return snapshots

    def _score_lookup(self, snapshots: list[FundamentalSnapshot]) -> dict[str, Mapping]:
        if not snapshots:
            return {}
        scored = self.scorer.score(snapshots_to_scorer_frame(snapshots))
        return {
            str(row["symbol"]): row for row in scored.to_dict(orient="records")
        }


class ResearchStore:
    """Persist walk-forward research evaluations in SQLite."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def save_records(self, records: Iterable[ResearchRecord]) -> int:
        materialized = list(records)
        if not materialized:
            return 0

        created_at = datetime.now(tz=IST).isoformat()
        inserted = 0
        with self._connect() as connection:
            for evaluation_key, group in _group_by_evaluation(materialized).items():
                first = group[0]
                connection.execute(
                    """
                    INSERT OR REPLACE INTO research_evaluations (
                        evaluation_key,
                        as_of,
                        benchmark_index,
                        benchmark_symbol,
                        forward_days,
                        snapshot_cadence,
                        symbols_json,
                        portfolio_symbols_json,
                        calculation_version,
                        market_join_version,
                        store_version,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        evaluation_key,
                        first.as_of,
                        first.benchmark_index,
                        first.benchmark_symbol,
                        first.forward_days,
                        first.snapshot_cadence,
                        json.dumps(sorted({item.snapshot.symbol for item in group})),
                        json.dumps(sorted(first.portfolio_symbols)),
                        CALCULATION_VERSION,
                        MARKET_JOIN_VERSION,
                        RESEARCH_STORE_VERSION,
                        created_at,
                    ),
                )
                for record in group:
                    snapshot_key = _snapshot_key(
                        evaluation_key, record.snapshot.symbol
                    )
                    row = record.to_row()
                    connection.execute(
                        """
                        INSERT OR REPLACE INTO research_snapshots (
                            snapshot_key,
                            evaluation_key,
                            symbol,
                            as_of,
                            entity_type,
                            period_end,
                            roe,
                            roce,
                            operating_margin,
                            revenue_cagr_3y,
                            earnings_cagr_3y,
                            debt_to_equity,
                            interest_coverage,
                            free_cash_flow,
                            pre_tax_margin,
                            return_on_assets,
                            gross_npa_ratio,
                            cet1_ratio,
                            profit_margin,
                            investment_income_ratio,
                            equity_to_assets,
                            latest_net_income,
                            basic_eps,
                            book_equity,
                            price_date,
                            price,
                            shares_outstanding,
                            pe,
                            pb,
                            free_cash_flow_yield,
                            volatility_1y,
                            overall_score,
                            research_view,
                            rank,
                            data_coverage,
                            quality_score,
                            growth_score,
                            financial_strength_score,
                            valuation_score,
                            price_discipline_score,
                            forward_return,
                            benchmark_forward_return,
                            excess_forward_return,
                            snapshot_cadence,
                            portfolio_forward_return,
                            excess_portfolio_forward_return,
                            calculation_version,
                            market_join_version,
                            source_filing_keys,
                            created_at
                        ) VALUES (
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                        )
                        """,
                        (
                            snapshot_key,
                            evaluation_key,
                            row["symbol"],
                            row["as_of"],
                            row.get("entity_type"),
                            row.get("period_end"),
                            row.get("roe"),
                            row.get("roce"),
                            row.get("operating_margin"),
                            row.get("revenue_cagr_3y"),
                            row.get("earnings_cagr_3y"),
                            row.get("debt_to_equity"),
                            row.get("interest_coverage"),
                            row.get("free_cash_flow"),
                            row.get("pre_tax_margin"),
                            row.get("return_on_assets"),
                            row.get("gross_npa_ratio"),
                            row.get("cet1_ratio"),
                            row.get("profit_margin"),
                            row.get("investment_income_ratio"),
                            row.get("equity_to_assets"),
                            row.get("latest_net_income"),
                            row.get("basic_eps"),
                            row.get("book_equity"),
                            row.get("price_date"),
                            row.get("price"),
                            row.get("shares_outstanding"),
                            row.get("pe"),
                            row.get("pb"),
                            row.get("free_cash_flow_yield"),
                            row.get("volatility_1y"),
                            row.get("overall_score"),
                            row.get("research_view"),
                            row.get("rank"),
                            row.get("data_coverage"),
                            row.get("quality_score"),
                            row.get("growth_score"),
                            row.get("financial_strength_score"),
                            row.get("valuation_score"),
                            row.get("price_discipline_score"),
                            row.get("forward_return"),
                            row.get("benchmark_forward_return"),
                            row.get("excess_forward_return"),
                            row.get("snapshot_cadence"),
                            row.get("portfolio_forward_return"),
                            row.get("excess_portfolio_forward_return"),
                            row.get("calculation_version"),
                            row.get("market_join_version"),
                            row.get("source_filing_keys"),
                            created_at,
                        ),
                    )
                    inserted += 1
        return inserted

    def list_evaluations(self) -> pd.DataFrame:
        query = """
            SELECT *
            FROM research_evaluations
            ORDER BY as_of DESC, created_at DESC
        """
        with self._connect() as connection:
            rows = connection.execute(query).fetchall()
        return (
            pd.DataFrame([dict(row) for row in rows], columns=rows[0].keys())
            if rows
            else pd.DataFrame()
        )

    def list_snapshots(
        self,
        *,
        symbol: str | None = None,
        as_of: str | None = None,
    ) -> pd.DataFrame:
        query = "SELECT * FROM research_snapshots"
        filters: list[str] = []
        params: list[Any] = []
        if symbol is not None:
            filters.append("symbol = ?")
            params.append(symbol.strip().upper())
        if as_of is not None:
            filters.append("as_of = ?")
            params.append(as_of)
        if filters:
            query += " WHERE " + " AND ".join(filters)
        query += " ORDER BY as_of, symbol"

        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return pd.DataFrame([dict(row) for row in rows], columns=rows[0].keys()) if rows else pd.DataFrame()

    def save_explanations(
        self,
        items: Iterable[tuple[str, str, Mapping[str, Any]]],
    ) -> int:
        """Persist explanations keyed by ``(snapshot_key, evaluation_key, record)``."""

        created_at = datetime.now(tz=IST).isoformat()
        inserted = 0
        with self._connect() as connection:
            for snapshot_key, evaluation_key, row in items:
                explanation_key = _explanation_key(snapshot_key)
                connection.execute(
                    """
                    INSERT OR REPLACE INTO research_explanations (
                        explanation_key,
                        snapshot_key,
                        evaluation_key,
                        symbol,
                        as_of,
                        research_view,
                        overall_score,
                        data_coverage,
                        score_drivers_json,
                        risk_flags_json,
                        source_documents_json,
                        explanation_version,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        explanation_key,
                        snapshot_key,
                        evaluation_key,
                        row["symbol"],
                        row["as_of"],
                        row.get("research_view"),
                        row.get("overall_score"),
                        row.get("data_coverage"),
                        row.get("score_drivers_json", "[]"),
                        row.get("risk_flags_json", "[]"),
                        row.get("source_documents_json", "[]"),
                        row.get("explanation_version", 1),
                        created_at,
                    ),
                )
                inserted += 1
        return inserted

    def list_explanations(
        self,
        *,
        symbol: str | None = None,
        as_of: str | None = None,
    ) -> pd.DataFrame:
        query = "SELECT * FROM research_explanations"
        filters: list[str] = []
        params: list[Any] = []
        if symbol is not None:
            filters.append("symbol = ?")
            params.append(symbol.strip().upper())
        if as_of is not None:
            filters.append("as_of = ?")
            params.append(as_of)
        if filters:
            query += " WHERE " + " AND ".join(filters)
        query += " ORDER BY as_of, symbol"
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return (
            pd.DataFrame([dict(row) for row in rows], columns=rows[0].keys())
            if rows
            else pd.DataFrame()
        )

    def counts(self) -> dict[str, int]:
        with self._connect() as connection:
            evaluations = connection.execute(
                "SELECT COUNT(*) FROM research_evaluations"
            ).fetchone()[0]
            snapshots = connection.execute(
                "SELECT COUNT(*) FROM research_snapshots"
            ).fetchone()[0]
            explanations = connection.execute(
                "SELECT COUNT(*) FROM research_explanations"
            ).fetchone()[0]
        return {
            "evaluations": evaluations,
            "snapshots": snapshots,
            "explanations": explanations,
        }

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS research_evaluations (
                    evaluation_key TEXT PRIMARY KEY,
                    as_of TEXT NOT NULL,
                    benchmark_index TEXT NOT NULL,
                    benchmark_symbol TEXT NOT NULL,
                    forward_days INTEGER NOT NULL CHECK (forward_days > 0),
                    snapshot_cadence TEXT NOT NULL DEFAULT 'annual',
                    symbols_json TEXT NOT NULL,
                    portfolio_symbols_json TEXT,
                    calculation_version INTEGER NOT NULL,
                    market_join_version INTEGER NOT NULL,
                    store_version INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS research_snapshots (
                    snapshot_key TEXT PRIMARY KEY,
                    evaluation_key TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    as_of TEXT NOT NULL,
                    entity_type TEXT,
                    period_end TEXT,
                    roe REAL,
                    roce REAL,
                    operating_margin REAL,
                    revenue_cagr_3y REAL,
                    earnings_cagr_3y REAL,
                    debt_to_equity REAL,
                    interest_coverage REAL,
                    free_cash_flow REAL,
                    pre_tax_margin REAL,
                    return_on_assets REAL,
                    gross_npa_ratio REAL,
                    cet1_ratio REAL,
                    profit_margin REAL,
                    investment_income_ratio REAL,
                    equity_to_assets REAL,
                    latest_net_income REAL,
                    basic_eps REAL,
                    book_equity REAL,
                    price_date TEXT,
                    price REAL,
                    shares_outstanding REAL,
                    pe REAL,
                    pb REAL,
                    free_cash_flow_yield REAL,
                    volatility_1y REAL,
                    overall_score REAL,
                    research_view TEXT,
                    rank INTEGER,
                    data_coverage REAL,
                    quality_score REAL,
                    growth_score REAL,
                    financial_strength_score REAL,
                    valuation_score REAL,
                    price_discipline_score REAL,
                    forward_return REAL,
                    benchmark_forward_return REAL,
                    excess_forward_return REAL,
                    snapshot_cadence TEXT NOT NULL DEFAULT 'annual',
                    portfolio_forward_return REAL,
                    excess_portfolio_forward_return REAL,
                    calculation_version INTEGER NOT NULL,
                    market_join_version INTEGER,
                    source_filing_keys TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE (evaluation_key, symbol),
                    FOREIGN KEY (evaluation_key)
                        REFERENCES research_evaluations(evaluation_key)
                );

                CREATE INDEX IF NOT EXISTS idx_research_snapshots_symbol_as_of
                ON research_snapshots(symbol, as_of);

                CREATE TABLE IF NOT EXISTS research_explanations (
                    explanation_key TEXT PRIMARY KEY,
                    snapshot_key TEXT NOT NULL UNIQUE,
                    evaluation_key TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    as_of TEXT NOT NULL,
                    research_view TEXT,
                    overall_score REAL,
                    data_coverage REAL,
                    score_drivers_json TEXT NOT NULL,
                    risk_flags_json TEXT NOT NULL,
                    source_documents_json TEXT NOT NULL,
                    explanation_version INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (snapshot_key)
                        REFERENCES research_snapshots(snapshot_key),
                    FOREIGN KEY (evaluation_key)
                        REFERENCES research_evaluations(evaluation_key)
                );
                """)
            self._migrate(connection)

    @staticmethod
    def _migrate(connection: sqlite3.Connection) -> None:
        evaluation_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(research_evaluations)")
        }
        snapshot_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(research_snapshots)")
        }
        if "snapshot_cadence" not in evaluation_columns:
            connection.execute(
                "ALTER TABLE research_evaluations "
                "ADD COLUMN snapshot_cadence TEXT NOT NULL DEFAULT 'annual'"
            )
        if "portfolio_symbols_json" not in evaluation_columns:
            connection.execute(
                "ALTER TABLE research_evaluations ADD COLUMN portfolio_symbols_json TEXT"
            )
        if "snapshot_cadence" not in snapshot_columns:
            connection.execute(
                "ALTER TABLE research_snapshots "
                "ADD COLUMN snapshot_cadence TEXT NOT NULL DEFAULT 'annual'"
            )
        if "portfolio_forward_return" not in snapshot_columns:
            connection.execute(
                "ALTER TABLE research_snapshots ADD COLUMN portfolio_forward_return REAL"
            )
        if "excess_portfolio_forward_return" not in snapshot_columns:
            connection.execute(
                "ALTER TABLE research_snapshots "
                "ADD COLUMN excess_portfolio_forward_return REAL"
            )
        if "profit_margin" not in snapshot_columns:
            connection.execute(
                "ALTER TABLE research_snapshots ADD COLUMN profit_margin REAL"
            )
        if "investment_income_ratio" not in snapshot_columns:
            connection.execute(
                "ALTER TABLE research_snapshots ADD COLUMN investment_income_ratio REAL"
            )
        if "equity_to_assets" not in snapshot_columns:
            connection.execute(
                "ALTER TABLE research_snapshots ADD COLUMN equity_to_assets REAL"
            )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS research_explanations (
                explanation_key TEXT PRIMARY KEY,
                snapshot_key TEXT NOT NULL UNIQUE,
                evaluation_key TEXT NOT NULL,
                symbol TEXT NOT NULL,
                as_of TEXT NOT NULL,
                research_view TEXT,
                overall_score REAL,
                data_coverage REAL,
                score_drivers_json TEXT NOT NULL,
                risk_flags_json TEXT NOT NULL,
                source_documents_json TEXT NOT NULL,
                explanation_version INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (snapshot_key)
                    REFERENCES research_snapshots(snapshot_key),
                FOREIGN KEY (evaluation_key)
                    REFERENCES research_evaluations(evaluation_key)
            )
            """
        )


def fiscal_quarter_end_dates(start: date, end: date) -> list[datetime]:
    """Return Indian fiscal quarter-end dates between ``start`` and ``end``."""

    if end < start:
        raise ValueError("end must be on or after start")
    candidates: set[date] = set()
    for year in range(start.year - 1, end.year + 1):
        for month, day in FISCAL_QUARTER_ENDS:
            try:
                candidate = date(year, month, day)
            except ValueError:
                continue
            if start <= candidate <= end:
                candidates.add(candidate)
    return [
        datetime.combine(candidate, time.max, tzinfo=IST)
        for candidate in sorted(candidates)
    ]


def walkforward_report(records: Iterable[ResearchRecord]) -> pd.DataFrame:
    """Summarize walk-forward research output by as-of date."""

    frame = records_to_frame(records)
    if frame.empty:
        return frame
    summary_columns = [
        "as_of",
        "snapshot_cadence",
        "symbol",
        "rank",
        "overall_score",
        "research_view",
        "forward_return",
        "benchmark_forward_return",
        "excess_forward_return",
        "portfolio_forward_return",
        "excess_portfolio_forward_return",
    ]
    present = [column for column in summary_columns if column in frame.columns]
    return frame[present].sort_values(["as_of", "rank", "symbol"], na_position="last")


def records_to_frame(records: Iterable[ResearchRecord]) -> pd.DataFrame:
    materialized = [record.to_row() for record in records]
    return pd.DataFrame(materialized) if materialized else pd.DataFrame()


def _normalize_symbols(symbols: Iterable[str]) -> list[str]:
    normalized = [symbol.strip().upper() for symbol in symbols]
    if any(not symbol for symbol in normalized):
        raise ValueError("Symbols cannot be blank")
    return list(dict.fromkeys(normalized))


def _evaluation_key(
    *,
    as_of: datetime,
    symbols: list[str],
    benchmark_index: str,
    forward_days: int,
    snapshot_cadence: SnapshotCadence = "annual",
    portfolio_symbols: list[str] | None = None,
) -> str:
    payload = "|".join(
        [
            as_of.astimezone(IST).isoformat(),
            benchmark_index.strip().upper(),
            str(forward_days),
            snapshot_cadence,
            str(CALCULATION_VERSION),
            str(MARKET_JOIN_VERSION),
            ",".join(symbols),
            ",".join(portfolio_symbols or []),
        ]
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def _snapshot_key(evaluation_key: str, symbol: str) -> str:
    payload = f"{evaluation_key}|{symbol.strip().upper()}"
    return sha256(payload.encode("utf-8")).hexdigest()


def _explanation_key(snapshot_key: str) -> str:
    return sha256(f"explanation|{snapshot_key}".encode("utf-8")).hexdigest()


def _group_by_evaluation(
    records: list[ResearchRecord],
) -> dict[str, list[ResearchRecord]]:
    grouped: dict[str, list[ResearchRecord]] = {}
    for record in records:
        grouped.setdefault(record.evaluation_key, []).append(record)
    return grouped


def _optional_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _optional_int(value: Any) -> int | None:
    if value is None or pd.isna(value):
        return None
    return int(value)


def _optional_text(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None
