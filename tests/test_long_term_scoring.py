from __future__ import annotations

import pandas as pd
import pytest

from src.investing.scoring import LongTermScorer


def test_strong_company_ranks_ahead_of_weak_company() -> None:
    fundamentals = pd.DataFrame(
        [
            {
                "symbol": "STRONG",
                "roe": 0.24,
                "roce": 0.28,
                "operating_margin": 0.24,
                "revenue_cagr_3y": 0.18,
                "earnings_cagr_3y": 0.22,
                "debt_to_equity": 0.10,
                "interest_coverage": 15.0,
                "pe": 18.0,
                "pb": 2.0,
                "free_cash_flow_yield": 0.07,
                "volatility_1y": 0.18,
            },
            {
                "symbol": "WEAK",
                "roe": 0.02,
                "roce": 0.03,
                "operating_margin": 0.06,
                "revenue_cagr_3y": -0.03,
                "earnings_cagr_3y": -0.08,
                "debt_to_equity": 1.80,
                "interest_coverage": 1.20,
                "pe": 45.0,
                "pb": 7.0,
                "free_cash_flow_yield": -0.01,
                "volatility_1y": 0.55,
            },
        ]
    )

    result = LongTermScorer().score(fundamentals)

    assert result["symbol"].tolist() == ["STRONG", "WEAK"]
    assert result.loc[0, "research_view"] == "Strong candidate"
    assert result.loc[1, "research_view"] == "Avoid"
    assert result["rank"].tolist() == [1, 2]


def test_incomplete_company_is_not_ranked() -> None:
    result = LongTermScorer().score(pd.DataFrame([{"symbol": "PARTIAL", "roe": 0.20}]))

    assert result.loc[0, "research_view"] == "Insufficient data"
    assert pd.isna(result.loc[0, "rank"])


def test_duplicate_symbols_are_rejected() -> None:
    fundamentals = pd.DataFrame([{"symbol": "INFY"}, {"symbol": " infy "}])

    with pytest.raises(ValueError, match="duplicate symbols"):
        LongTermScorer().score(fundamentals)
