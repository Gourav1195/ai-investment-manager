"""Market prices and mutual fund NAV fetchers for portfolio tracking."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from io import StringIO
from typing import Iterable, Protocol

import pandas as pd
import requests

from .portfolio_store import PortfolioStore
from .providers import YFinancePriceProvider

AMFI_NAV_ALL_URL = "https://www.amfiindia.com/spages/NAVAll.txt"
AMFI_NAV_HISTORY_URL = "https://portal.amfiindia.com/NAVHistoryReport_Po.aspx"


class StockPriceProvider(Protocol):
    def latest_prices(self, symbols: Iterable[str]) -> dict[str, float]: ...


class NavProvider(Protocol):
    def latest_navs(self, scheme_codes: Iterable[str]) -> dict[str, float]: ...


class YFinanceStockPriceProvider:
    """Fetch latest NSE equity prices via yfinance (.NS suffix)."""

    def __init__(self, provider: YFinancePriceProvider | None = None) -> None:
        self._provider = provider or YFinancePriceProvider()

    def latest_prices(self, symbols: Iterable[str]) -> dict[str, float]:
        symbols = [symbol.strip().upper() for symbol in symbols if str(symbol).strip()]
        if not symbols:
            return {}
        end = date.today()
        start = end - timedelta(days=14)
        frame = self._provider.fetch(
            symbols,
            start.isoformat(),
            end.isoformat(),
        )
        prices: dict[str, float] = {}
        for symbol in symbols:
            subset = frame[frame["symbol"] == symbol]
            if subset.empty:
                continue
            latest = subset.sort_values("date").iloc[-1]
            price = latest.get("adj_close", latest.get("close"))
            if price is not None and not pd.isna(price):
                prices[symbol] = float(price)
        return prices

    def history(
        self,
        symbols: Iterable[str],
        start: str,
        end: str,
    ) -> pd.DataFrame:
        return self._provider.fetch(list(symbols), start, end)


class AmfiNavProvider:
    """Fetch mutual fund NAVs from AMFI public data."""

    def __init__(self, session: requests.Session | None = None) -> None:
        self._session = session or requests.Session()

    def latest_navs(self, scheme_codes: Iterable[str]) -> dict[str, float]:
        codes = {str(code).strip() for code in scheme_codes if str(code).strip()}
        if not codes:
            return {}
        text = self._session.get(AMFI_NAV_ALL_URL, timeout=60).text
        table = self._parse_nav_all(text)
        result: dict[str, float] = {}
        for code in codes:
            matches = table[table["scheme_code"] == code]
            if matches.empty:
                continue
            result[code] = float(matches.iloc[-1]["nav"])
        return result

    def _parse_nav_all(self, text: str) -> pd.DataFrame:
        rows: list[dict[str, str | float]] = []
        for line in text.splitlines():
            if ";" not in line:
                continue
            parts = [part.strip() for part in line.split(";")]
            if len(parts) < 5:
                continue
            scheme_code = parts[0]
            if not scheme_code.isdigit():
                continue
            try:
                nav = float(parts[4].replace(",", ""))
            except ValueError:
                continue
            rows.append({"scheme_code": scheme_code, "nav": nav})
        return pd.DataFrame(rows)


def cache_stock_prices(
    store: PortfolioStore,
    prices: dict[str, float],
    *,
    price_date: str | None = None,
) -> None:
    as_of = price_date or date.today().isoformat()
    with store._connect() as connection:
        for symbol, price in prices.items():
            connection.execute(
                """
                INSERT OR REPLACE INTO price_cache (symbol, price_date, price)
                VALUES (?, ?, ?)
                """,
                (symbol.upper(), as_of, float(price)),
            )


def cache_navs(
    store: PortfolioStore,
    navs: dict[str, float],
    *,
    nav_date: str | None = None,
) -> None:
    as_of = nav_date or date.today().isoformat()
    with store._connect() as connection:
        for scheme_code, nav in navs.items():
            connection.execute(
                """
                INSERT OR REPLACE INTO nav_cache (scheme_code, nav_date, nav)
                VALUES (?, ?, ?)
                """,
                (str(scheme_code), as_of, float(nav)),
            )
