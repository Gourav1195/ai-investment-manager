from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

from src.investing.market import (
    equal_weight_portfolio_forward_return,
    forward_return,
    total_return,
)
from src.investing.providers import nifty_benchmark_symbol


def price_frame() -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-01", "2024-12-31")
    prices = pd.Series([100.0, 110.0, 121.0], index=dates[:3])
    return pd.DataFrame(
        {
            "date": prices.index,
            "symbol": "TEST",
            "adj_close": prices.values,
        }
    )


def test_total_return_uses_point_in_time_prices() -> None:
    prices = price_frame()
    start = datetime(2024, 1, 2)
    end = datetime(2024, 1, 4)

    assert total_return(prices, "TEST", start, end) == pytest.approx(0.10)


def test_forward_return_uses_forward_horizon() -> None:
    prices = price_frame()
    as_of = datetime(2024, 1, 2)

    assert forward_return(prices, "TEST", as_of, forward_days=2) == pytest.approx(0.10)


def test_equal_weight_portfolio_forward_return_averages_symbols() -> None:
    prices = price_frame()
    as_of = datetime(2024, 1, 2)

    assert equal_weight_portfolio_forward_return(
        prices, ["TEST", "MISSING"], as_of, forward_days=2
    ) == pytest.approx(0.10)


def test_nifty_benchmark_symbol_mapping() -> None:
    assert nifty_benchmark_symbol("nifty 50") == "^NSEI"
    assert nifty_benchmark_symbol("NIFTY 200") == "^CNX200"

    with pytest.raises(ValueError, match="Unsupported benchmark"):
        nifty_benchmark_symbol("NIFTY 500")
