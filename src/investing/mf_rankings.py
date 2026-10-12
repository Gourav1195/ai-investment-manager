"""Rank mutual funds by SEBI category using AMFI master + cached NAV history."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .mf_nav_client import MfNavClient
from .mf_peer_comparison import _metrics_row, _return_metrics
from .portfolio_store import PortfolioStore

# Plain-English labels for common AMFI category strings
CATEGORY_CHOICES = [
    "All categories",
    "Equity Scheme - Flexi Cap Fund",
    "Equity Scheme - Large Cap Fund",
    "Equity Scheme - Mid Cap Fund",
    "Equity Scheme - Small Cap Fund",
    "Equity Scheme - ELSS",
    "Equity Scheme - Index Funds",
    "Hybrid Scheme - Aggressive Hybrid Fund",
    "Hybrid Scheme - Balanced Hybrid Fund",
]

MAX_FUNDS_TO_RANK = 80
MAX_NAV_FETCH_FOR_CHART = 8


@dataclass(frozen=True)
class CategoryRankingResult:
    table: pd.DataFrame
    nav_series: dict[str, pd.DataFrame]
    category_avg_series: pd.DataFrame | None
    funds_fetched: int
    funds_skipped: int


def list_categories_from_master(store: PortfolioStore) -> list[str]:
    if store.scheme_master_count() == 0:
        return []
    frame = store.list_scheme_master_options(limit=50_000)
    if frame.empty or "category" not in frame.columns:
        return []
    return sorted(frame["category"].dropna().astype(str).unique().tolist())


def rank_funds_in_category(
    store: PortfolioStore,
    *,
    category: str,
    plan_type: str = "Direct",
    option_type: str = "Growth",
    rank_by: str = "cagr_3y",
    top_n: int = 15,
    max_candidates: int = MAX_FUNDS_TO_RANK,
    client: MfNavClient | None = None,
    progress: callable | None = None,
) -> CategoryRankingResult:
    client = client or MfNavClient(store)
    codes = store.list_peer_scheme_codes(
        category=category,
        plan_type=plan_type,
        option_type=option_type,
        exclude_code="",
        limit=max_candidates,
    )
    rows: list[dict[str, object]] = []
    nav_series: dict[str, pd.DataFrame] = {}
    skipped = 0
    for index, code in enumerate(codes):
        if progress is not None:
            progress(index / max(len(codes), 1), f"Loading fund {index + 1} of {len(codes)}…")
        try:
            series = client.sync_scheme_nav(code)
        except Exception:
            skipped += 1
            continue
        metrics = _return_metrics(
            code,
            series.scheme_name,
            category,
            plan_type,
            option_type,
            series.nav,
        )
        if metrics.cagr_3y is None and metrics.cagr_1y is None:
            skipped += 1
            continue
        rows.append(_metrics_row(metrics))
        if len(nav_series) < MAX_NAV_FETCH_FOR_CHART:
            nav_series[code] = series.nav

    frame = pd.DataFrame(rows)
    if frame.empty:
        return CategoryRankingResult(
            table=frame,
            nav_series={},
            category_avg_series=None,
            funds_fetched=0,
            funds_skipped=skipped,
        )

    sort_col = rank_by if rank_by in frame.columns else "cagr_3y"
    frame = frame.sort_values(sort_col, ascending=False, na_position="last").head(top_n)
    frame = frame.reset_index(drop=True)
    frame.insert(0, "rank", range(1, len(frame) + 1))

    chart_codes = set(frame["scheme_code"].astype(str).tolist())
    nav_series = {k: v for k, v in nav_series.items() if k in chart_codes}
    for code in chart_codes:
        if code in nav_series:
            continue
        try:
            nav_series[code] = client.sync_scheme_nav(code).nav
        except Exception:
            continue

    category_avg = _category_average_nav(nav_series)
    return CategoryRankingResult(
        table=frame,
        nav_series=nav_series,
        category_avg_series=category_avg,
        funds_fetched=len(rows),
        funds_skipped=skipped,
    )


def normalized_nav_frame(nav_series: dict[str, pd.DataFrame], names: dict[str, str]) -> pd.DataFrame:
    """Wide frame of NAV indexed to 100 at the earliest common start."""

    columns: dict[str, pd.Series] = {}
    for code, nav in nav_series.items():
        if nav.empty:
            continue
        ordered = nav.sort_values("nav_date")
        start_nav = float(ordered.iloc[0]["nav"])
        if start_nav <= 0:
            continue
        label = names.get(code, code)
        indexed = ordered["nav"].astype(float) / start_nav * 100.0
        indexed.index = ordered["nav_date"].astype(str)
        columns[label] = indexed
    if not columns:
        return pd.DataFrame()
    frame = pd.DataFrame(columns)
    frame.index.name = "date"
    return frame.sort_index()


def _category_average_nav(nav_series: dict[str, pd.DataFrame]) -> pd.DataFrame | None:
    normalized = normalized_nav_frame(
        nav_series,
        {code: code for code in nav_series},
    )
    if normalized.empty:
        return None
    avg = normalized.mean(axis=1)
    return pd.DataFrame({"category_average": avg})
