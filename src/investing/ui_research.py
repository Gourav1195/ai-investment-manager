"""In-browser research runs and SQLite backup for Streamlit."""

from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Iterable

import pandas as pd
import streamlit as st

from .upload_state import needs_processing, mark_processed

from .constituents import ConstituentHistoryStore
from .demo_research import (
    DEMO_SYMBOLS,
    DemoFilingStore,
    StaticUniverseProvider,
    default_research_as_of,
    synthetic_prices_for_symbols,
)
from .cloud_persistence import is_cloud_persistence_configured
from .orchestration import UniverseResearchOrchestrator, _price_symbols
from .providers import DataProviderError, NiftyIndexUniverseProvider, YFinancePriceProvider, nifty_benchmark_symbol

ProgressCallback = Callable[[str, float], None]

UNIVERSE_OPTIONS = {
    "Quick demo (10 well-known stocks)": ("demo", 10),
    "NIFTY 50 — first 15 stocks": ("NIFTY 50", 15),
    "NIFTY 50 — first 30 stocks": ("NIFTY 50", 30),
    "NIFTY 100 — first 20 stocks": ("NIFTY 100", 20),
}


@dataclass(frozen=True)
class UiResearchResult:
    symbols_evaluated: int
    records_persisted: int
    skipped_count: int
    price_source: str
    filing_mode: str
    message: str


def resolve_universe_symbols(
    choice_key: str,
    *,
    offline: bool,
) -> tuple[list[str], str, str]:
    mode, max_symbols = UNIVERSE_OPTIONS.get(
        choice_key, UNIVERSE_OPTIONS["Quick demo (10 well-known stocks)"]
    )
    if mode == "demo" or offline:
        symbols = list(DEMO_SYMBOLS)[:max_symbols]
        return symbols, "Demo universe", "demo fundamentals"
    try:
        provider = NiftyIndexUniverseProvider(mode)
        symbols = provider.symbols()[:max_symbols]
        return symbols, mode, "demo fundamentals when NSE filings are unavailable"
    except DataProviderError:
        symbols = list(DEMO_SYMBOLS)[:max_symbols]
        return (
            symbols,
            "Demo universe (index list unavailable)",
            "demo fundamentals",
        )


class _StaticPriceProvider:
    def __init__(self, frame: pd.DataFrame) -> None:
        self._frame = frame

    def fetch(self, symbols: Iterable[str], start: str, end: str) -> pd.DataFrame:
        if self._frame.empty:
            raise DataProviderError("No price data available")
        subset = self._frame.copy()
        wanted = {str(symbol).removesuffix(".NS").upper() for symbol in symbols}
        wanted.add(nifty_benchmark_symbol("NIFTY 50").upper())
        mask = subset["symbol"].astype(str).str.upper().isin(wanted)
        filtered = subset.loc[mask]
        if "date" in filtered.columns:
            filtered = filtered.loc[
                (filtered["date"] >= start[:10]) & (filtered["date"] <= end[:10])
            ]
        return filtered if not filtered.empty else self._frame


def run_ui_research(
    database_path: Path,
    *,
    universe_choice: str,
    progress: ProgressCallback | None = None,
    offline: bool | None = None,
) -> UiResearchResult:
    if offline is None:
        offline = os.environ.get("INVESTING_UI_RESEARCH_OFFLINE", "").strip().lower() in {
            "1",
            "true",
            "yes",
        }

    def report(message: str, fraction: float) -> None:
        if progress is not None:
            progress(message, min(max(fraction, 0.0), 1.0))

    database_path.parent.mkdir(parents=True, exist_ok=True)
    symbols, index_label, filing_note = resolve_universe_symbols(universe_choice, offline=offline)
    report(f"Preparing research for {len(symbols)} companies…", 0.05)

    as_of = default_research_as_of()
    end = date.today()
    start = end - timedelta(days=365 * 4)
    prices_start = start.isoformat()
    prices_end = end.isoformat()

    price_source = "Yahoo Finance"
    prices: pd.DataFrame | None = None
    if not offline:
        report("Downloading share prices (this can take a minute)…", 0.15)
        try:
            provider = YFinancePriceProvider()
            constituent_store = ConstituentHistoryStore(database_path)
            price_symbols = _price_symbols(
                symbols,
                benchmark_index="NIFTY 50",
                portfolio_symbols=[],
                as_of_dates=[as_of],
                constituent_store=constituent_store,
                use_historical=False,
            )
            prices = provider.fetch(price_symbols, prices_start, prices_end)
        except (DataProviderError, ValueError, OSError):
            prices = None

    if prices is None or prices.empty:
        price_source = "Built-in demo prices"
        prices = synthetic_prices_for_symbols(
            symbols,
            benchmark_index="NIFTY 50",
            start=prices_start,
            end=prices_end,
        )

    report("Scoring companies and saving results…", 0.55)
    orchestrator = UniverseResearchOrchestrator(
        database=database_path,
        universe_provider=StaticUniverseProvider(symbols, label=index_label),
        filing_store=DemoFilingStore(),
        price_provider=_StaticPriceProvider(prices),
    )
    result = orchestrator.run(
        index_name=index_label,
        as_of_dates=[as_of],
        prices_start=prices_start,
        prices_end=prices_end,
        benchmark_index="NIFTY 50",
        forward_days=180,
        snapshot_cadence="quarterly",
        archive_constituents=False,
        benchmark_portfolio=False,
        persist=True,
        explain=True,
        max_symbols=len(symbols),
    )

    report("Finished.", 1.0)
    skipped = len(result.skipped_symbols)
    message = (
        f"Saved {result.records_persisted} research snapshots for "
        f"{result.symbols_evaluated} companies ({index_label}). "
        f"Prices: {price_source}. Fundamentals: {filing_note}."
    )
    if skipped:
        message += f" Skipped {skipped} symbols."
    return UiResearchResult(
        symbols_evaluated=result.symbols_evaluated,
        records_persisted=result.records_persisted,
        skipped_count=skipped,
        price_source=price_source,
        filing_mode=filing_note,
        message=message,
    )


