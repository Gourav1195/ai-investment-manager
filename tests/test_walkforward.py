from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

from src.investing.filings import IST
from src.investing.research import (
    ResearchStore,
    WalkForwardEvaluator,
    fiscal_quarter_end_dates,
    walkforward_report,
)
from tests.test_fundamental_calculator import non_bank_history


class FakeFilingStore:
    def canonical_observations_as_of(self, symbol: str, as_of: datetime):
        rows = non_bank_history()
        for row in rows:
            row["symbol"] = symbol.strip().upper()
        return rows


def synthetic_prices() -> pd.DataFrame:
    stock_dates = pd.bdate_range("2024-01-01", "2026-01-01")
    stock = pd.Series(100.0, index=stock_dates)
    stock.iloc[120:] = stock.iloc[120:] + pd.Series(range(len(stock) - 120), index=stock.index[120:])
    benchmark = pd.Series(1000.0, index=stock_dates)
    benchmark.iloc[120:] = benchmark.iloc[120:] * 1.001

    stock_frame = pd.DataFrame(
        {
            "date": stock.index,
            "symbol": "TEST",
            "open": stock.values,
            "high": stock.values,
            "low": stock.values,
            "close": stock.values,
            "adj_close": stock.values,
            "volume": 1_000,
        }
    )
    benchmark_frame = pd.DataFrame(
        {
            "date": benchmark.index,
            "symbol": "^NSEI",
            "open": benchmark.values,
            "high": benchmark.values,
            "low": benchmark.values,
            "close": benchmark.values,
            "adj_close": benchmark.values,
            "volume": 1_000,
        }
    )
    return pd.concat([stock_frame, benchmark_frame], ignore_index=True)


def test_walkforward_evaluator_scores_and_benchmarks() -> None:
    evaluator = WalkForwardEvaluator(filing_store=FakeFilingStore())
    as_of = datetime(2025, 7, 1, tzinfo=IST)
    records = evaluator.evaluate(
        ["TEST"],
        [as_of],
        synthetic_prices(),
        benchmark_index="NIFTY 50",
        forward_days=30,
    )

    assert len(records) == 1
    record = records[0]
    assert record.snapshot.symbol == "TEST"
    assert record.overall_score is not None
    assert record.research_view is not None
    assert record.forward_return is not None
    assert record.benchmark_forward_return is not None
    assert record.excess_forward_return == pytest.approx(
        record.forward_return - record.benchmark_forward_return
    )


def test_research_store_persists_idempotently(tmp_path) -> None:
    evaluator = WalkForwardEvaluator(filing_store=FakeFilingStore())
    as_of = datetime(2025, 7, 1, tzinfo=IST)
    records = evaluator.evaluate(
        ["TEST"],
        [as_of],
        synthetic_prices(),
        benchmark_index="NIFTY 50",
        forward_days=30,
    )
    store = ResearchStore(tmp_path / "research.db")

    first_insert = store.save_records(records)
    second_insert = store.save_records(records)
    saved = store.list_snapshots(symbol="TEST")

    assert first_insert == 1
    assert second_insert == 1
    assert len(saved) == 1
    assert saved.loc[0, "symbol"] == "TEST"
    assert saved.loc[0, "benchmark_forward_return"] is not None
    assert saved.loc[0, "excess_forward_return"] is not None


def test_fiscal_quarter_end_dates_cover_indian_quarters() -> None:
    dates = fiscal_quarter_end_dates(
        __import__("datetime").date(2024, 4, 1),
        __import__("datetime").date(2025, 3, 31),
    )

    assert [value.date().isoformat() for value in dates] == [
        "2024-06-30",
        "2024-09-30",
        "2024-12-31",
        "2025-03-31",
    ]


def test_walkforward_portfolio_benchmark_is_reported() -> None:
    evaluator = WalkForwardEvaluator(filing_store=FakeFilingStore())
    as_of = datetime(2025, 7, 1, tzinfo=IST)
    records = evaluator.evaluate(
        ["TEST"],
        [as_of],
        synthetic_prices(),
        benchmark_index="NIFTY 50",
        forward_days=30,
        portfolio_symbols=["TEST", "PEER"],
    )

    assert records[0].portfolio_forward_return is not None
    assert records[0].excess_portfolio_forward_return is not None
    summary = walkforward_report(records)
    assert "portfolio_forward_return" in summary.columns


def test_walkforward_runs_multiple_as_of_dates() -> None:
    evaluator = WalkForwardEvaluator(filing_store=FakeFilingStore())
    records = evaluator.evaluate(
        ["TEST"],
        [
            datetime(2025, 1, 15, tzinfo=IST),
            datetime(2025, 7, 1, tzinfo=IST),
        ],
        synthetic_prices(),
        benchmark_index="NIFTY 50",
        forward_days=30,
    )

    assert len(records) == 2
    assert {record.as_of for record in records} == {
        datetime(2025, 1, 15, tzinfo=IST).isoformat(),
        datetime(2025, 7, 1, tzinfo=IST).isoformat(),
    }
