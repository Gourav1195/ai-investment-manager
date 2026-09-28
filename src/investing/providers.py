"""Replaceable market-data providers for Indian equity research.

The providers in this module perform data acquisition only. They do not expose
order placement or brokerage operations.
"""

from __future__ import annotations

from io import StringIO
from typing import Callable, Iterable, Protocol

import pandas as pd
import requests


class DataProviderError(RuntimeError):
    """Raised when a provider cannot return valid normalized data."""


class HttpResponse(Protocol):
    text: str

    def raise_for_status(self) -> None: ...


class HttpSession(Protocol):
    def get(self, url: str, *, timeout: float) -> HttpResponse: ...


NIFTY_BENCHMARK_SYMBOLS = {
    "NIFTY 50": "^NSEI",
    "NIFTY 100": "^CNX100",
    "NIFTY 200": "^CNX200",
}


def nifty_benchmark_symbol(index_name: str) -> str:
    """Return the Yahoo Finance ticker for an official Nifty benchmark index."""

    normalized_name = index_name.strip().upper()
    if normalized_name not in NIFTY_BENCHMARK_SYMBOLS:
        supported = ", ".join(NIFTY_BENCHMARK_SYMBOLS)
        raise ValueError(
            f"Unsupported benchmark index '{index_name}'. Choose one of: {supported}"
        )
    return NIFTY_BENCHMARK_SYMBOLS[normalized_name]


class NiftyIndexUniverseProvider:
    """Load current constituents from official NSE index archive files."""

    INDEX_URLS = {
        "NIFTY 50": (
            "https://nsearchives.nseindia.com/content/indices/ind_nifty50list.csv",
            "https://www.niftyindices.com/IndexConstituent/ind_nifty50list.csv",
        ),
        "NIFTY 100": (
            "https://nsearchives.nseindia.com/content/indices/ind_nifty100list.csv",
            "https://www.niftyindices.com/IndexConstituent/ind_nifty100list.csv",
        ),
        "NIFTY 200": (
            "https://nsearchives.nseindia.com/content/indices/ind_nifty200list.csv",
            "https://www.niftyindices.com/IndexConstituent/ind_nifty200list.csv",
        ),
    }

    def __init__(
        self,
        index_name: str = "NIFTY 50",
        *,
        session: HttpSession | None = None,
        timeout: float = 20.0,
    ) -> None:
        normalized_name = index_name.strip().upper()
        if normalized_name not in self.INDEX_URLS:
            supported = ", ".join(self.INDEX_URLS)
            raise ValueError(
                f"Unsupported index '{index_name}'. Choose one of: {supported}"
            )
        self.index_name = normalized_name
        if session is None:
            real_session = requests.Session()
            real_session.headers.update(
                {
                    "Accept": "text/csv,*/*",
                    "User-Agent": "Mozilla/5.0 (compatible; AIInvestmentResearch/0.1)",
                }
            )
            session = real_session
        self.session = session
        self.timeout = timeout

    def fetch(self) -> pd.DataFrame:
        """Return the official constituent table with normalized NSE symbols."""

        last_error: Exception | None = None
        constituents: pd.DataFrame | None = None
        for url in self.INDEX_URLS[self.index_name]:
            for _attempt in range(2):
                try:
                    response = self.session.get(url, timeout=self.timeout)
                    response.raise_for_status()
                    constituents = pd.read_csv(StringIO(response.text))
                    break
                except (
                    requests.RequestException,
                    pd.errors.ParserError,
                    UnicodeError,
                ) as exc:
                    last_error = exc
            if constituents is not None:
                break
        if constituents is None:
            raise DataProviderError(
                f"Could not load {self.index_name} constituents from official sources: {last_error}"
            ) from last_error

        symbol_column = next(
            (
                column
                for column in constituents.columns
                if column.strip().lower() == "symbol"
            ),
            None,
        )
        if symbol_column is None:
            raise DataProviderError(
                "NSE constituent file does not contain a Symbol column"
            )

        constituents = constituents.copy()
        constituents["symbol"] = (
            constituents[symbol_column].astype("string").str.strip().str.upper()
        )
        if symbol_column != "symbol":
            constituents = constituents.drop(columns=symbol_column)
        constituents = constituents.loc[
            constituents["symbol"].notna() & constituents["symbol"].ne("")
        ].drop_duplicates(subset="symbol")
        if constituents.empty:
            raise DataProviderError(
                "NSE constituent file did not contain any valid symbols"
            )
        return constituents.reset_index(drop=True)

    def symbols(self, *, yahoo_suffix: bool = False) -> list[str]:
        """Return NSE symbols, optionally formatted for Yahoo Finance."""

        symbols = self.fetch()["symbol"].tolist()
        if yahoo_suffix:
            return [f"{symbol}.NS" for symbol in symbols]
        return symbols


