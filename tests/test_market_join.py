from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

from src.investing.filings import IST
from src.investing.fundamentals import FundamentalSnapshot
from src.investing.market import MarketJoinError, MarketMetricsJoiner, snapshots_to_scorer_frame
from src.investing.scoring import LongTermScorer


def base_snapshot(**overrides) -> FundamentalSnapshot:
    values = {
        "symbol": "TEST",
        "entity_type": "non_bank",
        "as_of": "2025-07-01T23:59:59.999999+05:30",
        "period_end": "2025-03-31",
        "roe": 0.18,
        "roce": 0.22,
        "operating_margin": 0.16,
        "revenue_cagr_3y": 0.12,
        "earnings_cagr_3y": 0.14,
        "debt_to_equity": 0.30,
        "interest_coverage": 8.0,
        "free_cash_flow": 20_000_000.0,
        "latest_net_income": 10.0,
        "basic_eps": 1.0,
        "book_equity": 50.0,
    }
    values.update(overrides)
    return FundamentalSnapshot(**values)


def price_history() -> pd.DataFrame:
    dates = pd.bdate_range("2024-06-01", "2025-07-15")
    prices = pd.Series(100.0, index=dates)
    prices.iloc[-1] = 120.0
    prices.iloc[-40:] = prices.iloc[-40:].add(pd.Series(range(40), index=prices.index[-40:]))
    return pd.DataFrame(
        {
            "date": prices.index,
            "symbol": "TEST",
            "open": prices.values,
            "high": prices.values,
            "low": prices.values,
            "close": prices.values,
            "adj_close": prices.values,
            "volume": 1_000,
        }
    )


def test_market_joiner_uses_last_price_on_or_before_as_of() -> None:
    snapshot = base_snapshot()
    prices = price_history()
    as_of = datetime(2025, 7, 1, tzinfo=IST)

    enriched = MarketMetricsJoiner(min_volatility_observations=60).join(snapshot, prices)

    eligible = prices.loc[pd.to_datetime(prices["date"]).dt.date <= as_of.date()]
    expected_price = float(eligible.iloc[-1]["adj_close"])
    assert enriched.price == pytest.approx(expected_price)
    assert enriched.price_date == eligible.iloc[-1]["date"].date().isoformat()
    assert enriched.shares_outstanding == pytest.approx(10.0)
    assert enriched.pe == pytest.approx(expected_price / 1.0)
    assert enriched.pb == pytest.approx((expected_price * 10.0) / 50.0)
    assert enriched.free_cash_flow_yield == pytest.approx(
        20_000_000.0 / (expected_price * 10.0)
    )
    assert enriched.volatility_1y is not None
    assert enriched.market_join_version == 1


def test_market_joiner_ignores_future_prices() -> None:
    snapshot = base_snapshot(as_of="2025-01-15T23:59:59.999999+05:30")
    prices = price_history()

    enriched = MarketMetricsJoiner(min_volatility_observations=60).join(snapshot, prices)

    eligible = prices.loc[
        pd.to_datetime(prices["date"]).dt.date <= datetime(2025, 1, 15).date()
    ]
    assert enriched.price == pytest.approx(float(eligible.iloc[-1]["adj_close"]))


def test_market_joiner_leaves_pe_empty_for_non_positive_eps() -> None:
    snapshot = base_snapshot(basic_eps=-1.0, latest_net_income=-10.0)
    prices = price_history()

    enriched = MarketMetricsJoiner(min_volatility_observations=60).join(snapshot, prices)

    assert enriched.pe is None
    assert enriched.shares_outstanding == pytest.approx(10.0)
    assert enriched.pb is not None


def test_market_joiner_requires_symbol_prices() -> None:
    snapshot = base_snapshot(symbol="MISSING")
    prices = price_history()

    with pytest.raises(MarketJoinError, match="No price history"):
        MarketMetricsJoiner().join(snapshot, prices)


def test_enriched_snapshots_score_directly() -> None:
    snapshot = MarketMetricsJoiner(min_volatility_observations=60).join(
        base_snapshot(), price_history()
    )
    result = LongTermScorer().score(snapshots_to_scorer_frame([snapshot]))

    assert result.loc[0, "symbol"] == "TEST"
    assert result.loc[0, "research_view"] in {
        "Strong candidate",
        "Watchlist",
        "Caution",
        "Avoid",
    }
    assert result.loc[0, "data_coverage"] >= 0.60
