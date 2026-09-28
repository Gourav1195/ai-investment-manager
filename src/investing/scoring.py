"""Transparent long-term equity scoring.

This module deliberately uses deterministic, documented factor transforms.
Language models may explain these results later, but they do not calculate or
override the scores.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .profile_store import ScoringProfileStore, resolve_metrics
from .scoring_profiles import DEFAULT_ENTITY_TYPE, Metric, metrics_for


class LongTermScorer:
    """Rank companies using quality, growth, resilience, and valuation factors."""

    CATEGORY_WEIGHTS = {
        "quality": 0.30,
        "growth": 0.25,
        "financial_strength": 0.20,
        "valuation": 0.20,
        "price_discipline": 0.05,
    }

    METRICS = metrics_for(DEFAULT_ENTITY_TYPE)

    def __init__(
        self,
        *,
        minimum_coverage: float = 0.60,
        profile_store: ScoringProfileStore | None = None,
        profile_version: int | None = None,
    ) -> None:
        if not 0 < minimum_coverage <= 1:
            raise ValueError("minimum_coverage must be greater than 0 and at most 1")
        self.minimum_coverage = minimum_coverage
        self.profile_store = profile_store
        self.profile_version = profile_version

    def metrics_for(self, entity_type: str | None) -> tuple[Metric, ...]:
        return resolve_metrics(
            entity_type,
            profile_store=self.profile_store,
            profile_version=self.profile_version,
        )

    @classmethod
    def default_metrics_for(cls, entity_type: str | None) -> tuple[Metric, ...]:
        return metrics_for(entity_type)

    @property
    def required_columns(self) -> list[str]:
        return ["symbol", *(metric.column for metric in self.METRICS)]

    def score(self, fundamentals: pd.DataFrame) -> pd.DataFrame:
        """Return ranked research candidates from normalized decimal metrics.

        Percentage-like inputs use decimals: 18% ROE is represented as ``0.18``.
        When an ``entity_type`` column is present, each row is scored with the
        industry-specific thresholds for ``non_bank``, ``bank``, ``nbfc``, or
        ``insurance``. When a ``ScoringProfileStore`` is configured, the active or
        requested profile version overrides built-in thresholds.
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

        if "entity_type" not in result:
            result["entity_type"] = DEFAULT_ENTITY_TYPE
        result["entity_type"] = (
            result["entity_type"].astype("string").str.strip().str.lower()
        )

        metric_columns = sorted(
            {
                metric.column
                for entity_type in result["entity_type"].dropna().unique()
                for metric in self.metrics_for(entity_type)
            }
        )
        for column in metric_columns:
            if column not in result:
                result[column] = np.nan
            result[column] = pd.to_numeric(result[column], errors="coerce")

        category_score_columns = {
            category: f"{category}_score" for category in self.CATEGORY_WEIGHTS
        }
        for category, column in category_score_columns.items():
            result[column] = np.nan

        result["data_coverage"] = np.nan
        result["overall_score"] = np.nan
        result["research_view"] = "Insufficient data"

        for index, row in result.iterrows():
            entity_type = row["entity_type"] or DEFAULT_ENTITY_TYPE
            metrics = self.metrics_for(entity_type)
            metric_scores: dict[str, float] = {}
            available_columns: list[str] = []
            for metric in metrics:
                value = row.get(metric.column)
                if value is None or pd.isna(value):
                    continue
                available_columns.append(metric.column)
                score = self._metric_score(pd.Series([float(value)]), metric).iloc[0]
                if pd.notna(score):
                    metric_scores[metric.column] = float(score)

            coverage = (
                len(available_columns) / len(metrics) if metrics else np.nan
            )
            result.at[index, "data_coverage"] = coverage

            for category in self.CATEGORY_WEIGHTS:
                category_metrics = [
                    metric_scores[metric.column]
                    for metric in metrics
                    if metric.category == category
                    and metric.column in metric_scores
                ]
                if category_metrics:
                    result.at[index, category_score_columns[category]] = float(
                        np.mean(category_metrics)
                    )

            overall = self._overall_score_from_categories(
                {category: result.at[index, column] for category, column in category_score_columns.items()}
            )
            result.at[index, "overall_score"] = overall
            result.at[index, "research_view"] = self._research_view(
                coverage=coverage,
                overall_score=overall,
            )

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

    def _overall_score_from_categories(self, category_scores: dict[str, float]) -> float:
        weighted_total = 0.0
        available_weight = 0.0
        for category, weight in self.CATEGORY_WEIGHTS.items():
            value = category_scores.get(category)
            if value is not None and pd.notna(value):
                weighted_total += float(value) * weight
                available_weight += weight
        if available_weight == 0:
            return np.nan
        return weighted_total / available_weight

    def _research_view(self, *, coverage: float, overall_score: float) -> str:
        if coverage < self.minimum_coverage or pd.isna(overall_score):
            return "Insufficient data"
        score = float(overall_score)
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
