from __future__ import annotations

import pandas as pd

from src.investing.calibration import build_profile_version
from src.investing.profile_store import ScoringProfileStore
from src.investing.scoring import LongTermScorer
from src.investing.scoring_profiles import metrics_for


def test_profile_store_saves_and_activates_version(tmp_path) -> None:
    store = ScoringProfileStore(tmp_path / "research.db")
    profiles = {
        "non_bank": tuple(
            metric
            if metric.column != "roe"
            else metric.__class__(
                metric.column,
                metric.category,
                metric.direction,
                0.05,
                0.30,
            )
            for metric in metrics_for("non_bank")
        )
    }

    inserted = store.save_version(2, profiles, source="test")
    store.activate(2)

    assert inserted > 0
    assert store.active_version() == 2
    loaded = store.metrics_for("non_bank", 2)
    assert loaded is not None
    roe = next(metric for metric in loaded if metric.column == "roe")
    assert roe.poor == 0.05
    assert roe.strong == 0.30


def test_scorer_uses_activated_profile(tmp_path) -> None:
    store = ScoringProfileStore(tmp_path / "research.db")
    profiles = {
        "non_bank": tuple(
            metric
            if metric.column != "roe"
            else metric.__class__(
                metric.column,
                metric.category,
                metric.direction,
                0.00,
                0.50,
            )
            for metric in metrics_for("non_bank")
        )
    }
    store.save_version(2, profiles, source="test")
    store.activate(2)

    fundamentals = pd.DataFrame(
        [
            {
                "symbol": "TEST",
                "entity_type": "non_bank",
                "roe": 0.40,
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
            }
        ]
    )
    scorer = LongTermScorer(profile_store=store, profile_version=2)
    result = scorer.score(fundamentals)

    assert result.loc[0, "overall_score"] is not None


def test_build_profile_version_keeps_defaults_for_small_samples() -> None:
    suggestions = pd.DataFrame(
        [
            {
                "entity_type": "non_bank",
                "metric": "roe",
                "direction": "higher",
                "current_poor": 0.0,
                "current_strong": 0.25,
                "suggested_poor": 0.10,
                "suggested_strong": 0.30,
                "sample_size": 2,
            }
        ]
    )

    profiles = build_profile_version(suggestions, min_sample_size=5)
    roe = next(metric for metric in profiles["non_bank"] if metric.column == "roe")

    assert roe.poor == 0.0
    assert roe.strong == 0.25
