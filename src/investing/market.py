"""Point-in-time market metrics joined to fundamental snapshots.

Market prices and volatility use only observations available on or before the
evaluation timestamp. Valuation ratios are left empty when the required inputs
are missing or not meaningful, rather than silently substituting current prices
into a historical snapshot.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta
import math

import pandas as pd

from .fundamentals import FundamentalSnapshot

MARKET_JOIN_VERSION = 1
TRADING_DAYS_PER_YEAR = 252


class MarketJoinError(ValueError):
    """Raised when market inputs cannot be joined to a fundamental snapshot."""


class MarketMetricsJoiner:
    """Join point-in-time prices to accounting snapshots for valuation metrics."""

    def __init__(
        self,
        *,
        min_volatility_observations: int = 120,
        trading_days_per_year: int = TRADING_DAYS_PER_YEAR,
    ) -> None:
        if min_volatility_observations < 2:
            raise ValueError("min_volatility_observations must be at least 2")
        if trading_days_per_year < 1:
            raise ValueError("trading_days_per_year must be at least 1")
        self.min_volatility_observations = min_volatility_observations
        self.trading_days_per_year = trading_days_per_year

    def join(
        self,
        snapshot: FundamentalSnapshot,
        prices: pd.DataFrame,
    ) -> FundamentalSnapshot:
        """Return a snapshot enriched with point-in-time market metrics."""

        as_of = _parse_as_of(snapshot.as_of)
        symbol_prices = _symbol_prices(prices, snapshot.symbol)
        if symbol_prices.empty:
            raise MarketJoinError(
                f"No price history is available for {snapshot.symbol}"
            )

        price_date, price = _price_as_of(symbol_prices, as_of)
        volatility = _volatility_1y(
            symbol_prices,
            as_of,
            min_observations=self.min_volatility_observations,
            trading_days_per_year=self.trading_days_per_year,
        )
        shares = _shares_outstanding(snapshot.latest_net_income, snapshot.basic_eps)
        market_cap = (
            price * shares if price is not None and shares is not None else None
        )

        return replace(
            snapshot,
            price_date=price_date.isoformat() if price_date else None,
            price=price,
            shares_outstanding=shares,
            pe=_pe(price, snapshot.basic_eps),
            pb=_pb(market_cap, snapshot.book_equity),
            free_cash_flow_yield=_fcf_yield(snapshot.free_cash_flow, market_cap),
            volatility_1y=volatility,
            market_join_version=MARKET_JOIN_VERSION,
        )


def snapshots_to_scorer_frame(
    snapshots: list[FundamentalSnapshot],
) -> pd.DataFrame:
    """Convert enriched snapshots into the normalized input expected by the scorer."""

    if not snapshots:
        return pd.DataFrame()
    return pd.DataFrame([snapshot.to_scorer_row() for snapshot in snapshots])


def price_on_or_before(
    prices: pd.DataFrame, symbol: str, as_of: datetime
) -> tuple[date | None, float | None]:
    """Return the last adjusted close for ``symbol`` on or before ``as_of``."""

    frame = _symbol_prices(prices, symbol)
    if frame.empty:
        return None, None
    return _price_as_of(frame, as_of)


def total_return(
    prices: pd.DataFrame,
    symbol: str,
    start: datetime,
    end: datetime,
) -> float | None:
    """Return the compounded return between two point-in-time prices."""

    if end < start:
        return None
    _, start_price = price_on_or_before(prices, symbol, start)
    _, end_price = price_on_or_before(prices, symbol, end)
    if start_price is None or end_price is None or start_price <= 0:
        return None
    return_value = (end_price / start_price) - 1.0
    return return_value if math.isfinite(return_value) else None


def forward_return(
    prices: pd.DataFrame,
    symbol: str,
    as_of: datetime,
    *,
    forward_days: int,
) -> float | None:
    """Return the price change from ``as_of`` through the forward horizon."""

    if forward_days < 1:
        raise ValueError("forward_days must be at least 1")
    end = as_of + timedelta(days=forward_days)
    return total_return(prices, symbol, as_of, end)


def equal_weight_portfolio_forward_return(
    prices: pd.DataFrame,
    symbols: list[str],
    as_of: datetime,
    *,
    forward_days: int,
) -> float | None:
    """Return the equal-weight average forward return across ``symbols``."""

    if not symbols:
        return None
    returns = [
        value
        for symbol in symbols
        if (value := forward_return(prices, symbol, as_of, forward_days=forward_days))
        is not None
    ]
    if not returns:
        return None
    return float(sum(returns) / len(returns))


def _parse_as_of(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is not None:
        return parsed
    return parsed.replace(tzinfo=None)


def _symbol_prices(prices: pd.DataFrame, symbol: str) -> pd.DataFrame:
    required = {"date", "symbol", "adj_close"}
    missing = required - set(prices.columns)
    if missing:
        raise MarketJoinError(
            f"Price data must include columns: {', '.join(sorted(required))}"
        )

    normalized_symbol = symbol.strip().upper()
    frame = prices.copy()
    frame["symbol"] = frame["symbol"].astype("string").str.strip().str.upper()
    frame = frame.loc[frame["symbol"] == normalized_symbol]
    if frame.empty:
        return frame

    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame["adj_close"] = pd.to_numeric(frame["adj_close"], errors="coerce")
    frame = frame.loc[frame["date"].notna() & frame["adj_close"].notna()]
    return frame.sort_values("date", ignore_index=True)


def _as_of_date(as_of: datetime) -> date:
    return as_of.date()


def _eligible_prices(frame: pd.DataFrame, as_of: datetime) -> pd.DataFrame:
    cutoff = _as_of_date(as_of)
    return frame.loc[frame["date"].dt.date <= cutoff]


def _price_as_of(
    frame: pd.DataFrame, as_of: datetime
) -> tuple[date | None, float | None]:
    eligible = _eligible_prices(frame, as_of)
    if eligible.empty:
        return None, None
    row = eligible.iloc[-1]
    return row["date"].date(), float(row["adj_close"])


def _volatility_1y(
    frame: pd.DataFrame,
    as_of: datetime,
    *,
    min_observations: int,
    trading_days_per_year: int,
) -> float | None:
    eligible = _eligible_prices(frame, as_of)
    if eligible.empty:
        return None
    window = eligible.tail(trading_days_per_year)
    if len(window) < min_observations:
        return None
    returns = window["adj_close"].pct_change().dropna()
    if returns.empty:
        return None
    volatility = float(returns.std(ddof=1) * math.sqrt(trading_days_per_year))
    if not math.isfinite(volatility):
        return None
    return volatility


def _shares_outstanding(
    net_income: float | None, basic_eps: float | None
) -> float | None:
    if net_income is None or basic_eps is None or basic_eps == 0:
        return None
    shares = net_income / basic_eps
    if not math.isfinite(shares) or shares <= 0:
        return None
    return shares


def _pe(price: float | None, basic_eps: float | None) -> float | None:
    if price is None or basic_eps is None or basic_eps <= 0 or price <= 0:
        return None
    ratio = price / basic_eps
    return ratio if math.isfinite(ratio) and ratio > 0 else None


def _pb(market_cap: float | None, book_equity: float | None) -> float | None:
    if market_cap is None or book_equity is None or book_equity <= 0:
        return None
    ratio = market_cap / book_equity
    return ratio if math.isfinite(ratio) and ratio > 0 else None


def _fcf_yield(free_cash_flow: float | None, market_cap: float | None) -> float | None:
    if free_cash_flow is None or market_cap is None or market_cap <= 0:
        return None
    yield_value = free_cash_flow / market_cap
    return yield_value if math.isfinite(yield_value) else None
