from __future__ import annotations

from datetime import date, datetime

import pytest

from src.investing.constituents import (
    ConstituentHistoryStore,
    archive_current_constituents,
    constituent_coverage,
    import_snapshots_csv,
    latest_fiscal_quarter_end,
    resolve_portfolio_symbols,
)
from src.investing.filings import IST
from src.investing.research import WalkForwardEvaluator
from tests.test_walkforward import FakeFilingStore, synthetic_prices


def test_constituent_store_returns_latest_membership_on_or_before_as_of(
    tmp_path,
) -> None:
    store = ConstituentHistoryStore(tmp_path / "research.db")
    store.record_snapshot(
        "NIFTY 50",
        ["AAA", "BBB"],
        effective_date=date(2024, 3, 31),
        source="test",
    )
    store.record_snapshot(
        "NIFTY 50",
        ["AAA", "CCC"],
        effective_date=date(2024, 6, 30),
        source="test",
    )

    members = store.members_as_of("NIFTY 50", date(2024, 5, 31))

    assert members == ["AAA", "BBB"]


def test_resolve_portfolio_symbols_prefers_historical_membership(tmp_path) -> None:
    store = ConstituentHistoryStore(tmp_path / "research.db")
    store.record_snapshot(
        "NIFTY 50",
        ["HIST"],
        effective_date=date(2024, 3, 31),
        source="test",
    )

    symbols, source = resolve_portfolio_symbols(
        benchmark_index="NIFTY 50",
        as_of=date(2024, 5, 31),
        store=store,
        use_historical=True,
        fallback_symbols=["CURRENT"],
    )

    assert symbols == ["HIST"]
    assert source == "historical_constituents"


def test_walkforward_uses_historical_portfolio_per_as_of_date(tmp_path) -> None:
    store = ConstituentHistoryStore(tmp_path / "research.db")
    store.record_snapshot(
        "NIFTY 50",
        ["TEST"],
        effective_date=date(2024, 3, 31),
        source="test",
    )
    store.record_snapshot(
        "NIFTY 50",
        ["MISSING"],
        effective_date=date(2025, 3, 31),
        source="test",
    )

    evaluator = WalkForwardEvaluator(filing_store=FakeFilingStore())
    as_of_old = datetime(2024, 6, 30, tzinfo=IST)
    as_of_new = datetime(2025, 6, 30, tzinfo=IST)
    records = evaluator.evaluate(
        ["TEST"],
        [as_of_old, as_of_new],
        synthetic_prices(),
        benchmark_index="NIFTY 50",
        forward_days=30,
        portfolio_symbols=["FALLBACK"],
        constituent_store=store,
        use_historical_constituents=True,
    )

    by_as_of = {record.as_of: record for record in records}
    assert by_as_of[as_of_old.isoformat()].portfolio_symbols == ("TEST",)
    assert by_as_of[as_of_new.isoformat()].portfolio_symbols == ("MISSING",)


class FakeUniverseProvider:
    def __init__(self, index_name: str, symbols: list[str]) -> None:
        self.index_name = index_name
        self._symbols = symbols

    def fetch(self):
        import pandas as pd

        return pd.DataFrame({"symbol": self._symbols})


def test_archive_current_constituents_skips_existing_snapshot(tmp_path) -> None:
    store = ConstituentHistoryStore(tmp_path / "research.db")
    effective = latest_fiscal_quarter_end(date(2024, 7, 1))
    provider = FakeUniverseProvider("NIFTY 50", ["AAA", "BBB"])

    first = archive_current_constituents(store, provider, effective_date=effective)
    second = archive_current_constituents(store, provider, effective_date=effective)

    assert first[0].status == "recorded"
    assert second[0].status == "skipped"
    assert store.members_as_of("NIFTY 50", effective) == ["AAA", "BBB"]


def test_import_snapshots_csv_records_multiple_dates(tmp_path) -> None:
    csv_path = tmp_path / "constituents.csv"
    csv_path.write_text(
        "effective_date,symbol\n"
        "2024-03-31,AAA\n"
        "2024-03-31,BBB\n"
        "2024-06-30,AAA\n"
        "2024-06-30,CCC\n",
        encoding="utf-8",
    )
    store = ConstituentHistoryStore(tmp_path / "research.db")

    imported = import_snapshots_csv(
        store, csv_path, index_name="NIFTY 50", source="test_csv"
    )

    assert imported == 2
    assert store.members_as_of("NIFTY 50", date(2024, 5, 31)) == ["AAA", "BBB"]
    assert store.members_as_of("NIFTY 50", date(2024, 7, 1)) == ["AAA", "CCC"]


def test_constituent_coverage_reports_missing_dates(tmp_path) -> None:
    store = ConstituentHistoryStore(tmp_path / "research.db")
    store.record_snapshot(
        "NIFTY 50",
        ["AAA"],
        effective_date=date(2024, 3, 31),
        source="test",
    )

    report = constituent_coverage(
        store,
        "NIFTY 50",
        [date(2024, 5, 31), date(2023, 3, 31)],
    )

    assert report.loc[0, "has_snapshot"]
    assert not report.loc[1, "has_snapshot"]


def test_record_snapshot_rejects_blank_symbols(tmp_path) -> None:
    store = ConstituentHistoryStore(tmp_path / "research.db")
    with pytest.raises(ValueError, match="blank"):
        store.record_snapshot(
            "NIFTY 50",
            ["", "INFY"],
            effective_date=date(2024, 3, 31),
            source="test",
        )
