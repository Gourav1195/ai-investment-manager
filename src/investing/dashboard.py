"""Streamlit dashboard for persisted India long-term research."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import streamlit as st

from .dashboard_data import (
    activate_scoring_profile,
    calibration_report,
    category_scores,
    default_profile_diff_versions,
    explanation_for_snapshot,
    filter_options,
    fundamental_metrics,
    orchestration_calibration_options,
    orchestration_calibration_summary,
    orchestration_runs,
    overview_metrics,
    profile_calibration_alignment_frame,
    profile_version_can_activate,
    profile_version_diff_frame,
    profile_version_is_active,
    profile_version_option_list,
    profile_versions,
    snapshot_detail,
    snapshot_summary_frame,
)
from .portfolio_dashboard_data import (
    format_holdings_table,
    format_mf_returns_table,
    list_mf_scheme_options,
    load_manual_mf_comparison,
    load_mf_peer_reports,
    load_portfolio_summary,
    portfolio_has_data,
)
from .research import ResearchStore

DEFAULT_DATABASE = Path("work/research.db")
DEFAULT_PORTFOLIO_DATABASE = Path("work/portfolio.db")


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
    default_portfolio = Path(
        os.environ.get("INVESTING_PORTFOLIO_DB", DEFAULT_PORTFOLIO_DATABASE)
    )
    with st.sidebar:
        st.header("Databases")
        database_path = Path(
            st.text_input("Research database", value=str(default_database))
        )
        portfolio_path = Path(
            st.text_input("Portfolio database", value=str(default_portfolio))
        )
        store = ResearchStore(database_path) if database_path.exists() else None
        if store is None:
            st.warning(
                f"Research database not found: {database_path}. "
                "Research tabs stay empty until you persist walk-forward results."
            )
        options = filter_options(store) if store is not None else {
            "symbols": [],
            "as_of_dates": [],
            "research_views": [],
        }
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

    snapshots_tab, profile_tab, orchestration_tab, portfolio_tab = st.tabs(
        ["Snapshots", "Profile review", "Orchestration runs", "Portfolio"]
    )

    with snapshots_tab:
        if store is None:
            st.info("Load or create a research database to browse snapshots.")
        else:
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
        if store is None:
            st.info("Profile review requires a research database.")
        else:
            _render_profile_review(database_path, store)

    with orchestration_tab:
        _render_orchestration_runs(database_path)

    with portfolio_tab:
        _render_portfolio(portfolio_path, database_path)


def _render_portfolio(portfolio_path: Path, research_path: Path) -> None:
    st.subheader("Zerodha portfolio tracker")
    st.caption(
        "Imports from Zerodha Console or read-only Kite Connect sync. "
        "Not investment advice."
    )
    if not portfolio_path.exists():
        st.info(
            f"No portfolio database at {portfolio_path}. "
            "Run `python -m src.investing.cli portfolio load-examples` or import "
            "Console CSV exports first."
        )
        return
    if not portfolio_has_data(portfolio_path):
        st.info(
            "Portfolio database is empty. Import equity holdings, tradebook, and "
            "mutual fund files from Zerodha Console."
        )
        return

    benchmark_index = st.selectbox(
        "Benchmark",
        ["NIFTY 50", "NIFTY 100", "NIFTY 200"],
        index=0,
        key="portfolio_benchmark",
    )
    refresh = st.checkbox("Refresh live prices and NAVs", value=True, key="portfolio_refresh")
    research_db = research_path if research_path.exists() else None
    try:
        summary, comparison = load_portfolio_summary(
            portfolio_path,
            research_db,
            refresh_prices=refresh,
            benchmark_index=benchmark_index,
        )
    except Exception as error:  # noqa: BLE001 - surface provider failures in UI
        st.error(f"Could not load portfolio: {error}")
        return

    columns = st.columns(4)
    columns[0].metric("Invested", _format_inr(summary.totals.get("invested")))
    columns[1].metric("Current value", _format_inr(summary.totals.get("current_value")))
    columns[2].metric("P&L", _format_inr(summary.totals.get("pnl")))
    columns[3].metric(
        "XIRR",
        f"{summary.xirr * 100:.2f}%" if summary.xirr is not None else "—",
    )
    if summary.absolute_return_pct is not None:
        st.caption(
            f"Absolute return: {summary.absolute_return_pct * 100:.2f}% "
            "(includes mutual funds when NAV data is available)."
        )

    st.markdown("**Stocks (Kite)**")
    st.dataframe(
        format_holdings_table(summary.equity),
        use_container_width=True,
        hide_index=True,
    )
    st.markdown("**Mutual funds (Coin)**")
    st.dataframe(
        format_holdings_table(summary.mutual_funds),
        use_container_width=True,
        hide_index=True,
    )
    st.markdown("**Combined allocation**")
    st.dataframe(
        format_holdings_table(summary.combined),
        use_container_width=True,
        hide_index=True,
    )

    if comparison is not None and not comparison.empty:
        st.markdown("**Portfolio vs benchmark (indexed)**")
        chart = comparison.set_index("date")[["portfolio_indexed", "benchmark_indexed"]]
        st.line_chart(chart)
    else:
        st.info(
            "Benchmark chart needs trade history and price data. "
            "Import a tradebook export for equity XIRR and history."
        )

    _render_mf_peer_comparison(portfolio_path)


def _render_mf_peer_comparison(portfolio_path: Path) -> None:
    st.markdown("**Mutual fund peer comparison (SEBI category)**")
    st.caption(
        "Compares Direct vs Regular and Growth vs IDCW separately using cached NAV "
        "history (mfapi.in + AMFI scheme master)."
    )
    sync_master = st.checkbox(
        "Refresh AMFI scheme master",
        value=False,
        key="mf_sync_master",
        help="Download the latest AMFI NAVAll.txt category list (one-time or weekly).",
    )
    try:
        reports = load_mf_peer_reports(
            portfolio_path,
            sync_master=sync_master,
        )
    except Exception as error:  # noqa: BLE001
        st.error(f"Could not load MF peer comparison: {error}")
        reports = []

    if not reports:
        st.info(
            "Import mutual fund holdings with AMFI scheme codes to see category peers. "
            "Run `portfolio sync-mf-master` once to populate categories."
        )
    else:
        for report in reports:
            held = report.held_fund
            title = f"{held.scheme_name} ({held.category})"
            if held.is_underperformer:
                st.warning(f"Underperformer vs category peers: {title}")
            else:
                st.markdown(f"**{title}**")
            summary = format_mf_returns_table(
                pd.DataFrame(
                    [
                        {
                            "scheme_code": held.scheme_code,
                            "cagr_1y": held.cagr_1y,
                            "cagr_3y": held.cagr_3y,
                            "cagr_5y": held.cagr_5y,
                            "rolling_1y_median": held.rolling_1y_median,
                            "rank_3y": held.rank_3y,
                            "percentile_3y": held.percentile_3y,
                            "category_avg_3y": held.category_avg_3y,
                            "is_underperformer": held.is_underperformer,
                        }
                    ]
                )
            )
            st.dataframe(summary, use_container_width=True, hide_index=True)
            if not report.top_peers.empty:
                st.markdown("Top peers (3Y CAGR)")
                st.dataframe(
                    format_mf_returns_table(report.top_peers),
                    use_container_width=True,
                    hide_index=True,
                )

    st.markdown("**Manual fund comparison**")
    options = list_mf_scheme_options(portfolio_path)
    if options.empty:
        st.caption("Load AMFI scheme master to pick funds for side-by-side comparison.")
        return
    labels = {
        str(row["scheme_code"]): f"{row['scheme_code']} — {row['scheme_name']}"
        for row in options.to_dict(orient="records")
    }
    selected = st.multiselect(
        "Compare funds",
        options=list(labels.keys()),
        format_func=lambda code: labels[code],
        key="mf_manual_compare",
    )
    if selected:
        manual = load_manual_mf_comparison(portfolio_path, selected)
        st.dataframe(
            format_mf_returns_table(manual),
            use_container_width=True,
            hide_index=True,
        )


def _format_inr(value: object) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"₹{float(value):,.0f}"


def _render_profile_review(database_path: Path, store: ResearchStore) -> None:
    st.subheader("Latest orchestration calibration")
    run_options = orchestration_calibration_options(database_path)
    calibration_summary = None
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
        calibration_summary = orchestration_calibration_summary(
            database_path,
            run_key=selected_run,
            store=store,
        )
        if calibration_summary is None:
            st.warning(
                "No persisted snapshots match this orchestration run's as-of dates."
            )
        else:
            columns = st.columns(4)
            columns[0].metric("Snapshots persisted", calibration_summary.records_persisted)
            columns[1].metric("Symbols evaluated", calibration_summary.symbols_evaluated)
            columns[2].metric("Skipped symbols", calibration_summary.skipped_count)
            columns[3].metric(
                "Calibration source",
                calibration_summary.source,
                help="Persisted at run time or recomputed from stored snapshots.",
            )
            st.caption(
                f"{calibration_summary.index_name} | created {calibration_summary.created_at} | "
                f"as-of dates: {', '.join(calibration_summary.as_of_dates)}"
            )
            _render_calibration_tables(calibration_summary.report)
            st.info(
                "Review threshold suggestions below, then activate a saved profile version "
                "from the diff section after comparing changes."
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

    _render_profile_version_diff(database_path, calibration_summary)

    st.subheader("All-snapshot calibration review")
    report = calibration_report(store)
    if report.score_buckets.empty and report.threshold_suggestions.empty:
        st.info(
            "No persisted snapshots are available for calibration review. "
            "Run `orchestrate` or `calibrate` after a universe walk-forward."
        )
        return

    _render_calibration_tables(report)


def _render_profile_version_diff(
    database_path: Path,
    calibration_summary,
) -> None:
    st.subheader("Profile version diff")
    options = profile_version_option_list(database_path)
    version_labels = {option.profile_version: option.label for option in options}
    default_base, default_compare = default_profile_diff_versions(database_path)
    if default_base == default_compare and len(options) <= 1:
        st.info(
            "Save a candidate profile with `profiles apply` to compare it against the "
            "active or baseline thresholds before activation."
        )
        return

    columns = st.columns(3)
    with columns[0]:
        base_version = st.selectbox(
            "Base version",
            options=list(version_labels.keys()),
            index=_option_index(version_labels, default_base),
            format_func=lambda version: version_labels[version],
            key="profile_diff_base",
        )
    with columns[1]:
        compare_version = st.selectbox(
            "Candidate version",
            options=list(version_labels.keys()),
            index=_option_index(version_labels, default_compare),
            format_func=lambda version: version_labels[version],
            key="profile_diff_compare",
        )
    with columns[2]:
        changed_only = st.checkbox(
            "Changed metrics only",
            value=True,
            key="profile_diff_changed_only",
        )

    diff = profile_version_diff_frame(
        database_path,
        base_version=base_version,
        compare_version=compare_version,
        changed_only=changed_only,
    )
    if diff.empty:
        st.success("No threshold differences between the selected profile versions.")
    else:
        st.dataframe(diff, use_container_width=True, hide_index=True)
        changed_count = int(diff["changed"].sum()) if "changed" in diff.columns else len(diff)
        st.caption(f"{changed_count} metric thresholds differ between the selected versions.")

    if (
        calibration_summary is not None
        and not calibration_summary.report.threshold_suggestions.empty
    ):
        st.markdown("**Calibration alignment for candidate version**")
        alignment = profile_calibration_alignment_frame(
            database_path,
            profile_version=compare_version,
            suggestions=calibration_summary.report.threshold_suggestions,
        )
        mismatches = alignment[~alignment["matches_suggestion"]]
        st.dataframe(alignment, use_container_width=True, hide_index=True)
        if mismatches.empty:
            st.success(
                "Candidate thresholds match the latest orchestration calibration suggestions."
            )
        else:
            st.warning(
                f"{len(mismatches)} suggested thresholds differ from the candidate profile. "
                "Review the alignment table before activating."
            )

    _render_profile_activation(
        database_path,
        compare_version=compare_version,
        calibration_summary=calibration_summary,
    )


def _render_profile_activation(
    database_path: Path,
    *,
    compare_version: int,
    calibration_summary,
) -> None:
    st.markdown("**Activate candidate profile**")
    can_activate, reason = profile_version_can_activate(database_path, compare_version)
    is_active = profile_version_is_active(database_path, compare_version)

    if is_active:
        st.success(f"Profile version {compare_version} is the active scoring profile.")
        return

    st.caption(reason)
    mismatch_count = 0
    if (
        calibration_summary is not None
        and not calibration_summary.report.threshold_suggestions.empty
    ):
        alignment = profile_calibration_alignment_frame(
            database_path,
            profile_version=compare_version,
            suggestions=calibration_summary.report.threshold_suggestions,
        )
        mismatch_count = int((~alignment["matches_suggestion"]).sum())

    reviewed = st.checkbox(
        "I reviewed the threshold diff and calibration alignment for this version.",
        value=False,
        key=f"profile_activate_reviewed_{compare_version}",
    )
    if mismatch_count > 0:
        st.warning(
            f"{mismatch_count} calibration suggestions do not match the candidate profile. "
            "Confirm only if you intentionally diverge from the latest orchestration run."
        )
        acknowledge_mismatch = st.checkbox(
            "I accept activating thresholds that differ from calibration suggestions.",
            value=False,
            key=f"profile_activate_mismatch_{compare_version}",
        )
    else:
        acknowledge_mismatch = True

    activate_disabled = not can_activate or not reviewed or not acknowledge_mismatch
    if st.button(
        f"Activate profile v{compare_version}",
        type="primary",
        disabled=activate_disabled,
        key=f"profile_activate_button_{compare_version}",
    ):
        try:
            result = activate_scoring_profile(database_path, compare_version)
        except ValueError as error:
            st.error(str(error))
            return
        if result.was_already_active:
            st.info(f"Profile version {compare_version} was already active.")
        else:
            st.success(
                f"Activated scoring profile version {compare_version}. "
                "Future runs with `--use-active-profile` will use these thresholds."
            )
        st.rerun()


def _option_index(options: dict[int, str], value: int) -> int:
    keys = list(options.keys())
    return keys.index(value) if value in keys else 0


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
