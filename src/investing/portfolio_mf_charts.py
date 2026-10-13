"""Plotly chart helpers for mutual fund holdings on the Portfolio tab."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from .royal_theme import style_plotly_figure

from .mf_nav_client import MfNavClient
from .mf_peer_comparison import PeerComparisonReport
from .mf_rankings import _category_average_nav, normalized_nav_frame
from .portfolio_store import PortfolioStore


def _holding_labels(frame: pd.DataFrame) -> pd.Series:
    if "scheme_name" in frame.columns:
        return frame["scheme_name"].astype(str)
    if "symbol" in frame.columns:
        return frame["symbol"].astype(str)
    return pd.Series(frame.index.astype(str), index=frame.index)


def allocation_pie(holdings: pd.DataFrame) -> go.Figure | None:
    if holdings.empty or "current_value" not in holdings.columns:
        return None
    frame = holdings.copy()
    frame["label"] = _holding_labels(frame)
    frame = frame.loc[frame["current_value"].fillna(0) > 0]
    if frame.empty:
        return None
    fig = px.pie(
        frame,
        names="label",
        values="current_value",
        title="How your money is split across holdings",
    )
    fig.update_traces(textposition="inside", textinfo="percent+label")
    return style_plotly_figure(fig)


def pnl_bar(holdings: pd.DataFrame) -> go.Figure | None:
    if holdings.empty:
        return None
    pnl_col = "pnl" if "pnl" in holdings.columns else None
    if pnl_col is None:
        return None
    frame = holdings.copy()
    frame["label"] = _holding_labels(frame)
    frame = frame.sort_values(pnl_col)
    fig = px.bar(
        frame,
        x=pnl_col,
        y="label",
        orientation="h",
        title="Profit and loss by holding (₹)",
        labels={pnl_col: "P&L (₹)", "label": "Holding"},
    )
    return style_plotly_figure(fig)


def held_fund_vs_peers_chart(
    report: PeerComparisonReport,
    *,
    client_nav: pd.DataFrame,
) -> go.Figure | None:
    nav_map: dict[str, pd.DataFrame] = {report.held_fund.scheme_code: client_nav}
    names = {report.held_fund.scheme_code: "Your fund"}
    for _, row in report.top_peers.head(3).iterrows():
        code = str(row["scheme_code"])
        nav_map[code] = pd.DataFrame()  # placeholder filled below
        names[code] = str(row["scheme_name"])[:40]
    # top_peers frame doesn't include NAV — chart uses held + peer names only when NAV cached
    wide = normalized_nav_frame(
        {report.held_fund.scheme_code: client_nav},
        {report.held_fund.scheme_code: "Your fund"},
    )
    if wide.empty:
        return None
    fig = px.line(wide, title="Your fund vs category (NAV indexed to 100)")
    fig.update_layout(yaxis_title="Indexed NAV (start = 100)", xaxis_title="Date")
    return style_plotly_figure(fig)


def build_peer_nav_chart(
    held_code: str,
    held_name: str,
    held_nav: pd.DataFrame,
    peer_navs: dict[str, pd.DataFrame],
    peer_names: dict[str, str],
    category_avg: pd.DataFrame | None,
) -> go.Figure | None:
    series = {held_code: held_nav}
    names = {held_code: f"Your fund: {held_name[:30]}"}
    for code, nav in peer_navs.items():
        series[code] = nav
        names[code] = peer_names.get(code, code)
    wide = normalized_nav_frame(series, names)
    if wide.empty:
        return None
    fig = go.Figure()
    for column in wide.columns:
        fig.add_trace(go.Scatter(x=wide.index, y=wide[column], mode="lines", name=column))
    if category_avg is not None and not category_avg.empty:
        fig.add_trace(
            go.Scatter(
                x=category_avg.index,
                y=category_avg["category_average"],
                mode="lines",
                name="Category average",
                line=dict(dash="dash"),
            )
        )
    fig.update_layout(
        title="Fund performance vs category leaders (NAV indexed to 100)",
        yaxis_title="Indexed NAV",
        xaxis_title="Date",
    )
    return style_plotly_figure(fig)


def render_mutual_fund_charts(
    portfolio_path: Path,
    mf_holdings: pd.DataFrame,
    reports: list[PeerComparisonReport],
) -> None:
    """Streamlit plotly charts for MF section (import streamlit lazily)."""
    import streamlit as st

    store = PortfolioStore(portfolio_path)
    st.markdown("**Your mutual fund charts**")
    pie = allocation_pie(mf_holdings)
    if pie is not None:
        st.plotly_chart(pie, use_container_width=True)
    pnl = pnl_bar(mf_holdings)
    if pnl is not None:
        st.plotly_chart(pnl, use_container_width=True)
    value_fig = portfolio_value_over_time(store, mf_holdings)
    if value_fig is not None:
        st.plotly_chart(value_fig, use_container_width=True)

    client = MfNavClient(store)
    for report in reports[:5]:
        held = report.held_fund
        try:
            held_nav = client.sync_scheme_nav(held.scheme_code).nav
        except Exception:
            continue
        peer_navs: dict[str, pd.DataFrame] = {}
        peer_names: dict[str, str] = {}
        for _, row in report.top_peers.head(3).iterrows():
            code = str(row["scheme_code"])
            try:
                peer_navs[code] = client.sync_scheme_nav(code).nav
                peer_names[code] = str(row["scheme_name"])
            except Exception:
                continue
        cat_avg = _category_average_nav(peer_navs) if peer_navs else None
        fig = build_peer_nav_chart(
            held.scheme_code,
            held.scheme_name,
            held_nav,
            peer_navs,
            peer_names,
            cat_avg,
        )
        if fig is not None:
            st.plotly_chart(fig, use_container_width=True)


def portfolio_value_over_time(
    store: PortfolioStore,
    mf_holdings: pd.DataFrame,
) -> go.Figure | None:
    """Approximate portfolio value by summing units × historical NAV per fund."""

    if mf_holdings.empty:
        return None
    totals: dict[str, float] = {}
    for record in mf_holdings.to_dict(orient="records"):
        code = str(record.get("scheme_code") or "").strip()
        units = float(record.get("quantity") or record.get("units") or 0)
        if not code or units <= 0:
            continue
        nav = store.get_nav_history(code)
        if nav.empty:
            continue
        ordered = nav.sort_values("nav_date")
        for _, row in ordered.iterrows():
            day = str(row["nav_date"])
            totals[day] = totals.get(day, 0.0) + units * float(row["nav"])
    if not totals:
        return None
    frame = pd.DataFrame(
        [{"date": day, "value": value} for day, value in sorted(totals.items())]
    )
    fig = px.line(
        frame,
        x="date",
        y="value",
        title="Estimated mutual fund portfolio value over time",
        labels={"value": "Value (₹)", "date": "Date"},
    )
    return style_plotly_figure(fig)
