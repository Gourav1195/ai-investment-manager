"""Streamlit dashboard for persisted India long-term research."""

from __future__ import annotations

import os
import uuid
from datetime import date, timedelta
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
from .portfolio_store import PortfolioStore
from .portfolio_dashboard_data import (
    format_holdings_table,
    format_mf_returns_table,
    list_mf_scheme_options,
    load_manual_mf_comparison,
    load_mf_peer_reports,
    load_portfolio_summary,
    portfolio_has_data,
)
from .app_preferences import AppPreferences
from .cloud_auth import require_app_password
from .mf_rankings_ui import render_top_mutual_funds_tab
from .portfolio_cloud_ui import render_portfolio_import_panel
from .portfolio_mf_charts import render_mutual_fund_charts
from .repo_bootstrap import default_work_dir
from .research import ResearchStore
from .friendly_copy import TERM_HELP, friendly_runtime_error
from .onboarding_ui import maybe_auto_load_demo_for_qa, render_portfolio_empty_state
from .royal_theme import (
    apply_royal_theme,
    render_empty_state,
    render_friendly_error,
    render_term_glossary,
    render_welcome_header,
    render_wealth_hero,
)
from .cloud_persistence import PersistenceMode, sync_session_cloud_data
from .cloud_persistence_ui import render_data_persistence_badge, render_main_persistence_banner
from .ui_research import render_database_backup_panel, render_run_research_controls
from .wealth_insights import load_wealth_snapshot, plain_english_insights
from .about_ui import render_about_section
from .sidebar_nav import render_sidebar_section_menu
from .portfolio_start import (
    render_demo_data_banner,
    render_get_started_actions,
    render_start_setup,
    selected_portfolio_path,
    using_demo_portfolio,
)

DEFAULT_DATABASE = Path("work/research.db")
DEFAULT_PORTFOLIO_DATABASE = Path("work/portfolio.db")


def main() -> None:
    st.set_page_config(
        page_title="Your Wealth Dashboard",
        page_icon="👑",
        layout="wide",
    )
    apply_royal_theme()
    require_app_password()
    try:
        _run_dashboard()
    except Exception as error:  # noqa: BLE001 — show friendly message, not traceback
        render_friendly_error(friendly_runtime_error(error))
    finally:
        # Also save writes made during this run (including before st.rerun).
        # Never push local data until the initial cloud pull has succeeded.
        if st.session_state.get("_cloud_pulled"):
            state = sync_session_cloud_data(default_work_dir())
            if state.mode.value == "cloud_degraded":
                st.warning(state.message)


