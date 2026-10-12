"""Demo filing data and offline prices so research can run without NSE imports."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from .demo_filing_data import non_bank_history
from .filings import IST
from .providers import nifty_benchmark_symbol


class DemoFilingStore:
    """Synthetic canonical observations for walk-forward evaluation in the UI."""

    def canonical_observations_as_of(self, symbol: str, as_of: datetime) -> list[dict[str, Any]]:
        rows = [dict(row) for row in non_bank_history()]
        normalized = symbol.strip().upper()
        for row in rows:
            row["symbol"] = normalized
        return rows

    def filing_summaries(self, filing_keys: object) -> list[dict[str, object]]:
        return []


DEMO_SYMBOLS: tuple[str, ...] = (
    "RELIANCE",
    "INFY",
    "HDFCBANK",
    "ICICIBANK",
    "TCS",
    "BHARTIARTL",
    "ITC",
    "SBIN",
    "KOTAKBANK",
    "LT",
)


class StaticUniverseProvider:
    """Fixed symbol list when NSE index files are unavailable."""

    def __init__(self, symbols: list[str], *, label: str = "Demo universe") -> None:
        self._symbols = [s.strip().upper() for s in symbols if s.strip()]
        self.label = label

    def symbols(self, *, yahoo_suffix: bool = False) -> list[str]:
        if yahoo_suffix:
            return [f"{symbol}.NS" for symbol in self._symbols]
        return list(self._symbols)


def synthetic_prices_for_symbols(
    symbols: list[str],
    *,
    benchmark_index: str = "NIFTY 50",
    start: str = "2022-01-01",
    end: str = "2026-12-31",
) -> pd.DataFrame:
    """Build deterministic daily prices for UI runs when Yahoo Finance is unreachable."""

    dates = pd.bdate_range(start, end)
    frames: list[pd.DataFrame] = []
    benchmark = nifty_benchmark_symbol(benchmark_index)
    for index, symbol in enumerate(symbols):
        base = 100.0 + index * 12.5
        series = pd.Series(base, index=dates, dtype=float)
        ramp = pd.Series(range(len(dates)), index=dates, dtype=float) * (0.02 + index * 0.001)
        series = series + ramp
        frames.append(_price_frame(symbol, series))
    bench = pd.Series(1000.0, index=dates, dtype=float)
    bench = bench * (1.0003 ** pd.Series(range(len(dates)), index=dates))
    frames.append(_price_frame(benchmark, bench))
    return pd.concat(frames, ignore_index=True)


def _price_frame(symbol: str, close: pd.Series) -> pd.DataFrame:
    yahoo = symbol if symbol.startswith("^") else symbol
    return pd.DataFrame(
        {
            "date": close.index.strftime("%Y-%m-%d"),
            "symbol": yahoo.removesuffix(".NS"),
            "open": close.values,
            "high": close.values,
            "low": close.values,
            "close": close.values,
            "adj_close": close.values,
            "volume": 1_000,
        }
    )


def default_research_as_of() -> datetime:
    """Most recent Indian fiscal quarter-end before today (IST)."""

    now = datetime.now(tz=IST)
    month = now.month
    year = now.year
    if month >= 4:
        quarter_end_year = year if month >= 7 else year - 1
    else:
        quarter_end_year = year - 1
    # March, June, September, December quarter ends
    candidates = [
        datetime(quarter_end_year, 3, 31, 23, 59, 59, tzinfo=IST),
        datetime(quarter_end_year, 6, 30, 23, 59, 59, tzinfo=IST),
        datetime(quarter_end_year, 9, 30, 23, 59, 59, tzinfo=IST),
        datetime(quarter_end_year, 12, 31, 23, 59, 59, tzinfo=IST),
        datetime(quarter_end_year + 1, 3, 31, 23, 59, 59, tzinfo=IST),
    ]
    past = [dt for dt in candidates if dt <= now]
    return past[-1] if past else candidates[0]
