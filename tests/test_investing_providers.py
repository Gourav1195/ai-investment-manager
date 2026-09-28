from __future__ import annotations

import pandas as pd
import pytest
import requests

from src.investing.providers import (
    DataProviderError,
    NiftyIndexUniverseProvider,
    YFinancePriceProvider,
)


class FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        return None


class FakeSession:
    def __init__(self, text: str) -> None:
        self.text = text

    def get(self, url: str, *, timeout: float) -> FakeResponse:
        assert "nseindia.com" in url
        assert timeout == 20.0
        return FakeResponse(self.text)


class FlakySession(FakeSession):
    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.calls = 0

    def get(self, url: str, *, timeout: float) -> FakeResponse:
        self.calls += 1
        if self.calls == 1:
            raise requests.Timeout("temporary timeout")
        return super().get(url, timeout=timeout)


def test_nifty_provider_normalizes_and_deduplicates_symbols() -> None:
    provider = NiftyIndexUniverseProvider(
        session=FakeSession(
            "Company Name,Industry,Symbol\nA Ltd,IT, infy \nA Ltd,IT,INFY\nB Ltd,Bank,HDFCBANK\n"
        )
    )

    constituents = provider.fetch()

    assert constituents["symbol"].tolist() == ["INFY", "HDFCBANK"]
    assert "Symbol" not in constituents.columns


def test_nifty_provider_rejects_an_unexpected_file() -> None:
    provider = NiftyIndexUniverseProvider(session=FakeSession("Name,Code\nA,1\n"))

    with pytest.raises(DataProviderError, match="Symbol column"):
        provider.fetch()


def test_nifty_provider_retries_a_temporary_transport_failure() -> None:
    session = FlakySession("Company Name,Industry,Symbol\nA Ltd,IT,INFY\n")

    symbols = NiftyIndexUniverseProvider(session=session).symbols()

    assert symbols == ["INFY"]
    assert session.calls == 2


def test_yfinance_provider_normalizes_single_symbol_prices() -> None:
    index = pd.to_datetime(["2024-01-01", "2024-01-02"])
    raw = pd.DataFrame(
        {
            "Open": [100.0, 101.0],
            "High": [102.0, 103.0],
            "Low": [99.0, 100.0],
            "Close": [101.0, 102.0],
            "Adj Close": [100.5, 101.5],
            "Volume": [1000, 1200],
        },
        index=index,
    )
    calls: list[dict] = []

    def download(**kwargs):
        calls.append(kwargs)
        return raw

    prices = YFinancePriceProvider(download=download).fetch(
        ["reliance"], "2024-01-01", "2024-02-01"
    )

    assert calls[0]["tickers"] == ["RELIANCE.NS"]
    assert prices["symbol"].tolist() == ["RELIANCE", "RELIANCE"]
    assert prices["adj_close"].tolist() == [100.5, 101.5]
