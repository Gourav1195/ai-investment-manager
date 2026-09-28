"""Streamlit dashboard for persisted India long-term research."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import streamlit as st

from .dashboard_data import (
    calibration_report,
    category_scores,
    explanation_for_snapshot,
    filter_options,
    fundamental_metrics,
    orchestration_calibration_options,
    orchestration_calibration_summary,
    orchestration_runs,
    overview_metrics,
    profile_versions,
    snapshot_detail,
    snapshot_summary_frame,
)
from .research import ResearchStore

DEFAULT_DATABASE = Path("work/research.db")


def main() -> None:
    st.set_page_config(
        page_title="India Research Dashboard",
        page_icon="📊",
        layout="wide",
    )
    st.title("India Long-Term Research Dashboard")
    st.caption(
        "Research classifications for further investigation. Not investment advice. "
        "Scores and rankings are deterministic and auditable."
    )

    default_database = Path(os.environ.get("INVESTING_RESEARCH_DB", DEFAULT_DATABASE))
    with st.sidebar:
        st.header("Database")
        database_path = Path(
            st.text_input("Research database", value=str(default_database))
        )
        if not database_path.exists():
            st.error(f"Database not found: {database_path}")
            st.stop()

        store = ResearchStore(database_path)
        options = filter_options(store)
        st.header("Filters")
        symbol = st.selectbox(
            "Symbol",
            ["All"] + options["symbols"],
            index=0,
        )
        as_of = st.selectbox(
            "As-of date",
            ["All"] + options["as_of_dates"],
            index=0,
        )
        research_view = st.selectbox(
            "Research view",
            ["All"] + options["research_views"],
            index=0,
        )

    snapshots_tab, profile_tab, orchestration_tab = st.tabs(
        ["Snapshots", "Profile review", "Orchestration runs"]
    )

    with snapshots_tab:
        metrics = overview_metrics(store)
        _render_overview(metrics)

        selected_symbol = None if symbol == "All" else symbol
        selected_as_of = None if as_of == "All" else as_of
        selected_view = None if research_view == "All" else research_view
        summary = snapshot_summary_frame(
            store,
            symbol=selected_symbol,
            as_of=selected_as_of,
            research_view=selected_view,
        )

        st.subheader("Research snapshots")
        if summary.empty:
            st.info(
                "No persisted research snapshots match the current filters. "
                "Run `orchestrate` or `walkforward` with `--persist` first."
            )
        else:
            st.dataframe(summary, use_container_width=True, hide_index=True)
            detail_symbol = selected_symbol or summary.iloc[0]["symbol"]
            detail_as_of = selected_as_of or summary.iloc[0]["as_of"]
            with st.expander(
                f"Detail: {detail_symbol} as of {detail_as_of}", expanded=True
            ):
                _render_detail(store, symbol=detail_symbol, as_of=detail_as_of)

    with profile_tab:
        _render_profile_review(database_path, store)

    with orchestration_tab:
        _render_orchestration_runs(database_path)


def _render_profile_review(database_path: Path, store: ResearchStore) -> None:
    st.subheader("Latest orchestration calibration")
    run_options = orchestration_calibration_options(database_path)
    if not run_options:
        st.info(
            "No orchestration runs recorded yet. Run `orchestrate` or "
            "`schedule run-quarterly` with `--persist` to review universe calibration."
        )
    else:
        labels = {option["run_key"]: option["label"] for option in run_options}
        selected_run = st.selectbox(
            "Orchestration run",
            options=list(labels.keys()),
            format_func=lambda run_key: labels[run_key],
        )
        summary = orchestration_calibration_summary(
            database_path,
            run_key=selected_run,
            store=store,
        )
        if summary is None:
            st.warning(
                "No persisted snapshots match this orchestration run's as-of dates."
            )
        else:
            columns = st.columns(4)
            columns[0].metric("Snapshots persisted", summary.records_persisted)
            columns[1].metric("Symbols evaluated", summary.symbols_evaluated)
            columns[2].metric("Skipped symbols", summary.skipped_count)
            columns[3].metric(
                "Calibration source",
                summary.source,
                help="Persisted at run time or recomputed from stored snapshots.",
            )
            st.caption(
                f"{summary.index_name} | created {summary.created_at} | "
                f"as-of dates: {', '.join(summary.as_of_dates)}"
            )
            _render_calibration_tables(summary.report)
            st.info(
                "Review threshold suggestions, export with `calibrate --report thresholds`, "
                "then apply a new version with `profiles apply --activate`."
            )

    st.subheader("Scoring profile versions")
    versions = profile_versions(database_path)
    if versions:
        st.dataframe(
            pd.DataFrame([item.__dict__ for item in versions]),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No saved scoring profile versions yet. Use `profiles apply` after calibration.")

    st.subheader("All-snapshot calibration review")
    report = calibration_report(store)
    if report.score_buckets.empty and report.threshold_suggestions.empty:
        st.info(
            "No persisted snapshots are available for calibration review. "
            "Run `orchestrate` or `calibrate` after a universe walk-forward."
        )
        return

    _render_calibration_tables(report)


def _render_calibration_tables(report) -> None:
    st.markdown("**Score buckets**")
    st.dataframe(report.score_buckets, use_container_width=True, hide_index=True)
    if not report.score_buckets.empty and "avg_excess_return" in report.score_buckets:
        chart = report.score_buckets.set_index("research_view")[["avg_excess_return"]]
        st.bar_chart(chart)

    st.markdown("**Threshold suggestions**")
    st.dataframe(
        report.threshold_suggestions,
        use_container_width=True,
        hide_index=True,
    )


def _render_orchestration_runs(database_path: Path) -> None:
    st.subheader("Universe orchestration runs")
    runs = orchestration_runs(database_path)
    if runs.empty:
        st.info(
            "No orchestration runs recorded yet. Schedule `orchestrate` for a full "
            "Nifty universe walk-forward."
        )
        return
    st.dataframe(runs, use_container_width=True, hide_index=True)


def _render_overview(metrics: dict) -> None:
    columns = st.columns(5)
    columns[0].metric("Evaluations", metrics.get("evaluations", 0))
    columns[1].metric("Snapshots", metrics.get("snapshots", 0))
    columns[2].metric("Explanations", metrics.get("explanations", 0))
    columns[3].metric("Symbols", metrics.get("symbols", 0))
    columns[4].metric("Latest as-of", metrics.get("latest_as_of") or "—")

    views = metrics.get("research_views") or {}
    if views:
        view_frame = pd.DataFrame(
            [{"research_view": key, "count": value} for key, value in views.items()]
        )
        st.bar_chart(view_frame.set_index("research_view"))


def _render_detail(store: ResearchStore, *, symbol: str, as_of: str) -> None:
    detail = snapshot_detail(store, symbol=symbol, as_of=as_of)
    if detail is None:
        st.warning("No snapshot detail is available for the selected company.")
        return

    snapshot = detail["snapshot"]
    left, right = st.columns(2)

    with left:
        st.markdown("**Category scores**")
        scores = category_scores(snapshot)
        if scores.empty:
            st.write("No category scores are available.")
        else:
            st.bar_chart(scores.set_index("category"))

    with right:
        st.markdown("**Benchmark comparison**")
        comparison = pd.DataFrame(
            [
                {
                    "metric": "Forward return",
                    "value": snapshot.get("forward_return"),
                },
                {
                    "metric": "Benchmark forward return",
                    "value": snapshot.get("benchmark_forward_return"),
                },
                {
                    "metric": "Excess vs benchmark",
                    "value": snapshot.get("excess_forward_return"),
                },
                {
                    "metric": "Portfolio forward return",
                    "value": snapshot.get("portfolio_forward_return"),
                },
                {
                    "metric": "Excess vs portfolio",
                    "value": snapshot.get("excess_portfolio_forward_return"),
                },
            ]
        )
        comparison["value"] = comparison["value"].map(_display_return)
        st.dataframe(comparison, use_container_width=True, hide_index=True)

    fundamentals = fundamental_metrics(snapshot)
    if not fundamentals.empty:
        st.markdown("**Fundamentals and valuation**")
        st.dataframe(fundamentals, use_container_width=True, hide_index=True)

    explanation = detail.get("explanation") or explanation_for_snapshot(
        store, symbol=symbol, as_of=as_of
    )
    if explanation is None:
        st.info(
            "No persisted explanation exists for this snapshot. "
            "Re-run research with `--explain` or use the `explain` CLI command."
        )
        return

    st.markdown("**Score drivers**")
    if explanation["score_drivers"]:
        for item in explanation["score_drivers"]:
            st.write(f"- {item}")
    else:
        st.write("No score drivers recorded.")

    st.markdown("**Risk flags**")
    if explanation["risk_flags"]:
        for item in explanation["risk_flags"]:
            st.warning(item)
    else:
        st.success("No material risk flags recorded.")

    if explanation["source_documents"]:
        st.markdown("**Source documents**")
        documents = pd.DataFrame(explanation["source_documents"])
        st.dataframe(documents, use_container_width=True, hide_index=True)


def _display_return(value) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{float(value) * 100:.1f}%"


if __name__ == "__main__":
    main()
