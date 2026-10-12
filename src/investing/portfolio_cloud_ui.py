"""Browser uploads and example data for ephemeral Streamlit hosts."""

from __future__ import annotations

from pathlib import Path
import tempfile

import streamlit as st

from .portfolio_service import (
    import_equity_holdings_file,
    import_mf_holdings_file,
    import_tradebook_file,
    load_example_portfolio,
)
from .portfolio_store import PortfolioStore


def render_portfolio_import_panel(portfolio_path: Path) -> None:
    """Load examples or import Zerodha Console files from the browser."""

    st.markdown("**Portfolio data (this session)**")
    st.caption(
        "On Streamlit Cloud, files are stored only for the current session. "
        "Upload exports from Zerodha Console or load the anonymized demo."
    )
    portfolio_path.parent.mkdir(parents=True, exist_ok=True)

    if st.button("Load anonymized example portfolio", key="portfolio_load_examples"):
        store = PortfolioStore(portfolio_path)
        counts = load_example_portfolio(store)
        st.success(
            f"Loaded demo: {counts['equity_holdings']} equity, "
            f"{counts['mf_holdings']} MF holdings, {counts['tradebook']} trades."
        )
        st.rerun()

    col1, col2, col3 = st.columns(3)
    with col1:
        _import_upload(
            portfolio_path,
            label="Equity holdings (CSV/XLSX)",
            kind="equity-holdings",
            key="upload_equity",
        )
    with col2:
        _import_upload(
            portfolio_path,
            label="Tradebook (CSV/XLSX)",
            kind="tradebook",
            key="upload_tradebook",
        )
    with col3:
        _import_upload(
            portfolio_path,
            label="MF holdings (CSV/XLSX)",
            kind="mf-holdings",
            key="upload_mf",
        )


def _import_upload(
    portfolio_path: Path,
    *,
    label: str,
    kind: str,
    key: str,
) -> None:
    uploaded = st.file_uploader(label, type=["csv", "xlsx", "xls"], key=key)
    if uploaded is None:
        return
    store = PortfolioStore(portfolio_path)
    suffix = Path(uploaded.name).suffix.lower() or ".csv"
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
            handle.write(uploaded.getvalue())
            temp_path = Path(handle.name)
        if kind == "equity-holdings":
            count = import_equity_holdings_file(store, temp_path)
        elif kind == "tradebook":
            count = import_tradebook_file(
                store, temp_path, replace_existing=True
            )
        else:
            count = import_mf_holdings_file(store, temp_path)
        st.success(f"Imported {count} rows from {uploaded.name}")
        temp_path.unlink(missing_ok=True)
        st.rerun()
    except Exception as error:  # noqa: BLE001
        st.error(f"Import failed: {error}")
