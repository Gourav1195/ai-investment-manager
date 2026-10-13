"""Streamlit UI for top mutual fund rankings."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from .friendly_copy import TERM_HELP
from .royal_theme import render_empty_state, style_plotly_figure

from .mf_nav_client import MfNavClient
from .mf_rankings import (
    CATEGORY_CHOICES,
    MAX_FUNDS_TO_RANK,
    list_categories_from_master,
    normalized_nav_frame,
    rank_funds_in_category,
)
from .portfolio_dashboard_data import format_mf_returns_table
from .portfolio_store import PortfolioStore


def render_top_mutual_funds_tab(portfolio_path: Path) -> None:
    st.subheader("Top mutual funds by category")
    st.caption(
        "Ranks funds using public AMFI categories and NAV history (mfapi.in). "
        "Direct and Growth plans are compared separately from Regular and dividend options."
    )
    portfolio_path.parent.mkdir(parents=True, exist_ok=True)
    store = PortfolioStore(portfolio_path)

    if store.scheme_master_count() == 0:
        st.info("First, load the fund list. Then choose a category and compare returns.")
    sync = st.button(
        "Refresh fund list", key="mf_rank_sync_master",
        help="Downloads the public AMFI fund list. Refresh about once a week.",
    )
    if sync:
        client = MfNavClient(store)
        with st.spinner("Downloading AMFI fund list…"):
            try:
                count = client.sync_scheme_master_from_amfi()
                st.success(f"Loaded {count:,} funds from AMFI.")
            except Exception as error:  # noqa: BLE001
                st.error(f"Could not download AMFI list: {error}")
                st.info("Try again later or upload a portfolio backup that already includes fund data.")
                return

    categories = list_categories_from_master(store)
    options = [c for c in CATEGORY_CHOICES if c != "All categories"]
    if categories:
        extra = [c for c in categories if c not in options]
        options = options + extra[:30]

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        category = st.selectbox(
            "Category",
            options=options,
            index=0,
            key="mf_rank_category",
        )
    with col2:
        plan = st.selectbox("Plan", ["Direct", "Regular"], index=0, key="mf_rank_plan")
    with col3:
        option = st.selectbox("Option", ["Growth", "IDCW"], index=0, key="mf_rank_option")
    with col4:
        rank_by = st.selectbox(
            "Sort funds by",
            ["cagr_3y", "cagr_5y", "cagr_1y"],
            format_func=lambda x: {
                "cagr_1y": "1-year average growth",
                "cagr_3y": "3-year average growth",
                "cagr_5y": "5-year average growth",
            }[x],
            index=0,
            key="mf_rank_metric",
            help=TERM_HELP["cagr"],
        )
    top_n = st.slider("Show top N funds", min_value=5, max_value=25, value=10, key="mf_rank_topn")

    if st.button("Load rankings", type="primary", key="mf_rank_load"):
        st.session_state["mf_rank_run"] = True

    if not st.session_state.get("mf_rank_run"):
        render_empty_state(
            "🏆",
            "Discover top funds in each category",
            "Pick a category above, then tap Load rankings to compare 1-year, 3-year, and 5-year returns.",
        )
        return

    progress = st.progress(0.0, text="Starting…")
    bar = st.empty()

    def on_progress(fraction: float, message: str) -> None:
        progress.progress(fraction, text=message)
        bar.caption(message)

    client = MfNavClient(store)
    try:
        result = rank_funds_in_category(
            store,
            category=category,
            plan_type=plan,
            option_type=option,
            rank_by=rank_by,
            top_n=top_n,
            max_candidates=min(MAX_FUNDS_TO_RANK, 40),
            client=client,
            progress=on_progress,
        )
    except Exception as error:  # noqa: BLE001
        st.error(f"Could not rank funds: {error}")
        return
    progress.progress(1.0, text="Done")
    if result.table.empty:
        st.warning(
            "No funds with enough NAV history matched these filters. "
            "Try another category or refresh the AMFI list."
        )
        return

    st.caption(
        f"Compared {result.funds_fetched} funds "
        f"({result.funds_skipped} skipped due to missing data)."
    )
    display = format_mf_returns_table(result.table)
    st.dataframe(display, use_container_width=True, hide_index=True)

    metric_label = {"cagr_1y": "1Y", "cagr_3y": "3Y", "cagr_5y": "5Y"}[rank_by]
    chart_frame = result.table.head(min(10, len(result.table))).copy()
    chart_frame["label"] = chart_frame["scheme_name"].astype(str).str.slice(0, 35)
    fig_bar = px.bar(
        chart_frame,
        x="label",
        y=rank_by,
        title=f"Top funds by {metric_label} return",
        labels={rank_by: f"{metric_label} CAGR", "label": "Fund"},
    )
    fig_bar.update_layout(xaxis_tickangle=-45)
    st.plotly_chart(style_plotly_figure(fig_bar), use_container_width=True)

    names = {
        str(row["scheme_code"]): str(row["scheme_name"])[:35]
        for row in result.table.to_dict(orient="records")
    }
    wide = normalized_nav_frame(result.nav_series, names)
    if not wide.empty:
        fig_line = px.line(
            wide,
            title="NAV growth (each line starts at 100)",
        )
        fig_line.update_layout(yaxis_title="Indexed NAV", xaxis_title="Date")
        st.plotly_chart(style_plotly_figure(fig_line), use_container_width=True)
