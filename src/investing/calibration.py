"""Universe backtest analysis and industry threshold suggestions.

Calibration reports use persisted research snapshots only. They do not change
scores automatically; they surface how score buckets and metric distributions
behaved in historical walk-forward runs.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .scoring_profiles import INDUSTRY_PROFILES, Metric, metrics_for


@dataclass(frozen=True)
class CalibrationReport:
    score_buckets: pd.DataFrame
    threshold_suggestions: pd.DataFrame


def analyze_universe_backtest(
    snapshots: pd.DataFrame,
    *,
    low_quantile: float = 0.25,
    high_quantile: float = 0.75,
) -> CalibrationReport:
    """Summarize score buckets and suggest metric thresholds from snapshots."""

    if snapshots.empty:
        empty_buckets = pd.DataFrame(
            columns=[
                "research_view",
                "count",
                "avg_forward_return",
                "avg_excess_return",
                "positive_excess_rate",
            ]
        )
        empty_thresholds = pd.DataFrame(
            columns=[
                "entity_type",
                "metric",
                "direction",
                "current_poor",
                "current_strong",
                "suggested_poor",
                "suggested_strong",
                "sample_size",
            ]
        )
        return CalibrationReport(
            score_buckets=empty_buckets,
            threshold_suggestions=empty_thresholds,
        )

    return CalibrationReport(
        score_buckets=score_bucket_report(snapshots),
        threshold_suggestions=threshold_suggestions(
            snapshots,
            low_quantile=low_quantile,
            high_quantile=high_quantile,
        ),
    )


def score_bucket_report(snapshots: pd.DataFrame) -> pd.DataFrame:
    """Aggregate forward returns by research view."""

    frame = snapshots.copy()
    if "research_view" not in frame.columns:
        raise ValueError("Snapshots must include a research_view column")

    grouped = frame.groupby("research_view", dropna=False, sort=False)
    report = grouped.agg(
        count=("symbol", "count"),
        avg_forward_return=("forward_return", "mean"),
        avg_excess_return=("excess_forward_return", "mean"),
        positive_excess_rate=(
            "excess_forward_return",
            lambda values: _positive_rate(values),
        ),
    ).reset_index()

    order = [
        "Strong candidate",
        "Watchlist",
        "Caution",
        "Avoid",
        "Insufficient data",
    ]
    report["research_view"] = pd.Categorical(
        report["research_view"], categories=order, ordered=True
    )
    return report.sort_values("research_view").reset_index(drop=True)


def threshold_suggestions(
    snapshots: pd.DataFrame,
    *,
    low_quantile: float = 0.25,
    high_quantile: float = 0.75,
) -> pd.DataFrame:
    """Suggest poor/strong metric bounds from cross-sectional snapshot values."""

    if not 0 < low_quantile < high_quantile < 1:
        raise ValueError("Quantiles must satisfy 0 < low_quantile < high_quantile < 1")
    if snapshots.empty:
        return pd.DataFrame(
            columns=[
                "entity_type",
                "metric",
                "direction",
                "current_poor",
                "current_strong",
                "suggested_poor",
                "suggested_strong",
                "sample_size",
            ]
        )

    frame = snapshots.copy()
    if "entity_type" not in frame.columns:
        frame["entity_type"] = "non_bank"
    frame["entity_type"] = frame["entity_type"].fillna("non_bank").astype(str).str.lower()

    rows: list[dict[str, object]] = []
    for entity_type, group in frame.groupby("entity_type", sort=True):
        for metric in metrics_for(entity_type):
            if metric.column not in group.columns:
                continue
            values = pd.to_numeric(group[metric.column], errors="coerce").dropna()
            if values.empty:
                continue
            low_value = float(values.quantile(low_quantile))
            high_value = float(values.quantile(high_quantile))
            suggested_poor, suggested_strong = _suggested_bounds(
                metric, low_value, high_value
            )
            rows.append(
                {
                    "entity_type": entity_type,
                    "metric": metric.column,
                    "direction": metric.direction,
                    "current_poor": metric.poor,
                    "current_strong": metric.strong,
                    "suggested_poor": round(suggested_poor, 6),
                    "suggested_strong": round(suggested_strong, 6),
                    "sample_size": int(len(values)),
                }
            )
    return pd.DataFrame(rows)


def _suggested_bounds(
    metric: Metric, low_value: float, high_value: float
) -> tuple[float, float]:
    if metric.direction == "higher":
        return low_value, high_value
    return high_value, low_value


def build_profile_version(
    suggestions: pd.DataFrame,
    *,
    min_sample_size: int = 5,
) -> dict[str, tuple[Metric, ...]]:
    """Merge calibration suggestions into full entity profiles."""

    if min_sample_size < 1:
        raise ValueError("min_sample_size must be at least 1")

    suggestion_lookup: dict[tuple[str, str], pd.Series] = {}
    if not suggestions.empty:
        for _, row in suggestions.iterrows():
            suggestion_lookup[(str(row["entity_type"]), str(row["metric"]))] = row

    profiles: dict[str, tuple[Metric, ...]] = {}
    for entity_type in INDUSTRY_PROFILES:
        updated: list[Metric] = []
        for metric in metrics_for(entity_type):
            row = suggestion_lookup.get((entity_type, metric.column))
            if row is not None and int(row["sample_size"]) >= min_sample_size:
                updated.append(
                    Metric(
                        column=metric.column,
                        category=metric.category,
                        direction=metric.direction,
                        poor=float(row["suggested_poor"]),
                        strong=float(row["suggested_strong"]),
                    )
                )
            else:
                updated.append(metric)
        profiles[entity_type] = tuple(updated)
    return profiles


def _positive_rate(values: pd.Series) -> float | None:
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    if numeric.empty:
        return None
    return float((numeric > 0).mean())
