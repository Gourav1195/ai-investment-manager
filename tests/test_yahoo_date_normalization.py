from __future__ import annotations

import pandas as pd

from src.investing.portfolio_analytics import benchmark_comparison_series
from src.investing.providers import YFinancePriceProvider, _yahoo_date_only


def test_yahoo_date_only_strips_time() -> None:
    assert _yahoo_date_only("2024-01-15 00:00:00") == "2024-01-15"
    assert _yahoo_date_only("2024-01-15T12:30:00") == "2024-01-15"


def test_benchmark_comparison_accepts_timestamp_portfolio_dates() -> None:
    history = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-02-01"]),
            "portfolio_value": [100.0, 105.0],
        }
    )
    result = benchmark_comparison_series(portfolio_values=history)
    assert not result.empty
    assert "benchmark_indexed" in result.columns
