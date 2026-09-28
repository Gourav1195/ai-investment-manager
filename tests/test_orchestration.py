from __future__ import annotations

from datetime import datetime

import pandas as pd

from src.investing.filings import IST
from src.investing.orchestration import (
    OrchestrationStore,
    UniverseResearchOrchestrator,
    UniverseRunResult,
    resolve_orchestration_dates,
)
from tests.test_walkforward import FakeFilingStore, synthetic_prices


class SelectiveFilingStore(FakeFilingStore):
    def canonical_observations_as_of(self, symbol, as_of):
        if symbol.strip().upper() == "MISSING":
            return []
        return super().canonical_observations_as_of(symbol, as_of)


class FakeUniverseProvider:
    index_name = "NIFTY 50"

    def symbols(self) -> list[str]:
        return ["TEST", "MISSING"]


class FakePriceProvider:
    def fetch(self, symbols, start, end) -> pd.DataFrame:
        return synthetic_prices()


def test_resolve_orchestration_dates_from_quarter_range() -> None:
    dates = resolve_orchestration_dates(
        quarter_range_start="2024-04-01",
        quarter_range_end="2025-03-31",
    )

    assert len(dates) == 4
    assert dates[0].date().isoformat() == "2024-06-30"


def test_orchestration_store_persists_run_summary(tmp_path) -> None:
    store = OrchestrationStore(tmp_path / "research.db")
    result = UniverseRunResult(
        run_key="abc",
        index_name="NIFTY 50",
        as_of_dates=("2024-06-30T18:29:59.999999+05:30",),
        symbols_requested=2,
        symbols_evaluated=1,
        records_persisted=1,
        skipped_symbols=(("MISSING", "no data"),),
        archive_status="skipped",
    )
    store.save_run(result, benchmark_index="NIFTY 50", forward_days=30)

    runs = store.list_runs()

    assert len(runs) == 1
    assert runs.iloc[0]["symbols_evaluated"] == 1
    assert runs.iloc[0]["records_persisted"] == 1


def test_universe_orchestrator_skips_missing_symbols(tmp_path) -> None:
    orchestrator = UniverseResearchOrchestrator(
        database=tmp_path / "research.db",
        universe_provider=FakeUniverseProvider(),
        price_provider=FakePriceProvider(),
        filing_store=SelectiveFilingStore(),
    )
    as_of = datetime(2025, 7, 1, tzinfo=IST)

    result = orchestrator.run(
        as_of_dates=[as_of],
        prices_start="2024-01-01",
        prices_end="2026-01-01",
        persist=True,
        benchmark_portfolio=False,
        use_historical_constituents=False,
    )

    assert result.symbols_requested == 2
    assert result.symbols_evaluated == 1
    assert result.records_persisted == 1
    assert len(result.skipped_symbols) == 1
    assert result.skipped_symbols[0][0] == "MISSING"
