"""Browser uploads and example data for ephemeral Streamlit hosts."""

from __future__ import annotations

from pathlib import Path
import tempfile

import streamlit as st

from .friendly_copy import friendly_import_error
from .upload_state import needs_processing, mark_processed
from .portfolio_service import (
    import_cas_transactions_file,
    import_equity_holdings_file,
    import_mf_holdings_file,
    import_mf_portfolio_disclosure_file,
    import_mf_transactions_file,
    import_tradebook_file,
)
from .portfolio_store import PortfolioStore


def render_portfolio_import_panel(portfolio_path: Path, *, compact: bool = False) -> None:
    """Load examples or import Zerodha Console files from the browser."""

    if not compact:
        st.markdown("**Add or update your files**")
        st.caption("Files are stored by this app. Open Storage & help in the sidebar for backup availability.")

    portfolio_path.parent.mkdir(parents=True, exist_ok=True)

    st.markdown("**Upload from Zerodha Console**")
    st.caption("Each upload replaces the previous holdings or trade history of that type. Download a backup first to keep a copy.")
    if compact:
        _import_upload(
            portfolio_path,
            label="Stocks you own today (CSV or Excel)",
            kind="equity-holdings",
            key="upload_equity",
            help="From Console: Reports → Holdings → Equity",
        )
        _import_upload(
            portfolio_path,
            label="Mutual fund holdings (CSV or Excel)",
            kind="mf-holdings",
            key="upload_mf",
            help="From Console: Reports → Holdings → Mutual funds",
        )
        _import_upload(
            portfolio_path,
            label="Trade history (optional, CSV or Excel)",
            kind="tradebook",
            key="upload_tradebook",
            help="From Console: Reports → Tradebook — improves charts and annual return",
        )
        _import_upload(
            portfolio_path,
            label="MF transactions / SIP history (CSV or Excel)",
            kind="mf-transactions",
            key="upload_mf_txn",
            help="From Coin or Console: MF transaction export — needed for accurate annual return on funds",
        )
        _render_cas_import(portfolio_path)
        _import_upload(
            portfolio_path,
            label="MF monthly portfolio disclosure (CSV/Excel from AMC)",
            kind="mf-disclosure",
            key="upload_mf_disclosure",
            help="SEBI monthly portfolio file — enables stock-level fund overlap (one scheme per file).",
        )
    else:
        col1, col2, col3 = st.columns(3)
        with col1:
            _import_upload(
                portfolio_path,
                label="Stocks you own (CSV/Excel)",
                kind="equity-holdings",
                key="upload_equity",
                help="Reports → Holdings → Equity",
            )
        with col2:
            _import_upload(
                portfolio_path,
                label="Trade history (CSV/Excel)",
                kind="tradebook",
                key="upload_tradebook",
                help="Reports → Tradebook",
            )
        with col3:
            _import_upload(
                portfolio_path,
                label="Mutual funds (CSV/Excel)",
                kind="mf-holdings",
                key="upload_mf",
                help="Reports → Holdings → Mutual funds",
            )
        st.markdown("**Mutual fund cashflows (optional)**")
        st.caption(
            "Upload Zerodha Coin / Console MF transaction or SIP history so annual return (XIRR) "
            "includes your mutual funds."
        )
        _import_upload(
            portfolio_path,
            label="MF transactions / SIP history (CSV/Excel)",
            kind="mf-transactions",
            key="upload_mf_txn",
            help="Coin or Console MF transaction export",
        )
        _render_cas_import(portfolio_path)
        st.markdown("**MF portfolio disclosure (overlap)**")
        st.caption(
            "Upload the monthly Excel/CSV from your AMC (or AMFI portal) for each fund you hold. "
            "One scheme per file."
        )
        scheme_code = st.text_input(
            "AMFI scheme code (if not in file)",
            key="mf_disclosure_scheme_code",
            placeholder="e.g. 119063",
        )
        _import_upload(
            portfolio_path,
            label="Monthly portfolio disclosure (CSV/Excel)",
            kind="mf-disclosure",
            key="upload_mf_disclosure",
            help="SEBI disclosure with ISIN and % to NAV columns",
            extra_scheme_code=scheme_code.strip() or None,
        )


def _render_cas_import(portfolio_path: Path) -> None:
    st.markdown("**CAMS / KFintech CAS**")
    st.caption(
        "Import a detailed CAS export (CSV from casparser) or the original password-protected PDF."
    )
    password = st.text_input("CAS PDF password", type="password", key="cas_pdf_password")
    uploaded = st.file_uploader(
        "CAS statement (CSV, Excel, or PDF)",
        type=["csv", "xlsx", "xls", "pdf"],
        key="upload_cas",
    )
    if not needs_processing(uploaded, "upload_cas", portfolio_path):
        return
    store = PortfolioStore(portfolio_path)
    suffix = Path(uploaded.name).suffix.lower() or ".csv"
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
            handle.write(uploaded.getvalue())
            temp_path = Path(handle.name)
        count = import_cas_transactions_file(
            store,
            temp_path,
            password=password.strip() or None,
            replace_existing=False,
        )
        st.success(f"Imported {count} CAS transactions from {uploaded.name}.")
        mark_processed(uploaded, "upload_cas", portfolio_path)
        st.rerun()
    except Exception as error:  # noqa: BLE001
        st.error(friendly_import_error("cas", str(error)))
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _import_upload(
    portfolio_path: Path,
    *,
    label: str,
    kind: str,
    key: str,
    help: str | None = None,
    extra_scheme_code: str | None = None,
) -> None:
    uploaded = st.file_uploader(label, type=["csv", "xlsx", "xls"], key=key, help=help)
    if not needs_processing(uploaded, key, portfolio_path):
        return
    store = PortfolioStore(portfolio_path)
    suffix = Path(uploaded.name).suffix.lower() or ".csv"
    temp_path = None
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
        elif kind == "mf-transactions":
            count = import_mf_transactions_file(
                store, temp_path, replace_existing=True
            )
        elif kind == "mf-disclosure":
            count = import_mf_portfolio_disclosure_file(
                store,
                temp_path,
                scheme_code=extra_scheme_code,
            )
        else:
            count = import_mf_holdings_file(store, temp_path)
        st.success(f"Added {count} rows from {uploaded.name}.")
        mark_processed(uploaded, key, portfolio_path)
        st.session_state.pop("home_setup", None)
        st.rerun()
    except Exception as error:  # noqa: BLE001
        st.error(friendly_import_error(kind, str(error)))
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