DownloadFunction = Callable[..., pd.DataFrame]


class YFinancePriceProvider:
    """Fetch adjusted daily prices from yfinance for personal research."""

    def __init__(self, download: DownloadFunction | None = None) -> None:
        if download is None:
            import yfinance as yf

            download = yf.download
        self._download = download

    def fetch(self, symbols: Iterable[str], start: str, end: str) -> pd.DataFrame:
        """Return normalized long-form daily OHLCV data.

        Symbols without an exchange suffix are treated as NSE equities and get
        the ``.NS`` suffix used by Yahoo Finance.
        """

        requested = [self._as_yahoo_symbol(symbol) for symbol in symbols]
        requested = list(dict.fromkeys(requested))
        if not requested:
            raise ValueError("At least one symbol is required")

        try:
            raw = self._download(
                tickers=requested,
                start=start,
                end=end,
                auto_adjust=False,
                actions=False,
                progress=False,
                group_by="ticker",
                threads=True,
            )
        except Exception as exc:  # yfinance can surface several transport exceptions
            raise DataProviderError(
                f"Yahoo Finance price request failed: {exc}"
            ) from exc

        if raw is None or raw.empty:
            raise DataProviderError("Yahoo Finance returned no price data")

        frames: list[pd.DataFrame] = []
        if isinstance(raw.columns, pd.MultiIndex):
            level_zero = {str(value) for value in raw.columns.get_level_values(0)}
            level_one = {str(value) for value in raw.columns.get_level_values(1)}
            for symbol in requested:
                if symbol in level_zero:
                    symbol_frame = raw.xs(symbol, axis=1, level=0, drop_level=True)
                elif symbol in level_one:
                    symbol_frame = raw.xs(symbol, axis=1, level=1, drop_level=True)
                else:
                    continue
                frames.append(self._normalize_symbol_frame(symbol, symbol_frame))
        elif len(requested) == 1:
            frames.append(self._normalize_symbol_frame(requested[0], raw))
        else:
            raise DataProviderError(
                "Unexpected Yahoo Finance response for multiple symbols"
            )

        frames = [frame for frame in frames if not frame.empty]
        if not frames:
            raise DataProviderError("No requested symbol had usable price data")
        return pd.concat(frames, ignore_index=True).sort_values(
            ["date", "symbol"], ignore_index=True
        )

    @staticmethod
    def _as_yahoo_symbol(symbol: str) -> str:
        normalized = symbol.strip().upper()
        if not normalized:
            raise ValueError("Symbols cannot be blank")
        if normalized.startswith("^"):
            return normalized
        if "." not in normalized:
            normalized = f"{normalized}.NS"
        return normalized

    @staticmethod
    def _normalize_symbol_frame(symbol: str, frame: pd.DataFrame) -> pd.DataFrame:
        normalized = frame.copy()
        normalized.columns = [
            str(column).strip().lower().replace(" ", "_")
            for column in normalized.columns
        ]
        normalized.index = pd.to_datetime(normalized.index, errors="coerce")
        normalized.index.name = "date"
        normalized = normalized.reset_index()
        normalized = normalized.loc[normalized["date"].notna()]
        if "close" not in normalized:
            return pd.DataFrame()
        if "adj_close" not in normalized:
            normalized["adj_close"] = normalized["close"]
        normalized["symbol"] = symbol.removesuffix(".NS").removesuffix(".BO")

        output_columns = [
            "date",
            "symbol",
            "open",
            "high",
            "low",
            "close",
            "adj_close",
            "volume",
        ]
        for column in output_columns:
            if column not in normalized:
                normalized[column] = pd.NA
        return normalized.loc[normalized["close"].notna(), output_columns]