def render_run_research_controls(
    database_path: Path,
    *,
    key_prefix: str = "sidebar",
) -> bool:
    st.markdown("**Run a new research batch**")
    st.caption(
        "Downloads prices, scores companies, and **saves snapshots** to your database. "
        "Results appear on this page when the run finishes, and stay available under "
        "**Saved research** for browsing and filtering. Uses a small stock list by default "
        "to stay within free hosting limits."
    )
    choice = st.selectbox(
        "Stock list",
        options=list(UNIVERSE_OPTIONS.keys()),
        index=0,
        key=f"{key_prefix}_universe",
    )
    if st.button("Run research", type="primary", key=f"{key_prefix}_run_research"):
        bar = st.progress(0.0, text="Starting…")
        status = st.empty()

        def progress(message: str, fraction: float) -> None:
            bar.progress(fraction, text=message)
            status.caption(message)

        try:
            outcome = run_ui_research(database_path, universe_choice=choice, progress=progress)
        except Exception as error:  # noqa: BLE001
            st.error(f"Research run failed: {error}")
            return False
        st.success(outcome.message)
        return True
    return False


def render_database_backup_panel(
    research_path: Path,
    portfolio_path: Path,
) -> None:
    st.markdown("**Save or restore your data**")
    if is_cloud_persistence_configured():
        st.caption(
            "Cloud database is enabled — your files sync automatically. "
            "You can still download backups here as an extra safety copy."
        )
    else:
        st.caption(
            "On Streamlit Cloud, databases live on temporary disk unless you set "
            "DATABASE_URL in secrets (see sidebar guide). Download backups after "
            "a research run or portfolio import, then upload them in a later session."
        )
    col1, col2 = st.columns(2)
    with col1:
        if research_path.exists():
            st.download_button(
                "Download research database",
                data=research_path.read_bytes(),
                file_name="research.db",
                mime="application/octet-stream",
                key="dl_research_db",
            )
        else:
            st.caption("No research database file yet.")
    with col2:
        if portfolio_path.exists():
            st.download_button(
                "Download portfolio database",
                data=portfolio_path.read_bytes(),
                file_name="portfolio.db",
                mime="application/octet-stream",
                key="dl_portfolio_db",
            )
        else:
            st.caption("No portfolio database file yet.")

    up1, up2 = st.columns(2)
    with up1:
        uploaded = st.file_uploader("Restore research database", type=["db"], key="ul_research_db")
        _restore_uploaded_database(uploaded, research_path, key="ul_research_db", kind="Research")
    with up2:
        uploaded_pf = st.file_uploader("Restore portfolio database", type=["db"], key="ul_portfolio_db")
        _restore_uploaded_database(uploaded_pf, portfolio_path, key="ul_portfolio_db", kind="Portfolio")


def _restore_uploaded_database(uploaded, path: Path, *, key: str, kind: str) -> None:
    if not needs_processing(uploaded, key, path):
        return
    try:
        restore_sqlite_bytes(uploaded.getvalue(), path, kind=kind)
    except (ValueError, sqlite3.Error, OSError):
        st.error(f"This is not a valid {kind.lower()} backup. Your existing data has been kept.")
        return
    mark_processed(uploaded, key, path)
    st.success(f"{kind} database restored.")
    st.rerun()


def restore_sqlite_bytes(payload: bytes, path: Path, *, kind: str) -> None:
    """Validate an uploaded backup before atomically replacing existing data."""
    if not payload.startswith(b"SQLite format 3\x00"):
        raise ValueError("Not a SQLite database")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".db", delete=False) as handle:
            handle.write(payload)
            temp = Path(handle.name)
        conn = sqlite3.connect(temp.as_uri() + "?mode=ro", uri=True)
        try:
            if conn.execute("PRAGMA quick_check").fetchone() != ("ok",):
                raise ValueError("Damaged database")
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            required = {"research_snapshots", "research_evaluations"} if kind == "Research" else {"equity_holdings", "mf_holdings"}
            if not required.issubset(tables):
                raise ValueError("Wrong backup type")
        finally:
            conn.close()
        os.replace(temp, path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def copy_sqlite_backup(source: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as handle:
        temp = Path(handle.name)
    shutil.copy2(source, temp)
    shutil.move(str(temp), dest)