def _run_dashboard() -> None:
    work_dir = default_work_dir()
    default_database = Path(
        os.environ.get("INVESTING_RESEARCH_DB", work_dir / "research.db")
    )
    default_portfolio = Path(
        os.environ.get("INVESTING_PORTFOLIO_DB", work_dir / "portfolio.db")
    )
    prefs = AppPreferences(work_dir / "ui_prefs.json")
    database_path = default_database
    portfolio_path = default_portfolio
    persistence = sync_session_cloud_data(work_dir)

    with st.sidebar:
        st.markdown(
            '<div class="royal-sidebar-brand">'
            '<div class="royal-sidebar-brand-text">'
            "<strong>Wealth home</strong>"
            "<p>Your investments, clearly.</p>"
            "</div></div>",
            unsafe_allow_html=True,
        )
        active_section = render_sidebar_section_menu()
        st.divider()
        with st.expander("Personalise your dashboard"):
            stored_name = prefs.get_display_name()
            name = st.text_input(
                "Your name (optional)", value=stored_name,
                placeholder="Your name", key="royal_display_name",
            )
            if name != stored_name:
                prefs.set_display_name(name)
    database_path = Path(database_path)
    portfolio_path = Path(portfolio_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    maybe_auto_load_demo_for_qa(portfolio_path, prefs)

    personal_portfolio_path = portfolio_path

    portfolio_path = selected_portfolio_path(personal_portfolio_path, work_dir)

    store = ResearchStore(database_path) if database_path.exists() else None
    options = filter_options(store) if store is not None else {
        "symbols": [],
        "as_of_dates": [],
        "research_views": [],
    }

    with st.sidebar:
        with st.expander("Storage & help"):
            render_data_persistence_badge(persistence)
            render_term_glossary()
        st.caption("For tracking and research. Not investment advice.")

    render_main_persistence_banner(persistence)

    if active_section in {"Dashboard", "Portfolio", "My mutual funds", "MF peers"} and using_demo_portfolio(
        personal_portfolio_path
    ):
        render_demo_data_banner()

    if active_section == "Dashboard":
        render_welcome_header(name.strip())
        render_get_started_actions()
        if st.session_state.get("home_setup"):
            render_start_setup(personal_portfolio_path)
        notice = st.session_state.pop("portfolio_notice", None)
        if notice:
            st.success(notice)
        try:
            wealth, _summary, peer_reports = load_wealth_snapshot(
                portfolio_path,
                database_path,
                refresh_prices=False,
            )
        except Exception as error:  # noqa: BLE001
            render_friendly_error(friendly_runtime_error(error))
            from .wealth_insights import WealthSnapshot

            wealth = WealthSnapshot(None, None, None, None, None, False)
            peer_reports = []

        insights = plain_english_insights(peer_reports)
        if wealth.has_portfolio and not insights:
            insights = ["Your holdings are loaded. Open Portfolio for details or Compare funds for fund comparisons."]

        render_wealth_hero(
            total_value=wealth.total_value,
            total_pnl=wealth.total_pnl,
            xirr=wealth.xirr,
            today_change=wealth.today_change,
            today_change_pct=wealth.today_change_pct,
            insights=insights,
        )
    elif active_section == "Portfolio":
        _render_portfolio(portfolio_path, database_path, prefs, import_path=personal_portfolio_path)
    elif active_section == "My mutual funds":
        _render_mutual_funds_charts_only(portfolio_path)
    elif active_section == "Top mutual funds":
        render_top_mutual_funds_tab(personal_portfolio_path)
    elif active_section == "MF peers":
        _render_mf_peers_section(portfolio_path)
    elif active_section == "Snapshots":
        _render_snapshots_tab(database_path, store, options)
    elif active_section == "Profile review":
        if store is None:
            render_empty_state(
                "⚙️",
                "Scoring settings need research data",
                "Open **Saved research** or **Run research** in the sidebar menu.",
            )
        else:
            _render_profile_review(database_path, store)
    elif active_section == "Orchestration":
        _render_orchestration_runs(database_path)
    elif active_section == "Run research":
        st.markdown(
            '<h3 class="royal-section-title">Run research</h3>',
            unsafe_allow_html=True,
        )
        st.caption(
            "Start a scoring run here. When it completes, your latest snapshots appear below. "
            "Use **Saved research** in the sidebar to filter older runs and compare views."
        )
        if render_run_research_controls(database_path, key_prefix="main_research"):
            st.rerun()
        if store is not None:
            st.divider()
            st.markdown("**Latest saved snapshots**")
            _render_research_snapshots(
                store,
                options,
                key_prefix="run_research_results",
                include_run_controls=False,
            )
    elif active_section == "Import & backup":
        st.markdown(
            '<h3 class="royal-section-title">Import & backup</h3>',
            unsafe_allow_html=True,
        )
        st.caption("Upload Console exports, download databases, or restore a previous backup.")
        render_portfolio_import_panel(personal_portfolio_path)
        st.divider()
        render_database_backup_panel(database_path, personal_portfolio_path)
        from .cloud_persistence_ui import render_cloud_database_guide

        render_cloud_database_guide(expanded=False)
    elif active_section == "About":
        render_about_section()


def _render_snapshots_tab(
    database_path: Path,
    store: ResearchStore | None,
    options: dict[str, list],
) -> None:
    st.markdown('<h3 class="royal-section-title">Saved research</h3>', unsafe_allow_html=True)
    st.caption(
        "Your research library: every run from **Run research** is stored here. "
        "Filter by symbol, as-of date, or research view, then open a row for score drivers and fundamentals."
    )

    if store is None:
        render_empty_state(
            "📈",
            "No research saved yet",
            "Go to **Run research** in the sidebar to score your first stock list. "
            "Results will appear there and in this library.",
        )
        if render_run_research_controls(database_path, key_prefix="snapshots"):
            st.rerun()
        return

    _render_research_snapshots(
        store,
        options,
        key_prefix="saved_research",
        include_run_controls=True,
        database_path=database_path,
    )


def _render_research_snapshots(
    store: ResearchStore,
    options: dict[str, list],
    *,
    key_prefix: str,
    include_run_controls: bool,
    database_path: Path | None = None,
) -> None:
    symbol = st.selectbox(
        "Symbol filter",
        ["All"] + options["symbols"],
        index=0,
        key=f"{key_prefix}_symbol_filter",
    )
    as_of = st.selectbox(
        "As-of date filter",
        ["All"] + options["as_of_dates"],
        index=0,
        key=f"{key_prefix}_asof_filter",
    )
    research_view = st.selectbox(
        "Research view filter",
        ["All"] + options["research_views"],
        index=0,
        key=f"{key_prefix}_view_filter",
    )

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
    if summary.empty:
        render_empty_state(
            "🔍",
            "No snapshots match your filters",
            "Adjust the filters above or run research again from **Run research**.",
        )
        if include_run_controls and database_path is not None:
            if render_run_research_controls(database_path, key_prefix=f"{key_prefix}_empty"):
                st.rerun()
        return

    st.dataframe(summary, use_container_width=True, hide_index=True)
    detail_symbol = selected_symbol or summary.iloc[0]["symbol"]
    detail_as_of = selected_as_of or summary.iloc[0]["as_of"]
    with st.expander(f"Detail: {detail_symbol} as of {detail_as_of}", expanded=True):
        _render_detail(store, symbol=detail_symbol, as_of=detail_as_of)


def _render_portfolio(portfolio_path: Path, research_path: Path, prefs: AppPreferences, *, import_path: Path | None = None) -> None:
    st.markdown('<h3 class="royal-section-title">Your Zerodha portfolio</h3>', unsafe_allow_html=True)
    if not portfolio_path.exists() or not portfolio_has_data(portfolio_path):
        render_portfolio_empty_state(import_path or portfolio_path, prefs)
        return

    with st.expander("Add or replace files from Zerodha Console", expanded=False):
        render_portfolio_import_panel(import_path or portfolio_path)

    benchmark_index = st.selectbox(
        "Compare my stocks to",
        ["NIFTY 50", "NIFTY 100", "NIFTY 200"],
        index=0,
        key="portfolio_benchmark",
        help=TERM_HELP["benchmark"],
    )
    refresh = st.button(
        "Update prices & charts", key="portfolio_refresh",
        help="Downloads current prices and history. This can take a minute; otherwise we use saved values.",
    )
    store = PortfolioStore(portfolio_path)
    stock_as_of, nav_as_of = store.latest_market_data_dates()
    if stock_as_of or nav_as_of:
        parts = []
        if stock_as_of:
            parts.append(f"stocks {stock_as_of}")
        if nav_as_of:
            parts.append(f"MF NAV {nav_as_of}")
        st.caption(
            "Cached prices: " + ", ".join(parts) + ". "
            "Use **Update prices & charts** for today's AMFI / market data."
        )
    else:
        st.caption("Showing saved values. Update prices & charts when you need fresh market data.")
    research_db = research_path if research_path.exists() else None
    try:
        summary, comparison = load_portfolio_summary(
            portfolio_path,
            research_db,
            refresh_prices=refresh,
            benchmark_index=benchmark_index,
        )
    except Exception as error:  # noqa: BLE001
        render_friendly_error(friendly_runtime_error(error))
        return

    comparison_key = (str(portfolio_path.resolve()), benchmark_index)
    cache = st.session_state.setdefault("_portfolio_comparisons", {})
    if refresh and comparison is not None:
        cache[comparison_key] = (portfolio_path.stat().st_mtime_ns, comparison)
    elif comparison_key in cache:
        modified, cached_comparison = cache[comparison_key]
        if modified == portfolio_path.stat().st_mtime_ns:
            comparison = cached_comparison

    columns = st.columns(4)
    columns[0].metric(
        "Money you put in",
        _format_inr(summary.totals.get("invested")),
        help="Total amount invested in stocks and mutual funds.",
    )
    columns[1].metric(
        "Worth today",
        _format_inr(summary.totals.get("current_value")),
        help="Current market value of your holdings.",
    )
    columns[2].metric(
        "Profit or loss",
        _format_inr(summary.totals.get("pnl")),
        help=TERM_HELP["pnl"],
    )
    columns[3].metric(
        "Annual return (XIRR)",
        _format_xirr(summary.xirr),
        help=TERM_HELP["xirr"],
    )
    if summary.xirr_note:
        st.info(summary.xirr_note)
    _render_portfolio_export(portfolio_path, summary, prefs)
    _render_investment_goals(summary, prefs)
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
    equity_xirr = summary.equity_holding_xirr
    if equity_xirr is not None and not equity_xirr.empty:
        display = equity_xirr.copy()
        if "xirr" in display.columns:
            display["xirr"] = display["xirr"].map(_format_xirr)
        st.markdown("**Per-stock annual return (XIRR)**")
        st.caption("Uses your tradebook cash flows and saved market prices.")
        st.dataframe(display, use_container_width=True, hide_index=True)
    elif not store.list_equity_trades().empty:
        st.caption("Per-stock XIRR needs current prices — use **Update prices & charts**.")
    st.markdown("**Mutual funds (Coin)**")
    st.dataframe(
        format_holdings_table(summary.mutual_funds),
        use_container_width=True,
        hide_index=True,
    )
    mf_txns = store.list_mf_transactions()
    _render_mf_xirr_and_sips(summary, mf_txns, prefs)
    _render_capital_gains_section(portfolio_path, summary)
    _render_asset_allocation_section(portfolio_path, summary)
    _render_concentration_section(portfolio_path, summary)
    _render_mf_overlap_section(portfolio_path, summary)
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
    elif PortfolioStore(portfolio_path).list_equity_trades().empty:
        render_empty_state(
            "📉",
            "Add trade history for a comparison chart",
            "Upload your Zerodha tradebook export, then choose Update prices & charts.",
        )
    elif refresh:
        st.info("The comparison chart could not be loaded. Try Update prices & charts again later.")
    else:
        st.caption("Choose Update prices & charts to compare your saved trade history with Nifty.")


def _render_mutual_funds_charts_only(portfolio_path: Path) -> None:
    st.markdown('<h3 class="royal-section-title">Mutual funds</h3>', unsafe_allow_html=True)
    st.caption("Charts and performance for your Coin / MF holdings.")
    if not portfolio_path.exists() or not portfolio_has_data(portfolio_path):
        render_empty_state(
            "🪙",
            "No mutual fund holdings yet",
            "Use **Import & backup** in the menu or try the demo on **Portfolio**.",
        )
        return
    store = PortfolioStore(portfolio_path)
    mf = store.list_mf_holdings()
    if mf.empty:
        render_empty_state(
            "🪙",
            "Add mutual fund holdings",
            "Upload an MF holdings export from Zerodha Console.",
        )
        return
    from .portfolio_dashboard_data import load_portfolio_summary

    summary, _ = load_portfolio_summary(portfolio_path, None, refresh_prices=False)
    reports = load_mf_peer_reports(portfolio_path, sync_master=False, allow_network=False)
    if not summary.mutual_funds.empty:
        render_mutual_fund_charts(portfolio_path, summary.mutual_funds, reports)
    from .app_preferences import AppPreferences
    from .repo_bootstrap import default_work_dir

    prefs = AppPreferences(default_work_dir() / "ui_prefs.json")
    _render_mf_xirr_and_sips(summary, store.list_mf_transactions(), prefs)


def _render_asset_allocation_section(portfolio_path: Path, summary) -> None:
    from .portfolio_allocation import build_allocation_frames
    from .portfolio_store import PortfolioStore

    store = PortfolioStore(portfolio_path)
    lookup = store.get_scheme_meta
    by_asset, by_cap, regular = build_allocation_frames(
        summary.equity,
        summary.mutual_funds,
        scheme_meta_lookup=lookup,
    )
    if by_asset.empty:
        return
    st.markdown("**Asset allocation**")
    st.caption("Mutual funds grouped by AMFI category; stocks shown as equity.")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("*By asset class (equity / debt / gold / hybrid)*")
        st.dataframe(by_asset, use_container_width=True, hide_index=True)
    with col2:
        st.markdown("*Equity style (large / mid / small / flexi)*")
        st.dataframe(by_cap, use_container_width=True, hide_index=True)
    if not regular.empty:
        st.warning(
            "Some holdings are **Regular** plans — you may pay more yearly than a Direct plan "
            "in the same fund category."
        )
        st.dataframe(regular, use_container_width=True, hide_index=True)


def _render_capital_gains_section(portfolio_path: Path, summary) -> None:
    from .portfolio_capital_gains import TAX_DISCLAIMER, build_capital_gains_report
    from .portfolio_store import PortfolioStore

    store = PortfolioStore(portfolio_path)
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
    categories: dict[str, str] = {}
    for row in summary.mutual_funds.to_dict(orient="records"):
        code = str(row.get("scheme_code") or "").strip()
        if not code:
            continue
        meta = store.get_scheme_meta(code)
        if meta.get("category"):
            categories[code] = str(meta["category"])
    report = build_capital_gains_report(
        store,
        stock_prices=stock_prices,
        navs=navs,
        scheme_categories=categories,
    )
    if report["realized"].empty and report["unrealized"].empty:
        return
    st.markdown("**Gains (FIFO)**")
    st.caption(TAX_DISCLAIMER)
    if not report["unrealized"].empty:
        st.markdown("*Unrealized (mark-to-market)*")
        st.dataframe(report["unrealized"], use_container_width=True, hide_index=True)
    if not report["realized"].empty:
        st.markdown("*Realized (from sells/redemptions)*")
        st.dataframe(report["realized"], use_container_width=True, hide_index=True)
    if not report["fiscal_year_estimates"].empty:
        st.markdown("**Estimated tax by financial year (equity rates only)**")
        st.dataframe(
            report["fiscal_year_estimates"],
            use_container_width=True,
            hide_index=True,
        )


def _render_mf_xirr_and_sips(
    summary,
    mf_transactions: pd.DataFrame | None = None,
    prefs: AppPreferences | None = None,
) -> None:
    from .portfolio_sip_calendar import (
        SipScheduleOverride,
        detect_sip_changes,
        monthly_sip_total,
        overrides_to_json,
        parse_sip_overrides,
        resolve_sip_schedules,
        upcoming_sip_dates,
    )

    fund_xirr = summary.mf_fund_xirr
    if fund_xirr is not None and not fund_xirr.empty:
        display = fund_xirr.copy()
        if "xirr" in display.columns:
            display["xirr"] = display["xirr"].map(_format_xirr)
        st.markdown("**Per-fund annual return (XIRR)**")
        st.dataframe(display, use_container_width=True, hide_index=True)
    sips = summary.mf_sips
    if sips is not None and not sips.empty:
        cols = [c for c in ("txn_date", "scheme_name", "amount", "units", "nav") if c in sips.columns]
        st.markdown("**SIP instalments (history)**")
        st.dataframe(sips[cols], use_container_width=True, hide_index=True)
    txn_frame = mf_transactions if mf_transactions is not None else pd.DataFrame()
    if txn_frame.empty and sips is not None and not sips.empty:
        txn_frame = sips
    overrides = parse_sip_overrides(prefs.get_sip_schedule_overrides()) if prefs else []
    schedules = resolve_sip_schedules(txn_frame, overrides)
    changes = detect_sip_changes(txn_frame)
    if not changes.empty:
        st.markdown("**SIP changes detected**")
        st.dataframe(changes, use_container_width=True, hide_index=True)
    if prefs is not None:
        with st.expander("Manual SIP schedule overrides", expanded=False):
            st.caption(
                "Override inferred debit day or amount for calendar and goal projections. "
                "Disable an override to fall back to history."
            )
            if overrides:
                st.dataframe(pd.DataFrame(overrides_to_json(overrides)), hide_index=True)
            with st.form("sip_override_form", clear_on_submit=True):
                scheme_name = st.text_input("Fund name (must match holdings)")
                scheme_code = st.text_input("AMFI code (optional)")
                day = st.number_input("Debit day of month", min_value=1, max_value=31, value=1)
                amount = st.number_input("Monthly amount (₹)", min_value=100.0, step=100.0)
                remove = st.checkbox("Remove override for this fund")
                if st.form_submit_button("Save SIP override"):
                    key_name = scheme_name.strip().casefold()
                    updated = [o for o in overrides if o.scheme_name.casefold() != key_name]
                    if not remove and scheme_name.strip():
                        updated.append(
                            SipScheduleOverride(
                                scheme_code=scheme_code.strip() or None,
                                scheme_name=scheme_name.strip(),
                                day_of_month=int(day),
                                amount_inr=float(amount),
                                enabled=True,
                            )
                        )
                    prefs.set_sip_schedule_overrides(overrides_to_json(updated))
                    st.rerun()
    if schedules:
        upcoming = upcoming_sip_dates(schedules, as_of=date.today(), horizon_days=90)
        total = monthly_sip_total(schedules)
        st.markdown("**Upcoming SIP calendar (next 90 days)**")
        st.caption(
            f"Inferred from your SIP history — about ₹{total:,.0f}/month across "
            f"{len(schedules)} fund(s). Dates follow your usual debit day."
        )
        if not upcoming.empty:
            display = upcoming.copy()
            if "amount_inr" in display.columns:
                display["amount_inr"] = display["amount_inr"].map(
                    lambda value: f"₹{float(value):,.0f}"
                )
            st.dataframe(display, use_container_width=True, hide_index=True)
        else:
            st.caption("No SIP dates fall in the next 90 days.")


def _render_investment_goals(summary, prefs: AppPreferences) -> None:
    from .portfolio_goals import (
        InvestmentGoal,
        compute_goal_progress,
        goal_progress_frame,
        goals_to_json,
        parse_goals,
    )
    from .portfolio_sip_calendar import infer_sip_schedules, monthly_sip_total

    with st.expander("Financial goals", expanded=False):
        st.caption(
            "Track a target amount and date against your whole portfolio. "
            "Projections use your portfolio XIRR when available, otherwise 10% p.a., "
            "plus detected monthly SIPs."
        )
        stored = parse_goals(prefs.get_investment_goals())
        current = summary.totals.get("current_value")
        current_inr = float(current) if current is not None else 0.0
        mf_sips = summary.mf_sips if summary.mf_sips is not None else pd.DataFrame()
        from .portfolio_sip_calendar import parse_sip_overrides, resolve_sip_schedules

        txn = summary.mf_sips if summary.mf_sips is not None else pd.DataFrame()
        monthly_sip = monthly_sip_total(
            resolve_sip_schedules(txn, parse_sip_overrides(prefs.get_sip_schedule_overrides()))
        )
        annual = summary.xirr if summary.xirr is not None else 0.10

        if stored:
            rows = compute_goal_progress(
                stored,
                current_portfolio_inr=current_inr,
                annual_return=annual,
                monthly_sip_inr=monthly_sip,
            )
            frame = goal_progress_frame(rows)
            if not frame.empty:
                display = frame.copy()
                for col in ("target_inr", "projected_inr", "required_monthly_inr"):
                    if col in display.columns:
                        display[col] = display[col].map(
                            lambda value: f"₹{float(value):,.0f}"
                            if value is not None and not pd.isna(value)
                            else "—"
                        )
                if "progress_pct" in display.columns:
                    display["progress_pct"] = display["progress_pct"].map(
                        lambda value: f"{float(value):.1f}%"
                    )
                if "goal_id" in frame.columns:
                    st.caption("Goal IDs: " + ", ".join(frame["goal_id"].astype(str).tolist()))
                st.dataframe(display, use_container_width=True, hide_index=True)
            for row in rows:
                st.progress(min(1.0, row.progress_pct / 100.0), text=f"{row.name}: {row.status}")

        with st.form("add_investment_goal", clear_on_submit=True):
            name = st.text_input("Goal name", placeholder="Retirement / child's education")
            target_inr = st.number_input("Target amount (₹)", min_value=1000.0, step=1000.0)
            default_date = date.today() + timedelta(days=365 * 5)
            target_date = st.date_input("Target date", value=default_date)
            remove_id = st.text_input("Remove goal by ID (optional)", placeholder="leave blank to add")
            submitted = st.form_submit_button("Save goal")
        if submitted:
            goals = list(stored)
            if remove_id.strip():
                goals = [goal for goal in goals if goal.goal_id != remove_id.strip()]
                prefs.set_investment_goals(goals_to_json(goals))
                st.success("Goal removed.")
                st.rerun()
            elif name.strip() and target_inr > 0:
                goals.append(
                    InvestmentGoal(
                        goal_id=str(uuid.uuid4())[:8],
                        name=name.strip(),
                        target_inr=float(target_inr),
                        target_date=target_date,
                    )
                )
                prefs.set_investment_goals(goals_to_json(goals))
                st.success("Goal saved.")
                st.rerun()


def _render_portfolio_export(portfolio_path: Path, summary, prefs: AppPreferences) -> None:
    from .portfolio_goals import compute_goal_progress, parse_goals
    from .portfolio_report_export import build_portfolio_report_zip
    from .portfolio_sip_calendar import infer_sip_schedules, monthly_sip_total

    store = PortfolioStore(portfolio_path)
    mf_sips = summary.mf_sips if summary.mf_sips is not None else pd.DataFrame()
    from .portfolio_sip_calendar import parse_sip_overrides, resolve_sip_schedules

    schedules = resolve_sip_schedules(mf_sips, parse_sip_overrides(prefs.get_sip_schedule_overrides()))
    goals = parse_goals(prefs.get_investment_goals())
    current = summary.totals.get("current_value") or 0.0
    goal_rows = (
        compute_goal_progress(
            goals,
            current_portfolio_inr=float(current),
            annual_return=summary.xirr if summary.xirr is not None else 0.10,
            monthly_sip_inr=monthly_sip_total(schedules),
        )
        if goals
        else None
    )
    try:
        payload = build_portfolio_report_zip(
            summary,
            store,
            goal_rows=goal_rows,
            sip_schedules=schedules or None,
        )
    except Exception:
        payload = None
    if payload:
        st.download_button(
            "Download portfolio report (ZIP of CSVs)",
            data=payload,
            file_name=f"portfolio-report-{date.today().isoformat()}.zip",
            mime="application/zip",
            key="portfolio_report_download",
        )


def _render_concentration_section(portfolio_path: Path, summary) -> None:
    from .portfolio_concentration import build_concentration_tables, mf_category_concentration

    top, insights = build_concentration_tables(summary.combined)
    if top.empty and not insights:
        categories = mf_category_concentration(
            summary.mutual_funds, PortfolioStore(portfolio_path).get_scheme_meta
        )
        if categories.empty:
            return
    else:
        categories = mf_category_concentration(
            summary.mutual_funds, PortfolioStore(portfolio_path).get_scheme_meta
        )
    st.markdown("**Concentration & diversification**")
    if not categories.empty:
        st.markdown("*Mutual funds by SEBI category (overlap proxy)*")
        display = categories.copy()
        if "allocation_pct" in display.columns:
            display["allocation_pct"] = display["allocation_pct"].map(
                lambda value: f"{float(value) * 100:.1f}%"
                if value is not None and not pd.isna(value)
                else "—"
            )
        if "current_value" in display.columns:
            display["current_value"] = display["current_value"].map(
                lambda value: f"₹{float(value):,.0f}"
            )
        st.dataframe(display, use_container_width=True, hide_index=True)
    if not top.empty:
        display = top.copy()
        if "allocation_pct" in display.columns:
            display["allocation_pct"] = display["allocation_pct"].map(
                lambda value: f"{float(value) * 100:.1f}%"
            )
        if "current_value" in display.columns:
            display["current_value"] = display["current_value"].map(
                lambda value: f"₹{float(value):,.0f}"
            )
        st.dataframe(display, use_container_width=True, hide_index=True)
    for message in insights:
        st.info(message)


def _render_mf_overlap_section(portfolio_path: Path, summary) -> None:
    from .mf_overlap import compute_pairwise_overlap, top_shared_holdings

    store = PortfolioStore(portfolio_path)
    held_codes = [
        str(row.get("scheme_code") or "").strip()
        for row in summary.mutual_funds.to_dict(orient="records")
        if row.get("scheme_code")
    ]
    disclosure_codes = store.list_mf_disclosure_scheme_codes()
    codes = sorted({code for code in held_codes if code} & set(disclosure_codes))
    if len(codes) < 2:
        if held_codes:
            st.markdown("**Stock-level fund overlap**")
            st.caption(
                "Upload monthly **portfolio disclosure** files (Import & backup) for at least two "
                "of your funds to see shared equity holdings. There is no reliable free bulk API "
                "for all AMC portfolios — files come from each AMC or AMFI."
            )
        return
    holdings_by_scheme: dict[str, pd.DataFrame] = {}
    for code in codes:
        as_of = store.latest_disclosure_as_of(code)
        frame = store.get_mf_disclosure_holdings(code, as_of=as_of)
        if not frame.empty:
            holdings_by_scheme[code] = frame
    overlap = compute_pairwise_overlap(holdings_by_scheme)
    if overlap.empty:
        return
    st.markdown("**Stock-level fund overlap**")
    st.caption(
        "From uploaded SEBI monthly disclosures. Overlap % ≈ sum of min(weight) for shared ISINs."
    )
    display = overlap.copy()
    display["overlap_pct"] = display["overlap_pct"].map(lambda value: f"{float(value) * 100:.1f}%")
    st.dataframe(display, use_container_width=True, hide_index=True)
    top_pair = overlap.iloc[0]
    left = store.get_mf_disclosure_holdings(str(top_pair["scheme_a"]))
    right = store.get_mf_disclosure_holdings(str(top_pair["scheme_b"]))
    shared = top_shared_holdings(left, right)
    if not shared.empty:
        st.markdown("*Top shared holdings (highest overlap pair)*")
        st.dataframe(shared, use_container_width=True, hide_index=True)


def _render_mf_peers_section(portfolio_path: Path) -> None:
    st.markdown('<h3 class="royal-section-title">Compare funds</h3>', unsafe_allow_html=True)
    st.caption("Compare your funds with others in the same SEBI category.")
    if not portfolio_path.exists() or not portfolio_has_data(portfolio_path):
        render_empty_state(
            "📊",
            "No holdings yet",
            "Import your portfolio from **Import & backup** in the menu.",
        )
        return
    _render_mf_peer_comparison(portfolio_path)


def _render_mf_peer_comparison(portfolio_path: Path) -> list:
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
        render_empty_state(
            "📊",
            "Peer comparison needs fund codes",
            "Import MF holdings with AMFI scheme codes, then refresh the fund list on Top Mutual Funds.",
        )
        return reports
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
        return reports
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
    return reports


def _format_xirr(value: object) -> str:
    if value is None or pd.isna(value):
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    if number != number:  # NaN
        return "—"
    return f"{number * 100:.2f}%"


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
            "No orchestration runs yet. Start **Run research** from the Snapshots tab or sidebar."
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
        st.info("No saved scoring profile versions yet.")

    _render_profile_version_diff(database_path, calibration_summary)

    st.subheader("All-snapshot calibration review")
    report = calibration_report(store)
    if report.score_buckets.empty and report.threshold_suggestions.empty:
        st.info(
            "No snapshots available for calibration review. Run research from the Snapshots tab first."
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
        st.info("Save a candidate profile to compare threshold versions before activation.")
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
    st.subheader("Research run history")
    runs = orchestration_runs(database_path)
    if runs.empty:
        render_empty_state(
            "🗂️",
            "No research runs logged yet",
            "Open Saved research or Run research in the sidebar.",
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
        st.info("No explanation was saved for this snapshot. Run research again from the sidebar.")
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
