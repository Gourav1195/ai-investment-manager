"""Compare held mutual funds against SEBI category peers."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
import pandas as pd

from .mf_nav_client import MfNavClient
from .portfolio_store import PortfolioStore

PERIODS_YEARS = (1, 3, 5)
UNDERPERFORMER_PERCENTILE = 30.0
TOP_PEER_COUNT = 5


@dataclass(frozen=True)
class FundReturnMetrics:
    scheme_code: str
    scheme_name: str
    category: str
    plan_type: str
    option_type: str
    cagr_1y: float | None
    cagr_3y: float | None
    cagr_5y: float | None
    rolling_1y_median: float | None
    percentile_3y: float | None
    rank_3y: int | None
    peer_count_3y: int
    category_avg_3y: float | None
    is_underperformer: bool


@dataclass(frozen=True)
class PeerComparisonReport:
    held_fund: FundReturnMetrics
    peers: pd.DataFrame
    top_peers: pd.DataFrame


def compare_held_fund_to_peers(
    store: PortfolioStore,
    scheme_code: str,
    *,
    client: MfNavClient | None = None,
    max_peers: int = 60,
    sync_master: bool = True,
) -> PeerComparisonReport | None:
    client = client or MfNavClient(store)
    if sync_master and store.scheme_master_count() == 0:
        client.sync_scheme_master_from_amfi()
    held = client.sync_scheme_nav(scheme_code)
    meta = store.get_scheme_meta(scheme_code)
    master = store.get_scheme_master_row(scheme_code)
    category = master.get("category") or held.category or meta.get("category")
    plan_type = master.get("plan_type") or held.plan_type or meta.get("plan_type")
    option_type = master.get("option_type") or held.option_type or meta.get("option_type")
    if not category or not plan_type or not option_type:
        return None

    peer_codes = store.list_peer_scheme_codes(
        category=str(category),
        plan_type=str(plan_type),
        option_type=str(option_type),
        exclude_code=scheme_code,
        limit=max_peers,
    )
    peer_metrics: list[dict[str, object]] = []
    for code in peer_codes:
        try:
            series = client.sync_scheme_nav(code)
        except Exception:
            continue
        metrics = _return_metrics(
            code,
            series.scheme_name,
            str(category),
            str(plan_type),
            str(option_type),
            series.nav,
        )
        if metrics.cagr_3y is not None:
            peer_metrics.append(_metrics_row(metrics))

    held_metrics = _return_metrics(
        scheme_code,
        held.scheme_name,
        str(category),
        str(plan_type),
        str(option_type),
        held.nav,
    )
    peer_frame = pd.DataFrame(peer_metrics)
    if not peer_frame.empty and held_metrics.cagr_3y is not None:
        peer_frame = peer_frame.sort_values("cagr_3y", ascending=False).reset_index(drop=True)
        rank = int((peer_frame["cagr_3y"] > held_metrics.cagr_3y).sum()) + 1
        count = len(peer_frame) + 1
        percentile = 100.0 * (1.0 - (rank - 1) / max(count - 1, 1))
        category_avg = float(peer_frame["cagr_3y"].mean())
        under = percentile < UNDERPERFORMER_PERCENTILE
        held_metrics = replace(
            held_metrics,
            rank_3y=rank,
            peer_count_3y=count,
            percentile_3y=percentile,
            category_avg_3y=category_avg,
            is_underperformer=under,
        )
    top = peer_frame.head(TOP_PEER_COUNT) if not peer_frame.empty else peer_frame
    return PeerComparisonReport(held_fund=held_metrics, peers=peer_frame, top_peers=top)


def peer_reports_to_frame(reports: list[PeerComparisonReport]) -> pd.DataFrame:
    return pd.DataFrame([_metrics_row(report.held_fund) for report in reports])


def compare_manual_funds(
    store: PortfolioStore,
    scheme_codes: list[str],
    *,
    client: MfNavClient | None = None,
) -> pd.DataFrame:
    client = client or MfNavClient(store)
    rows: list[dict[str, object]] = []
    for code in scheme_codes:
        try:
            series = client.sync_scheme_nav(code)
        except Exception:
            continue
        meta = store.get_scheme_meta(code)
        metrics = _return_metrics(
            code,
            series.scheme_name,
            str(meta.get("category") or series.category or "Unknown"),
            str(meta.get("plan_type") or series.plan_type or "Unknown"),
            str(meta.get("option_type") or series.option_type or "Unknown"),
            series.nav,
        )
        rows.append(_metrics_row(metrics))
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values("cagr_3y", ascending=False, na_position="last")


def compare_portfolio_mutual_funds(
    store: PortfolioStore,
    *,
    client: MfNavClient | None = None,
    sync_master: bool = True,
) -> list[PeerComparisonReport]:
    client = client or MfNavClient(store)
    if sync_master and store.scheme_master_count() == 0:
        client.sync_scheme_master_from_amfi()
    holdings = store.list_mf_holdings()
    if holdings.empty:
        return []
    reports: list[PeerComparisonReport] = []
    for record in holdings.to_dict(orient="records"):
        code = record.get("scheme_code")
        if not code or not str(code).strip():
            continue
        if client.allow_network is False and not store.has_nav_history(str(code)):
            continue
        report = compare_held_fund_to_peers(store, str(code), client=client, sync_master=sync_master)
        if report is not None:
            reports.append(report)
    return reports


def _return_metrics(
    scheme_code: str,
    scheme_name: str,
    category: str,
    plan_type: str,
    option_type: str,
    nav: pd.DataFrame,
) -> FundReturnMetrics:
    cagr_1y = _cagr(nav, years=1)
    cagr_3y = _cagr(nav, years=3)
    cagr_5y = _cagr(nav, years=5)
    rolling = _rolling_1y_median(nav)
    return FundReturnMetrics(
        scheme_code=scheme_code,
        scheme_name=scheme_name,
        category=category,
        plan_type=plan_type,
        option_type=option_type,
        cagr_1y=cagr_1y,
        cagr_3y=cagr_3y,
        cagr_5y=cagr_5y,
        rolling_1y_median=rolling,
        percentile_3y=None,
        rank_3y=None,
        peer_count_3y=0,
        category_avg_3y=None,
        is_underperformer=False,
    )


def _metrics_row(metrics: FundReturnMetrics) -> dict[str, object]:
    return {
        "scheme_code": metrics.scheme_code,
        "scheme_name": metrics.scheme_name,
        "category": metrics.category,
        "plan_type": metrics.plan_type,
        "option_type": metrics.option_type,
        "cagr_1y": metrics.cagr_1y,
        "cagr_3y": metrics.cagr_3y,
        "cagr_5y": metrics.cagr_5y,
        "rolling_1y_median": metrics.rolling_1y_median,
        "percentile_3y": metrics.percentile_3y,
        "rank_3y": metrics.rank_3y,
        "peer_count_3y": metrics.peer_count_3y,
        "category_avg_3y": metrics.category_avg_3y,
        "is_underperformer": metrics.is_underperformer,
    }


def _cagr(nav: pd.DataFrame, *, years: int) -> float | None:
    if nav.empty:
        return None
    ordered = nav.sort_values("nav_date")
    end_row = ordered.iloc[-1]
    end_date = date.fromisoformat(str(end_row["nav_date"]))
    start_date = end_date - timedelta(days=int(365.25 * years))
    subset = ordered[ordered["nav_date"].astype(str) <= start_date.isoformat()]
    if subset.empty:
        return None
    start_row = subset.iloc[-1]
    start_nav = float(start_row["nav"])
    end_nav = float(end_row["nav"])
    if start_nav <= 0 or end_nav <= 0:
        return None
    elapsed_years = (end_date - date.fromisoformat(str(start_row["nav_date"]))).days / 365.25
    if elapsed_years < years * 0.9:
        return None
    return (end_nav / start_nav) ** (1.0 / years) - 1.0


def _rolling_1y_median(nav: pd.DataFrame) -> float | None:
    if nav.empty:
        return None
    ordered = nav.sort_values("nav_date").copy()
    ordered["nav_date"] = ordered["nav_date"].astype(str)
    values: list[float] = []
    dates = ordered["nav_date"].tolist()
    navs = ordered["nav"].astype(float).tolist()
    for index, nav_date in enumerate(dates):
        end_nav = navs[index]
        end_dt = date.fromisoformat(nav_date)
        start_dt = end_dt - timedelta(days=365)
        start_nav = None
        for prior_date, prior_nav in zip(dates[: index + 1], navs[: index + 1]):
            if date.fromisoformat(prior_date) <= start_dt:
                start_nav = prior_nav
        if start_nav is None or start_nav <= 0 or end_nav <= 0:
            continue
        years = (end_dt - date.fromisoformat(dates[0])).days / 365.25
        if years < 1:
            continue
        values.append((end_nav / start_nav) - 1.0)
    if not values:
        return None
    values.sort()
    mid = len(values) // 2
    if len(values) % 2:
        return values[mid]
    return (values[mid - 1] + values[mid]) / 2.0
