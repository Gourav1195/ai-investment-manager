"""Portfolio valuation, returns, benchmark comparison, and research linkage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable

import pandas as pd

from .portfolio_pricing import (
    AmfiNavProvider,
    YFinanceStockPriceProvider,
    cache_navs,
    cache_stock_prices,
)
from .portfolio_store import PortfolioStore
from .providers import YFinancePriceProvider, nifty_benchmark_symbol
from .research import ResearchStore


@dataclass(frozen=True)
class HoldingMetrics:
    asset_class: str
    identifier: str
    name: str
    quantity: float
    average_cost: float
    market_price: float | None
    invested: float
    current_value: float | None
    pnl: float | None
    pnl_pct: float | None
    allocation_pct: float | None
    research_view: str | None = None
    overall_score: float | None = None


@dataclass(frozen=True)
class PortfolioSummary:
    equity: pd.DataFrame
    mutual_funds: pd.DataFrame
    combined: pd.DataFrame
    totals: dict[str, float | None]
    absolute_return_pct: float | None
    xirr: float | None


def build_portfolio_summary(
    store: PortfolioStore,
    *,
    stock_prices: dict[str, float] | None = None,
    navs: dict[str, float] | None = None,
    research_store: ResearchStore | None = None,
) -> PortfolioSummary:
    equity = store.list_equity_holdings()
    mf = store.list_mf_holdings()
    stock_prices = stock_prices or {}
    navs = navs or {}
    research = _latest_research_by_symbol(research_store) if research_store else {}

    equity_rows: list[dict[str, object]] = []
    for record in equity.to_dict(orient="records"):
        symbol = str(record["symbol"])
        quantity = float(record["quantity"])
        avg = float(record["average_price"])
        price = stock_prices.get(symbol)
        invested = quantity * avg
        current = quantity * price if price is not None else None
        pnl = (current - invested) if current is not None else None
        pnl_pct = (pnl / invested) if pnl is not None and invested else None
        research_row = research.get(symbol, {})
        equity_rows.append(
            {
                "asset_class": "Equity",
                "identifier": symbol,
                "name": symbol,
                "quantity": quantity,
                "average_cost": avg,
                "market_price": price,
                "invested": invested,
                "current_value": current,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "research_view": research_row.get("research_view"),
                "overall_score": research_row.get("overall_score"),
            }
        )

    mf_rows: list[dict[str, object]] = []
    for record in mf.to_dict(orient="records"):
        scheme_code = str(record.get("scheme_code") or "")
        scheme_name = str(record["scheme_name"])
        units = float(record["units"])
        avg_nav = record.get("average_nav")
        avg_nav = float(avg_nav) if avg_nav is not None and not pd.isna(avg_nav) else None
        nav = navs.get(scheme_code) if scheme_code else None
        invested = units * avg_nav if avg_nav is not None else None
        current = units * nav if nav is not None else None
        pnl = (current - invested) if current is not None and invested is not None else None
        pnl_pct = (pnl / invested) if pnl is not None and invested else None
        mf_rows.append(
            {
                "asset_class": "Mutual Fund",
                "identifier": scheme_code or scheme_name,
                "name": scheme_name,
                "quantity": units,
                "average_cost": avg_nav,
                "market_price": nav,
                "invested": invested,
                "current_value": current,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "research_view": None,
                "overall_score": None,
            }
        )

    equity_frame = pd.DataFrame(equity_rows)
    mf_frame = pd.DataFrame(mf_rows)
    combined = pd.concat([equity_frame, mf_frame], ignore_index=True)
    total_invested = _sum_column(combined, "invested")
    total_current = _sum_column(combined, "current_value")
    if total_current is not None and total_invested:
        combined["allocation_pct"] = combined["current_value"].map(
            lambda value: (float(value) / total_current) if value is not None else None
        )
    else:
        combined["allocation_pct"] = None

    absolute_return_pct = None
    if total_current is not None and total_invested:
        absolute_return_pct = (total_current - total_invested) / total_invested

    trades = store.list_equity_trades()
    xirr = compute_portfolio_xirr(
        trades,
        equity_terminal_value=_sum_column(equity_frame, "current_value"),
        mf_terminal_value=_sum_column(mf_frame, "current_value"),
    )

    totals = {
        "invested": total_invested,
        "current_value": total_current,
        "pnl": (total_current - total_invested)
        if total_current is not None and total_invested is not None
        else None,
        "pnl_pct": absolute_return_pct,
    }
    return PortfolioSummary(
        equity=equity_frame,
        mutual_funds=mf_frame,
        combined=combined,
        totals=totals,
        absolute_return_pct=absolute_return_pct,
        xirr=xirr,
    )


def compute_portfolio_xirr(
    trades: pd.DataFrame,
    *,
    equity_terminal_value: float | None,
    mf_terminal_value: float | None,
    as_of: date | None = None,
) -> float | None:
    """Compute XIRR from tradebook cash flows plus terminal portfolio value."""

    as_of = as_of or date.today()
    flows: list[tuple[date, float]] = []
    if not trades.empty:
        for record in trades.to_dict(orient="records"):
            amount = float(record["quantity"]) * float(record["price"])
            signed = -amount if record["side"] == "buy" else amount
            flows.append((date.fromisoformat(str(record["trade_date"])), signed))

    terminal = 0.0
    if equity_terminal_value is not None:
        terminal += equity_terminal_value
    if mf_terminal_value is not None:
        terminal += mf_terminal_value
    if terminal > 0:
        flows.append((as_of, terminal))

    if len(flows) < 2:
        return None
    return xirr(flows)


def xirr(
    cashflows: Iterable[tuple[date, float]],
    *,
    guess: float = 0.12,
    tolerance: float = 1e-7,
    max_iterations: int = 100,
) -> float | None:
    """Newton-Raphson XIRR for irregular dated cash flows."""

    flows = sorted(cashflows, key=lambda item: item[0])
    if not flows:
        return None
    base = flows[0][0]
    amounts = [amount for _, amount in flows]
    if not any(amount < 0 for amount in amounts) or not any(amount > 0 for amount in amounts):
        return None

    def year_fraction(when: date) -> float:
        return (when - base).days / 365.0

    rate = guess
    for _ in range(max_iterations):
        npv = 0.0
        derivative = 0.0
        for when, amount in flows:
            years = year_fraction(when)
            discount = (1.0 + rate) ** years
            npv += amount / discount
            if years != 0:
                derivative -= years * amount / ((1.0 + rate) ** (years + 1))
        if abs(npv) < tolerance:
            return rate
        if derivative == 0:
            break
        rate -= npv / derivative
    return None


def benchmark_comparison_series(
    *,
    portfolio_values: pd.DataFrame,
    benchmark_index: str = "NIFTY 50",
    provider: YFinancePriceProvider | None = None,
) -> pd.DataFrame:
    """Compare normalized portfolio value series with a Nifty benchmark."""

    if portfolio_values.empty:
        return portfolio_values
    provider = provider or YFinancePriceProvider()
    symbol = nifty_benchmark_symbol(benchmark_index)
    start = portfolio_values["date"].min()
    end = portfolio_values["date"].max()
    bench = provider.fetch([symbol], str(start), str(end))
    if bench.empty:
        return portfolio_values
    bench = bench.sort_values("date")[["date", "adj_close"]].rename(
        columns={"adj_close": "benchmark"}
    )
    merged = portfolio_values.merge(bench, on="date", how="inner")
    if merged.empty:
        return merged
    first_portfolio = merged["portfolio_value"].iloc[0]
    first_benchmark = merged["benchmark"].iloc[0]
    merged["portfolio_indexed"] = merged["portfolio_value"] / first_portfolio
    merged["benchmark_indexed"] = merged["benchmark"] / first_benchmark
    return merged


def estimate_portfolio_history(
    store: PortfolioStore,
    trades: pd.DataFrame,
    *,
    stock_provider: YFinanceStockPriceProvider | None = None,
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    """Approximate daily portfolio value from trade history and price history."""

    if trades.empty:
        return pd.DataFrame(columns=["date", "portfolio_value"])
    stock_provider = stock_provider or YFinanceStockPriceProvider()
    symbols = sorted(trades["symbol"].unique().tolist())
    start_date = start or trades["trade_date"].min()
    end_date = end or date.today().isoformat()
    try:
        prices = stock_provider.history(symbols, str(start_date), end_date)
    except Exception:
        return pd.DataFrame(columns=["date", "portfolio_value"])
    if prices.empty:
        return pd.DataFrame(columns=["date", "portfolio_value"])

    dates = sorted(str(value) for value in prices["date"].unique())
    rows: list[dict[str, object]] = []
    for day in dates:
        holdings = _holdings_as_of(trades, day)
        value = 0.0
        day_prices = prices[prices["date"].astype(str) == day]
        for symbol, quantity in holdings.items():
            match = day_prices[day_prices["symbol"] == symbol]
            if match.empty:
                continue
            price = float(match.iloc[-1]["adj_close"])
            value += quantity * price
        rows.append({"date": day, "portfolio_value": value})
    return pd.DataFrame(rows)


def _holdings_as_of(trades: pd.DataFrame, as_of: str) -> dict[str, float]:
    subset = trades[trades["trade_date"] <= as_of]
    holdings: dict[str, float] = {}
    for record in subset.to_dict(orient="records"):
        symbol = str(record["symbol"])
        qty = float(record["quantity"])
        if record["side"] == "buy":
            holdings[symbol] = holdings.get(symbol, 0.0) + qty
        else:
            holdings[symbol] = holdings.get(symbol, 0.0) - qty
    return {symbol: qty for symbol, qty in holdings.items() if qty > 0}


def _latest_research_by_symbol(store: ResearchStore) -> dict[str, dict[str, object]]:
    snapshots = store.list_snapshots()
    if snapshots.empty:
        return {}
    snapshots = snapshots.sort_values(["symbol", "as_of"])
    latest = snapshots.groupby("symbol", as_index=False).tail(1)
    result: dict[str, dict[str, object]] = {}
    for record in latest.to_dict(orient="records"):
        result[str(record["symbol"])] = {
            "research_view": record.get("research_view"),
            "overall_score": record.get("overall_score"),
        }
    return result


def _sum_column(frame: pd.DataFrame, column: str) -> float | None:
    if frame.empty or column not in frame.columns:
        return None
    values = [float(value) for value in frame[column].tolist() if value is not None and not pd.isna(value)]
    return sum(values) if values else None


def refresh_market_data(
    store: PortfolioStore,
    *,
    stock_provider: YFinanceStockPriceProvider | None = None,
    nav_provider: AmfiNavProvider | None = None,
) -> tuple[dict[str, float], dict[str, float]]:
    stock_provider = stock_provider or YFinanceStockPriceProvider()
    nav_provider = nav_provider or AmfiNavProvider()
    equity = store.list_equity_holdings()
    mf = store.list_mf_holdings()
    stock_prices = stock_provider.latest_prices(equity["symbol"].tolist())
    scheme_codes = [
        str(code)
        for code in mf.get("scheme_code", pd.Series(dtype=str)).tolist()
        if code and str(code).strip()
    ]
    navs = nav_provider.latest_navs(scheme_codes)
    cache_stock_prices(store, stock_prices)
    cache_navs(store, navs)
    return stock_prices, navs
