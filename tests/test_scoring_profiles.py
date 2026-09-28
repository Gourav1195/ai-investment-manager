from __future__ import annotations

import pandas as pd

from src.investing.scoring import LongTermScorer
from src.investing.scoring_profiles import metrics_for


def test_bank_profile_uses_prudential_metrics() -> None:
    columns = {metric.column for metric in metrics_for("bank")}
    assert "gross_npa_ratio" in columns
    assert "cet1_ratio" in columns
    assert "roce" not in columns


def test_bank_scores_use_industry_thresholds() -> None:
    fundamentals = pd.DataFrame(
        [
            {
                "symbol": "STRONG_BANK",
                "entity_type": "bank",
                "roe": 0.17,
                "return_on_assets": 0.014,
                "operating_margin": 0.40,
                "revenue_cagr_3y": 0.12,
                "earnings_cagr_3y": 0.15,
                "gross_npa_ratio": 1.2,
                "cet1_ratio": 15.0,
                "pe": 14.0,
                "pb": 1.5,
                "volatility_1y": 0.20,
            },
            {
                "symbol": "WEAK_BANK",
                "entity_type": "bank",
                "roe": 0.05,
                "return_on_assets": 0.004,
                "operating_margin": 0.18,
                "revenue_cagr_3y": -0.05,
                "earnings_cagr_3y": -0.10,
                "gross_npa_ratio": 6.0,
                "cet1_ratio": 7.0,
                "pe": 28.0,
                "pb": 2.8,
                "volatility_1y": 0.48,
            },
        ]
    )

    result = LongTermScorer().score(fundamentals)

    assert result["symbol"].tolist() == ["STRONG_BANK", "WEAK_BANK"]
    assert result.loc[0, "overall_score"] > result.loc[1, "overall_score"]


def test_missing_entity_type_defaults_to_non_bank_profile() -> None:
    assert metrics_for(None) == metrics_for("non_bank")


def test_insurance_profile_uses_premium_and_solvency_metrics() -> None:
    columns = {metric.column for metric in metrics_for("insurance")}
    assert "profit_margin" in columns
    assert "investment_income_ratio" in columns
    assert "equity_to_assets" in columns
    assert "roce" not in columns


def test_insurance_scores_use_industry_thresholds() -> None:
    fundamentals = pd.DataFrame(
        [
            {
                "symbol": "STRONG_INS",
                "entity_type": "insurance",
                "roe": 0.17,
                "return_on_assets": 0.011,
                "profit_margin": 0.10,
                "investment_income_ratio": 0.22,
                "revenue_cagr_3y": 0.12,
                "earnings_cagr_3y": 0.15,
                "equity_to_assets": 0.16,
                "pe": 14.0,
                "pb": 1.5,
                "volatility_1y": 0.20,
            },
            {
                "symbol": "WEAK_INS",
                "entity_type": "insurance",
                "roe": 0.05,
                "return_on_assets": 0.002,
                "profit_margin": 0.01,
                "investment_income_ratio": 0.05,
                "revenue_cagr_3y": -0.05,
                "earnings_cagr_3y": -0.10,
                "equity_to_assets": 0.04,
                "pe": 32.0,
                "pb": 3.5,
                "volatility_1y": 0.48,
            },
        ]
    )

    result = LongTermScorer().score(fundamentals)

    assert result["symbol"].tolist() == ["STRONG_INS", "WEAK_INS"]
    assert result.loc[0, "overall_score"] > result.loc[1, "overall_score"]
