"""Portfolio data helpers for the Streamlit dashboard."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .portfolio_analytics import (
    benchmark_comparison_series,
    build_portfolio_summary,
    estimate_portfolio_history,
    refresh_market_data,
)
from .mf_peer_comparison import PeerComparisonReport, compare_manual_funds, compare_portfolio_mutual_funds
from .mf_nav_client import MfNavClient
from .portfolio_store import PortfolioStore
from .research import ResearchStore


def portfolio_has_data(database: str | Path) -> bool:
    store = PortfolioStore(database)
    return not store.list_equity_holdings().empty or not store.list_mf_holdings().empty


def load_portfolio_summary(
    portfolio_database: str | Path,
    research_database: str | Path | None = None,
    *,
    refresh_prices: bool = True,
    benchmark_index: str = "NIFTY 50",
) -> tuple[object, pd.DataFrame | None]:
    store = PortfolioStore(portfolio_database)
    research_store = (
        ResearchStore(research_database)
        if research_database and Path(research_database).exists()
        else None
    )
    if refresh_prices:
        try:
            stock_prices, navs = refresh_market_data(store)
        except Exception:
            stock_prices = store.latest_price_cache()
            navs = store.latest_nav_cache()
    else:
        stock_prices = store.latest_price_cache()
        navs = store.latest_nav_cache()
    summary = build_portfolio_summary(
        store,
        stock_prices=stock_prices,
        navs=navs,
        research_store=research_store,
    )
    trades = store.list_equity_trades()
    history = estimate_portfolio_history(store, trades)
    comparison = None
    if not history.empty:
        try:
            comparison = benchmark_comparison_series(
                portfolio_values=history,
                benchmark_index=benchmark_index,
            )
        except Exception:
            comparison = None
    return summary, comparison


def format_holdings_table(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    display = frame.copy()
    for column in ("average_cost", "market_price", "invested", "current_value", "pnl"):
        if column in display.columns:
            display[column] = display[column].map(_money)
    if "pnl_pct" in display.columns:
        display["pnl_pct"] = display["pnl_pct"].map(_pct)
    if "allocation_pct" in display.columns:
        display["allocation_pct"] = display["allocation_pct"].map(_pct)
    return display


def _money(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    return f"₹{float(value):,.2f}"


def _pct(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    return f"{float(value) * 100:.2f}%"


def load_mf_peer_reports(
    portfolio_database: str | Path,
    *,
    sync_master: bool = False,
) -> list[PeerComparisonReport]:
    store = PortfolioStore(portfolio_database)
    client = MfNavClient(store)
    return compare_portfolio_mutual_funds(
        store,
        client=client,
        sync_master=sync_master,
    )


def load_manual_mf_comparison(
    portfolio_database: str | Path,
    scheme_codes: list[str],
) -> pd.DataFrame:
    store = PortfolioStore(portfolio_database)
    client = MfNavClient(store)
    return compare_manual_funds(store, scheme_codes, client=client)


def format_mf_returns_table(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    display = frame.copy()
    for column in ("cagr_1y", "cagr_3y", "cagr_5y", "rolling_1y_median", "category_avg_3y"):
        if column in display.columns:
            display[column] = display[column].map(_pct)
    if "percentile_3y" in display.columns:
        display["percentile_3y"] = display["percentile_3y"].map(
            lambda value: f"{float(value):.1f}" if value is not None and not pd.isna(value) else "—"
        )
    if "is_underperformer" in display.columns:
        display["is_underperformer"] = display["is_underperformer"].map(
            lambda value: "Yes" if value else "No"
        )
    return display


def list_mf_scheme_options(portfolio_database: str | Path) -> pd.DataFrame:
    return PortfolioStore(portfolio_database).list_scheme_master_options(limit=500)
