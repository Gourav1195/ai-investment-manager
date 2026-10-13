"""Hero metrics and plain-English portfolio insights."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .mf_peer_comparison import PeerComparisonReport
from .portfolio_analytics import PortfolioSummary, estimate_portfolio_history
from .portfolio_dashboard_data import load_mf_peer_reports, load_portfolio_summary, portfolio_has_data
from .portfolio_store import PortfolioStore


@dataclass(frozen=True)
class WealthSnapshot:
    total_value: float | None
    total_pnl: float | None
    xirr: float | None
    today_change: float | None
    today_change_pct: float | None
    has_portfolio: bool


def load_wealth_snapshot(
    portfolio_path: Path,
    research_path: Path | None,
    *,
    refresh_prices: bool = True,
) -> tuple[WealthSnapshot, PortfolioSummary | None, list[PeerComparisonReport]]:
    if not portfolio_path.exists() or not portfolio_has_data(portfolio_path):
        return (
            WealthSnapshot(None, None, None, None, None, False),
            None,
            [],
        )
    research_db = research_path if research_path and research_path.exists() else None
    try:
        summary, comparison = load_portfolio_summary(
            portfolio_path,
            research_db,
            refresh_prices=refresh_prices,
            benchmark_index="NIFTY 50",
        )
    except Exception:
        return (
            WealthSnapshot(None, None, None, None, None, True),
            None,
            [],
        )

    today_change, today_pct = _today_change(portfolio_path, summary, comparison)
    reports: list[PeerComparisonReport] = []
    try:
        reports = load_mf_peer_reports(portfolio_path, sync_master=False)
    except Exception:
        reports = []

    snapshot = WealthSnapshot(
        total_value=_float_or_none(summary.totals.get("current_value")),
        total_pnl=_float_or_none(summary.totals.get("pnl")),
        xirr=summary.xirr,
        today_change=today_change,
        today_change_pct=today_pct,
        has_portfolio=True,
    )
    return snapshot, summary, reports


def plain_english_insights(reports: list[PeerComparisonReport], limit: int = 4) -> list[str]:
    insights: list[str] = []
    for report in reports:
        held = report.held_fund
        short_name = _short_fund_name(held.scheme_name)
        category = _short_category(held.category)
        if held.percentile_3y is not None:
            beat = int(round(held.percentile_3y))
            if beat >= 50:
                insights.append(
                    f"Your <strong>{short_name}</strong> fund beat about "
                    f"<strong>{beat}%</strong> of its {category} peers over 3 years."
                )
            else:
                insights.append(
                    f"Your <strong>{short_name}</strong> fund trailed most {category} peers "
                    f"over 3 years (around the <strong>{beat}</strong>th percentile)."
                )
        elif held.cagr_3y is not None:
            insights.append(
                f"<strong>{short_name}</strong> returned about "
                f"<strong>{held.cagr_3y * 100:.1f}%</strong> per year over the last 3 years."
            )
        if len(insights) >= limit:
            break
    if not insights and reports:
        insights.append(
            "Your mutual funds are loaded — open **My mutual funds** or **MF peers** in the menu."
        )
    return insights[:limit]


def _today_change(
    portfolio_path: Path,
    summary: PortfolioSummary,
    comparison: pd.DataFrame | None,
) -> tuple[float | None, float | None]:
    if comparison is not None and len(comparison) >= 2:
        frame = comparison.copy()
        if "date" not in frame.columns:
            return None, None
        date_col = frame["date"]
        if isinstance(date_col, pd.DataFrame):
            frame = frame.loc[:, ~frame.columns.duplicated()].copy()
        ordered = frame.sort_values("date")
        if "portfolio_indexed" not in ordered.columns:
            return None, None
        last = float(ordered.iloc[-1]["portfolio_indexed"])
        prev = float(ordered.iloc[-2]["portfolio_indexed"])
        if prev:
            pct = (last - prev) / prev
            total = _float_or_none(summary.totals.get("current_value"))
            if total is not None:
                return total * pct, pct
    store = PortfolioStore(portfolio_path)
    trades = store.list_equity_trades()
    history = estimate_portfolio_history(store, trades)
    if len(history) >= 2:
        last_val = float(history.iloc[-1]["portfolio_value"])
        prev_val = float(history.iloc[-2]["portfolio_value"])
        if prev_val:
            change = last_val - prev_val
            return change, change / prev_val
    return None, None


def _short_fund_name(name: str) -> str:
    text = name.replace("Direct Plan", "").replace("Growth Option", "").strip()
    if len(text) > 42:
        return text[:39] + "…"
    return text


def _short_category(category: str) -> str:
    text = category or "category"
    for prefix in ("Equity Scheme - ", "Hybrid Scheme - ", "Other Scheme - "):
        if text.startswith(prefix):
            return text[len(prefix) :]
    return text


def _float_or_none(value: object) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
