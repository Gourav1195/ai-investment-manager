"""CSV portfolio report for download (no paid PDF APIs)."""

from __future__ import annotations

import io
import zipfile
from datetime import date

import pandas as pd

from .portfolio_analytics import PortfolioSummary
from .portfolio_capital_gains import build_capital_gains_report
from .portfolio_concentration import build_concentration_tables, mf_category_concentration
from .portfolio_goals import GoalProgressRow
from .portfolio_sip_calendar import SipSchedule, upcoming_sip_dates
from .portfolio_store import PortfolioStore


def build_portfolio_report_zip(
    summary: PortfolioSummary,
    store: PortfolioStore,
    *,
    goal_rows: list[GoalProgressRow] | None = None,
    sip_schedules: list[SipSchedule] | None = None,
    as_of: date | None = None,
) -> bytes:
    """Pack holdings, allocation, tax, and optional goal/SIP sheets into a zip."""

    as_of = as_of or date.today()
    buffers: dict[str, pd.DataFrame] = {
        "summary_totals.csv": _totals_frame(summary),
        "equity_holdings.csv": summary.equity,
        "mutual_fund_holdings.csv": summary.mutual_funds,
        "combined_holdings.csv": summary.combined,
    }
    if summary.mf_fund_xirr is not None and not summary.mf_fund_xirr.empty:
        buffers["mf_fund_xirr.csv"] = summary.mf_fund_xirr
    if summary.mf_sips is not None and not summary.mf_sips.empty:
        buffers["sip_history.csv"] = summary.mf_sips

    top, _ = build_concentration_tables(summary.combined)
    if not top.empty:
        buffers["concentration_top_holdings.csv"] = top

    categories = mf_category_concentration(summary.mutual_funds, store.get_scheme_meta)
    if not categories.empty:
        buffers["mf_category_allocation.csv"] = categories

    if sip_schedules:
        upcoming = upcoming_sip_dates(sip_schedules, as_of=as_of)
        if not upcoming.empty:
            buffers["sip_upcoming_90d.csv"] = upcoming

    if goal_rows:
        buffers["goals_progress.csv"] = pd.DataFrame(
            [
                {
                    "name": row.name,
                    "target_inr": row.target_inr,
                    "target_date": row.target_date.isoformat(),
                    "progress_pct": row.progress_pct,
                    "projected_inr": row.projected_inr,
                    "required_monthly_inr": row.required_monthly_inr,
                    "status": row.status,
                }
                for row in goal_rows
            ]
        )

    stock_prices = {
        str(row["identifier"]): float(row["market_price"])
        for row in summary.equity.to_dict(orient="records")
        if row.get("market_price") is not None
    }
    navs = {
        str(row.get("scheme_code") or ""): float(row["market_price"])
        for row in summary.mutual_funds.to_dict(orient="records")
        if row.get("market_price") is not None and row.get("scheme_code")
    }
    scheme_categories: dict[str, str] = {}
    for row in summary.mutual_funds.to_dict(orient="records"):
        code = str(row.get("scheme_code") or "").strip()
        if not code:
            continue
        meta = store.get_scheme_meta(code)
        if meta.get("category"):
            scheme_categories[code] = str(meta["category"])

    tax = build_capital_gains_report(
        store,
        stock_prices=stock_prices,
        navs=navs,
        scheme_categories=scheme_categories,
    )
    if not tax["unrealized"].empty:
        buffers["capital_gains_unrealized.csv"] = tax["unrealized"]
    if not tax["realized"].empty:
        buffers["capital_gains_realized.csv"] = tax["realized"]
    if not tax["fiscal_year_estimates"].empty:
        buffers["capital_gains_fy_estimates.csv"] = tax["fiscal_year_estimates"]

    meta = pd.DataFrame(
        [{"report_date": as_of.isoformat(), "note": "Illustrative tax figures; not advice."}]
    )
    buffers["README.csv"] = meta

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, frame in buffers.items():
            zf.writestr(name, frame.to_csv(index=False).encode("utf-8"))
    return archive.getvalue()


def _totals_frame(summary: PortfolioSummary) -> pd.DataFrame:
    return pd.DataFrame([summary.totals])
