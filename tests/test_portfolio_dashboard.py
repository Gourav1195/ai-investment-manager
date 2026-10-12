from __future__ import annotations

from pathlib import Path

from src.investing.portfolio_dashboard_data import load_portfolio_summary, portfolio_has_data
from src.investing.portfolio_pricing import cache_navs, cache_stock_prices
from src.investing.portfolio_service import load_example_portfolio
from src.investing.portfolio_store import PortfolioStore


def test_portfolio_dashboard_loads_cached_summary(tmp_path) -> None:
    database = tmp_path / "portfolio.db"
    store = PortfolioStore(database)
    load_example_portfolio(store)
    cache_stock_prices(
        store,
        {"RELIANCE": 2600.0, "INFY": 1500.0, "HDFCBANK": 1700.0},
    )
    cache_navs(store, {"119063": 900.0, "122639": 80.0})

    assert portfolio_has_data(database)
    summary, comparison = load_portfolio_summary(database, refresh_prices=False)
    assert summary.totals["current_value"] is not None
    assert len(summary.equity) == 3
