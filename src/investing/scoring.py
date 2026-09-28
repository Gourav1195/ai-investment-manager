"""Transparent long-term equity scoring.

This module deliberately uses deterministic, documented factor transforms.
Language models may explain these results later, but they do not calculate or
override the scores.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

Direction = Literal["higher", "lower"]


@dataclass(frozen=True)
class Metric:
    column: str
    category: str
    direction: Direction
    poor: float
    strong: float


class LongTermScorer:
    """Rank companies using quality, growth, resilience, and valuation factors."""

    CATEGORY_WEIGHTS = {
        "quality": 0.30,
        "growth": 0.25,
        "financial_strength": 0.20,
        "valuation": 0.20,
        "price_discipline": 0.05,
    }

    METRICS = (
        Metric("roe", "quality", "higher", 0.00, 0.25),
        Metric("roce", "quality", "higher", 0.00, 0.30),
        Metric("operating_margin", "quality", "higher", 0.05, 0.25),
        Metric("revenue_cagr_3y", "growth", "higher", -0.05, 0.20),
        Metric("earnings_cagr_3y", "growth", "higher", -0.10, 0.25),
        Metric("debt_to_equity", "financial_strength", "lower", 2.00, 0.00),
        Metric("interest_coverage", "financial_strength", "higher", 1.00, 10.00),
        Metric("pe", "valuation", "lower", 50.00, 10.00),
        Metric("pb", "valuation", "lower", 8.00, 1.00),
        Metric("free_cash_flow_yield", "valuation", "higher", -0.02, 0.08),
        Metric("volatility_1y", "price_discipline", "lower", 0.60, 0.15),
    )

    def __init__(self, *, minimum_coverage: float = 0.60) -> None:
        if not 0 < minimum_coverage <= 1:
            raise ValueError("minimum_coverage must be greater than 0 and at most 1")
        self.minimum_coverage = minimum_coverage

    @property
    def required_columns(self) -> list[str]:
        return ["symbol", *(metric.column for metric in self.METRICS)]

    def score(self, fundamentals: pd.DataFrame) -> pd.DataFrame:
        """Return ranked research candidates from normalized decimal metrics.

        Percentage-like inputs use decimals: 18% ROE is represented as ``0.18``.
        Missing factors reduce the reported data coverage; available category
        weights are re-normalized rather than silently treating missing data as
        either strong or poor.
        """

        if "symbol" not in fundamentals:
            raise ValueError("Fundamentals must contain a symbol column")
        if fundamentals.empty:
            return self._empty_result()

        result = fundamentals.copy()
        result["symbol"] = result["symbol"].astype("string").str.strip().str.upper()
        if result["symbol"].isna().any() or result["symbol"].eq("").any():
            raise ValueError("Fundamental rows must have non-empty symbols")
        if result["symbol"].duplicated().any():
            duplicates = sorted(
                result.loc[result["symbol"].duplicated(), "symbol"].unique()
            )
            raise ValueError(
                f"Fundamentals contain duplicate symbols: {', '.join(duplicates)}"
            )

        metric_score_columns: list[str] = []
        available_columns: list[str] = []
        for metric in self.METRICS:
            if metric.column not in result:
                result[metric.column] = np.nan
            values = pd.to_numeric(result[metric.column], errors="coerce")
            result[metric.column] = values
            score_column = f"{metric.column}_score"
            result[score_column] = self._metric_score(values, metric)
            metric_score_columns.append(score_column)
            available_columns.append(metric.column)

        result["data_coverage"] = result[available_columns].notna().mean(axis=1)
        for category in self.CATEGORY_WEIGHTS:
            category_score_columns = [
                f"{metric.column}_score"
                for metric in self.METRICS
                if metric.category == category
            ]
            result[f"{category}_score"] = result[category_score_columns].mean(
                axis=1, skipna=True
            )

        result["overall_score"] = result.apply(self._overall_score, axis=1)
        result["research_view"] = result.apply(self._research_view, axis=1)
        result = result.sort_values(
            ["overall_score", "data_coverage", "symbol"],
            ascending=[False, False, True],
            na_position="last",
            ignore_index=True,
        )
        eligible = result["data_coverage"] >= self.minimum_coverage
        result["rank"] = pd.Series(pd.NA, index=result.index, dtype="Int64")
        result.loc[eligible, "rank"] = range(1, int(eligible.sum()) + 1)

        display_columns = [
            "rank",
            "symbol",
            "overall_score",
            "research_view",
            "data_coverage",
            *(f"{category}_score" for category in self.CATEGORY_WEIGHTS),
        ]
        result["overall_score"] = result["overall_score"].round(1)
        result["data_coverage"] = result["data_coverage"].round(3)
        for category in self.CATEGORY_WEIGHTS:
            result[f"{category}_score"] = result[f"{category}_score"].round(1)
        return result[display_columns]

    @staticmethod
    def _metric_score(values: pd.Series, metric: Metric) -> pd.Series:
        if metric.direction == "higher":
            score = (values - metric.poor) / (metric.strong - metric.poor)
        else:
            score = (metric.poor - values) / (metric.poor - metric.strong)
        return score.clip(lower=0, upper=1).mul(100).where(values.notna())

    def _overall_score(self, row: pd.Series) -> float:
        weighted_total = 0.0
        available_weight = 0.0
        for category, weight in self.CATEGORY_WEIGHTS.items():
            value = row[f"{category}_score"]
            if pd.notna(value):
                weighted_total += float(value) * weight
                available_weight += weight
        if available_weight == 0:
            return np.nan
        return weighted_total / available_weight

    def _research_view(self, row: pd.Series) -> str:
        if row["data_coverage"] < self.minimum_coverage or pd.isna(
            row["overall_score"]
        ):
            return "Insufficient data"
        score = float(row["overall_score"])
        if score >= 75:
            return "Strong candidate"
        if score >= 60:
            return "Watchlist"
        if score >= 45:
            return "Caution"
        return "Avoid"

    @classmethod
    def _empty_result(cls) -> pd.DataFrame:
        return pd.DataFrame(
            columns=[
                "rank",
                "symbol",
                "overall_score",
                "research_view",
                "data_coverage",
                *(f"{category}_score" for category in cls.CATEGORY_WEIGHTS),
            ]
        )
