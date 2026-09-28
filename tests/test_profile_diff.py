from __future__ import annotations

import pandas as pd

from src.investing.profile_diff import (
    profile_calibration_alignment,
    profile_version_diff,
    resolve_profile_metrics,
)
from src.investing.profile_store import ScoringProfileStore
from src.investing.scoring_profiles import BASELINE_PROFILE_VERSION, metrics_for


def _save_test_version(store: ScoringProfileStore, version: int) -> None:
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
    store.save_version(version, profiles, source="test")


def test_profile_version_diff_flags_changed_thresholds(tmp_path) -> None:
    store = ScoringProfileStore(tmp_path / "research.db")
    _save_test_version(store, 2)

    diff = profile_version_diff(
        str(tmp_path / "research.db"),
        base_version=BASELINE_PROFILE_VERSION,
        compare_version=2,
        changed_only=True,
    )

    roe = diff.loc[
        (diff["metric"] == "roe") & (diff["entity_type"] == "non_bank")
    ].iloc[0]
    assert roe["changed"]
    assert roe["base_poor"] == 0.0
    assert roe["compare_poor"] == 0.05


def test_profile_calibration_alignment_detects_mismatches(tmp_path) -> None:
    store = ScoringProfileStore(tmp_path / "research.db")
    _save_test_version(store, 2)
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
                "sample_size": 10,
            }
        ]
    )

    alignment = profile_calibration_alignment(
        str(tmp_path / "research.db"),
        profile_version=2,
        suggestions=suggestions,
    )

    assert len(alignment) == 1
    assert not alignment.iloc[0]["matches_suggestion"]


def test_resolve_profile_metrics_uses_builtin_baseline(tmp_path) -> None:
    store = ScoringProfileStore(tmp_path / "research.db")
    profiles = resolve_profile_metrics(store, BASELINE_PROFILE_VERSION)

    assert "non_bank" in profiles
    assert profiles["non_bank"]
