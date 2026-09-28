"""Data helpers for the India research dashboard.

These functions load and format persisted research snapshots without any UI
dependencies so they can be tested independently of Streamlit.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import json

import pandas as pd

from .calibration import CalibrationReport, analyze_universe_backtest
from .orchestration import OrchestrationStore
from .profile_store import ProfileVersionSummary, ScoringProfileStore
from .research import ResearchStore

SUMMARY_COLUMNS = [
    "as_of",
    "symbol",
    "research_view",
    "overall_score",
    "rank",
    "data_coverage",
    "quality_score",
    "growth_score",
    "financial_strength_score",
    "valuation_score",
    "price_discipline_score",
    "forward_return",
    "benchmark_forward_return",
    "excess_forward_return",
    "portfolio_forward_return",
    "excess_portfolio_forward_return",
    "snapshot_cadence",
]

CATEGORY_COLUMNS = [
    ("quality_score", "Business quality"),
    ("growth_score", "Growth consistency"),
    ("financial_strength_score", "Financial strength"),
    ("valuation_score", "Valuation"),
    ("price_discipline_score", "Price discipline"),
]

FUNDAMENTAL_COLUMNS = [
    ("roe", "ROE"),
    ("roce", "ROCE"),
    ("operating_margin", "Operating margin"),
    ("revenue_cagr_3y", "Revenue CAGR (3y)"),
    ("earnings_cagr_3y", "Earnings CAGR (3y)"),
    ("debt_to_equity", "Debt / equity"),
    ("interest_coverage", "Interest coverage"),
    ("free_cash_flow", "Free cash flow"),
    ("pe", "P/E"),
    ("pb", "P/B"),
    ("free_cash_flow_yield", "FCF yield"),
    ("volatility_1y", "Volatility (1y)"),
]


def overview_metrics(store: ResearchStore) -> dict[str, Any]:
    """Return high-level counts and coverage for the research database."""

    counts = store.counts()
    snapshots = store.list_snapshots()
    evaluations = store.list_evaluations()
    if snapshots.empty:
        return {
            **counts,
            "symbols": 0,
            "as_of_dates": 0,
            "latest_as_of": None,
            "research_views": {},
        }

    views = (
        snapshots["research_view"]
        .fillna("Unknown")
        .value_counts()
        .sort_index()
        .to_dict()
    )
    return {
        **counts,
        "symbols": snapshots["symbol"].nunique(),
        "as_of_dates": snapshots["as_of"].nunique(),
        "latest_as_of": snapshots["as_of"].max(),
        "research_views": views,
        "evaluation_count": len(evaluations),
    }


def snapshot_summary_frame(
    store: ResearchStore,
    *,
    symbol: str | None = None,
    as_of: str | None = None,
    research_view: str | None = None,
) -> pd.DataFrame:
    """Return dashboard-ready snapshot rows with the most useful columns."""

    frame = store.list_snapshots(symbol=symbol, as_of=as_of)
    if frame.empty:
        return frame
    if research_view:
        frame = frame[frame["research_view"] == research_view]
    present = [column for column in SUMMARY_COLUMNS if column in frame.columns]
    summary = frame[present].copy()
    for column in ("overall_score", "data_coverage"):
        if column in summary.columns:
            summary[column] = summary[column].map(_format_ratio)
    for column in (
        "forward_return",
        "benchmark_forward_return",
        "excess_forward_return",
        "portfolio_forward_return",
        "excess_portfolio_forward_return",
    ):
        if column in summary.columns:
            summary[column] = summary[column].map(_format_return)
    return summary.sort_values(
        ["as_of", "rank", "symbol"], ascending=[False, True, True], na_position="last"
    )


def category_scores(row: Mapping[str, Any]) -> pd.DataFrame:
    """Return category score rows for charting."""

    records = []
    for column, label in CATEGORY_COLUMNS:
        value = row.get(column)
        if value is None or pd.isna(value):
            continue
        records.append({"category": label, "score": float(value)})
    return pd.DataFrame(records)


def fundamental_metrics(row: Mapping[str, Any]) -> pd.DataFrame:
    """Return fundamental metric rows for display."""

    records = []
    for column, label in FUNDAMENTAL_COLUMNS:
        value = row.get(column)
        if value is None or pd.isna(value):
            continue
        records.append({"metric": label, "value": _format_metric(column, value)})
    return pd.DataFrame(records)


def explanation_for_snapshot(
    store: ResearchStore,
    *,
    symbol: str,
    as_of: str,
) -> dict[str, Any] | None:
    """Load a parsed explanation for a symbol and as-of date."""

    explanations = store.list_explanations(symbol=symbol, as_of=as_of)
    if explanations.empty:
        return None
    row = explanations.iloc[0]
    return {
        "symbol": row["symbol"],
        "as_of": row["as_of"],
        "research_view": row.get("research_view"),
        "overall_score": row.get("overall_score"),
        "data_coverage": row.get("data_coverage"),
        "score_drivers": _parse_json_list(row.get("score_drivers_json")),
        "risk_flags": _parse_json_list(row.get("risk_flags_json")),
        "source_documents": _parse_json_objects(row.get("source_documents_json")),
    }


def snapshot_detail(
    store: ResearchStore,
    *,
    symbol: str,
    as_of: str,
) -> dict[str, Any] | None:
    """Return a snapshot row plus optional explanation for the detail panel."""

    snapshots = store.list_snapshots(symbol=symbol, as_of=as_of)
    if snapshots.empty:
        return None
    row = snapshots.iloc[0].to_dict()
    return {
        "snapshot": row,
        "explanation": explanation_for_snapshot(store, symbol=symbol, as_of=as_of),
    }


def calibration_report(store: ResearchStore) -> CalibrationReport:
    """Return score bucket and threshold suggestion tables."""

    snapshots = store.list_snapshots()
    return analyze_universe_backtest(snapshots)


def profile_versions(database: str | Path) -> list[ProfileVersionSummary]:
    return ScoringProfileStore(database).list_versions()


def orchestration_runs(database: str | Path) -> pd.DataFrame:
    runs = OrchestrationStore(database).list_runs()
    if runs.empty:
        return runs
    display = runs.copy()
    if "as_of_dates_json" in display.columns:
        display["as_of_dates"] = display["as_of_dates_json"].map(_format_as_of_dates)
    if "skipped_symbols_json" in display.columns:
        display["skipped_count"] = display["skipped_symbols_json"].map(_count_skipped)
    columns = [
        column
        for column in [
            "created_at",
            "index_name",
            "as_of_dates",
            "symbols_requested",
            "symbols_evaluated",
            "records_persisted",
            "skipped_count",
            "benchmark_index",
            "forward_days",
            "archive_status",
        ]
        if column in display.columns
    ]
    return display[columns]


def filter_options(store: ResearchStore) -> dict[str, list[str]]:
    """Return distinct filter values from persisted snapshots."""

    snapshots = store.list_snapshots()
    if snapshots.empty:
        return {"symbols": [], "as_of_dates": [], "research_views": []}
    return {
        "symbols": sorted(snapshots["symbol"].dropna().unique().tolist()),
        "as_of_dates": sorted(snapshots["as_of"].dropna().unique().tolist(), reverse=True),
        "research_views": sorted(
            snapshots["research_view"].dropna().unique().tolist()
        ),
    }


def _parse_json_list(value: Any) -> list[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed]


def _parse_json_objects(value: Any) -> list[dict[str, Any]]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict)]
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [dict(item) for item in parsed if isinstance(item, dict)]


def _format_ratio(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    return f"{float(value):.1f}"


def _format_return(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    return f"{float(value) * 100:.1f}%"


def _format_as_of_dates(value: Any) -> str:
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return str(value)
    if not isinstance(parsed, list):
        return str(value)
    return ", ".join(str(item) for item in parsed)


def _count_skipped(value: Any) -> int:
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return 0
    return len(parsed) if isinstance(parsed, list) else 0


def _format_metric(column: str, value: Any) -> str:
    numeric = float(value)
    if column in {"roe", "roce", "operating_margin", "revenue_cagr_3y", "earnings_cagr_3y"}:
        return f"{numeric * 100:.1f}%"
    if column in {"free_cash_flow_yield", "volatility_1y", "gross_npa_ratio", "cet1_ratio"}:
        return f"{numeric * 100:.1f}%"
    if column in {"debt_to_equity", "interest_coverage", "pe", "pb"}:
        return f"{numeric:.2f}"
    if column == "free_cash_flow":
        return f"{numeric:,.0f}"
    return str(value)
