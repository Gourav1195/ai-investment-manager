from __future__ import annotations

import pandas as pd

from src.investing.calibration import (
    analyze_universe_backtest,
    deserialize_calibration_report,
    serialize_calibration_report,
    threshold_suggestions,
)


def test_score_bucket_report_ranks_views_by_forward_returns() -> None:
    snapshots = pd.DataFrame(
        [
            {
                "symbol": "STRONG",
                "research_view": "Strong candidate",
                "forward_return": 0.20,
                "excess_forward_return": 0.10,
            },
            {
                "symbol": "WEAK",
                "research_view": "Avoid",
                "forward_return": -0.10,
                "excess_forward_return": -0.15,
            },
        ]
    )
    report = analyze_universe_backtest(snapshots).score_buckets

    assert set(report["research_view"]) == {"Strong candidate", "Avoid"}
    strong = report.loc[report["research_view"] == "Strong candidate"].iloc[0]
    weak = report.loc[report["research_view"] == "Avoid"].iloc[0]
    assert strong["avg_forward_return"] > weak["avg_forward_return"]


def test_threshold_suggestions_use_entity_type_profiles() -> None:
    snapshots = pd.DataFrame(
        [
            {
                "entity_type": "bank",
                "gross_npa_ratio": 1.0,
                "roe": 0.15,
            },
            {
                "entity_type": "bank",
                "gross_npa_ratio": 3.0,
                "roe": 0.10,
            },
            {
                "entity_type": "bank",
                "gross_npa_ratio": 5.0,
                "roe": 0.08,
            },
            {
                "entity_type": "bank",
                "gross_npa_ratio": 2.0,
                "roe": 0.12,
            },
        ]
    )

    suggestions = threshold_suggestions(snapshots)

    npa = suggestions.loc[suggestions["metric"] == "gross_npa_ratio"].iloc[0]
    assert npa["direction"] == "lower"
    assert npa["suggested_poor"] > npa["suggested_strong"]


def test_calibration_report_round_trips_through_json() -> None:
    snapshots = pd.DataFrame(
        [
            {
                "symbol": "AAA",
                "research_view": "Watchlist",
                "forward_return": 0.05,
                "excess_forward_return": 0.01,
                "entity_type": "non_bank",
                "roe": 0.12,
            }
        ]
    )
    report = analyze_universe_backtest(snapshots)
    restored = deserialize_calibration_report(serialize_calibration_report(report))

    assert list(restored.score_buckets.columns) == list(report.score_buckets.columns)
    assert list(restored.threshold_suggestions.columns) == list(
        report.threshold_suggestions.columns
    )
