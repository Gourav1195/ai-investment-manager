"""Compare scoring profile versions and calibration suggestions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import pandas as pd

from .profile_store import ScoringProfileStore
from .scoring_profiles import BASELINE_PROFILE_VERSION, INDUSTRY_PROFILES, Metric


@dataclass(frozen=True)
class ProfileVersionOption:
    profile_version: int
    label: str
    is_active: bool


def profile_version_options(database: str) -> list[ProfileVersionOption]:
    """Return selectable profile versions including the built-in baseline."""

    store = ScoringProfileStore(database)
    active = store.active_version()
    options = [
        ProfileVersionOption(
            profile_version=BASELINE_PROFILE_VERSION,
            label="Baseline (built-in v1)",
            is_active=active in {None, BASELINE_PROFILE_VERSION},
        )
    ]
    for summary in store.list_versions():
        if summary.profile_version == BASELINE_PROFILE_VERSION:
            continue
        status = "active" if summary.is_active else summary.source
        options.append(
            ProfileVersionOption(
                profile_version=summary.profile_version,
                label=f"v{summary.profile_version} ({status})",
                is_active=summary.is_active,
            )
        )
    return options


def default_profile_diff_versions(database: str) -> tuple[int, int]:
    """Return sensible default base/compare versions for review."""

    store = ScoringProfileStore(database)
    versions = store.list_versions()
    active = store.active_version() or BASELINE_PROFILE_VERSION
    candidates = [
        summary.profile_version
        for summary in versions
        if summary.profile_version != active
    ]
    if candidates:
        return active, max(candidates)
    if versions:
        newest = max(summary.profile_version for summary in versions)
        if newest != active:
            return active, newest
    return BASELINE_PROFILE_VERSION, BASELINE_PROFILE_VERSION


def profile_version_diff(
    database: str,
    *,
    base_version: int,
    compare_version: int,
    changed_only: bool = False,
) -> pd.DataFrame:
    """Return threshold differences between two profile versions."""

    store = ScoringProfileStore(database)
    base_profiles = resolve_profile_metrics(store, base_version)
    compare_profiles = resolve_profile_metrics(store, compare_version)
    rows: list[dict[str, object]] = []
    for entity_type in sorted(set(base_profiles) | set(compare_profiles)):
        base_metrics = {metric.column: metric for metric in base_profiles.get(entity_type, ())}
        compare_metrics = {
            metric.column: metric for metric in compare_profiles.get(entity_type, ())
        }
        for metric_name in sorted(set(base_metrics) | set(compare_metrics)):
            base_metric = base_metrics.get(metric_name)
            compare_metric = compare_metrics.get(metric_name)
            changed = _metric_changed(base_metric, compare_metric)
            if changed_only and not changed:
                continue
            rows.append(
                {
                    "entity_type": entity_type,
                    "metric": metric_name,
                    "category": _metric_field(compare_metric, base_metric, "category"),
                    "direction": _metric_field(compare_metric, base_metric, "direction"),
                    "base_poor": _metric_value(base_metric, "poor"),
                    "base_strong": _metric_value(base_metric, "strong"),
                    "compare_poor": _metric_value(compare_metric, "poor"),
                    "compare_strong": _metric_value(compare_metric, "strong"),
                    "poor_delta": _metric_delta(base_metric, compare_metric, "poor"),
                    "strong_delta": _metric_delta(base_metric, compare_metric, "strong"),
                    "changed": changed,
                }
            )
    return pd.DataFrame(rows)


def profile_calibration_alignment(
    database: str,
    *,
    profile_version: int,
    suggestions: pd.DataFrame,
) -> pd.DataFrame:
    """Compare a profile version against calibration threshold suggestions."""

    if suggestions.empty:
        return suggestions

    store = ScoringProfileStore(database)
    profiles = resolve_profile_metrics(store, profile_version)
    rows: list[dict[str, object]] = []
    for _, suggestion in suggestions.iterrows():
        entity_type = str(suggestion["entity_type"])
        metric_name = str(suggestion["metric"])
        profile_metric = _lookup_metric(profiles, entity_type, metric_name)
        rows.append(
            {
                "entity_type": entity_type,
                "metric": metric_name,
                "direction": suggestion.get("direction"),
                "profile_poor": _metric_value(profile_metric, "poor"),
                "profile_strong": _metric_value(profile_metric, "strong"),
                "suggested_poor": suggestion.get("suggested_poor"),
                "suggested_strong": suggestion.get("suggested_strong"),
                "sample_size": suggestion.get("sample_size"),
                "matches_suggestion": _matches_suggestion(profile_metric, suggestion),
            }
        )
    frame = pd.DataFrame(rows)
    return frame.sort_values(["entity_type", "metric"]).reset_index(drop=True)


def resolve_profile_metrics(
    store: ScoringProfileStore,
    profile_version: int,
) -> dict[str, tuple[Metric, ...]]:
    """Load a profile version from storage or built-in defaults."""

    if profile_version == BASELINE_PROFILE_VERSION and not store.version_exists(
        profile_version
    ):
        return {entity_type: tuple(metrics) for entity_type, metrics in INDUSTRY_PROFILES.items()}
    return store.load_version(profile_version)


def _lookup_metric(
    profiles: Mapping[str, tuple[Metric, ...]],
    entity_type: str,
    metric_name: str,
) -> Metric | None:
    for metric in profiles.get(entity_type, ()):
        if metric.column == metric_name:
            return metric
    return None


def _metric_changed(base_metric: Metric | None, compare_metric: Metric | None) -> bool:
    if base_metric is None or compare_metric is None:
        return base_metric is not compare_metric
    return (
        base_metric.poor != compare_metric.poor
        or base_metric.strong != compare_metric.strong
        or base_metric.direction != compare_metric.direction
        or base_metric.category != compare_metric.category
    )


def _metric_field(
    primary: Metric | None,
    fallback: Metric | None,
    field: str,
) -> str | None:
    metric = primary or fallback
    if metric is None:
        return None
    return str(getattr(metric, field))


def _metric_value(metric: Metric | None, field: str) -> float | None:
    if metric is None:
        return None
    return float(getattr(metric, field))


def _metric_delta(
    base_metric: Metric | None,
    compare_metric: Metric | None,
    field: str,
) -> float | None:
    base_value = _metric_value(base_metric, field)
    compare_value = _metric_value(compare_metric, field)
    if base_value is None or compare_value is None:
        return None
    return compare_value - base_value


def _matches_suggestion(metric: Metric | None, suggestion: pd.Series) -> bool:
    if metric is None:
        return False
    poor = suggestion.get("suggested_poor")
    strong = suggestion.get("suggested_strong")
    if poor is None or strong is None or pd.isna(poor) or pd.isna(strong):
        return False
    return _close(metric.poor, float(poor)) and _close(metric.strong, float(strong))


def _close(left: float, right: float, *, tolerance: float = 1e-6) -> bool:
    return abs(left - right) <= tolerance
