"""Browser uploads and example data for ephemeral Streamlit hosts."""

from __future__ import annotations

from pathlib import Path
import tempfile

import streamlit as st

from .friendly_copy import friendly_import_error
from .portfolio_service import (
    import_equity_holdings_file,
    import_mf_holdings_file,
    import_tradebook_file,
    load_example_portfolio,
)
from .portfolio_store import PortfolioStore


def render_portfolio_import_panel(portfolio_path: Path, *, compact: bool = False) -> None:
    """Load examples or import Zerodha Console files from the browser."""

    if not compact:
        st.markdown("**Add or update your files**")
        st.caption("Files stay on this device for your current session only.")

    portfolio_path.parent.mkdir(parents=True, exist_ok=True)

    if not compact:
        from .onboarding_ui import _load_demo_portfolio
        from .app_preferences import AppPreferences
        from .repo_bootstrap import default_work_dir

        prefs = AppPreferences(default_work_dir() / "ui_prefs.json")

        st.button(
            "Try demo portfolio (no files needed)",
            type="primary",
            use_container_width=True,
            key="portfolio_load_examples",
            on_click=_load_demo_portfolio,
            args=(portfolio_path, prefs),
        )

    st.markdown("**Upload from Zerodha Console**")
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


def _import_upload(
    portfolio_path: Path,
    *,
    label: str,
    kind: str,
    key: str,
    help: str | None = None,
) -> None:
    uploaded = st.file_uploader(label, type=["csv", "xlsx", "xls"], key=key, help=help)
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
        st.success(f"Added {count} rows from {uploaded.name}.")
        temp_path.unlink(missing_ok=True)
        st.rerun()
    except Exception as error:  # noqa: BLE001
        st.error(friendly_import_error(kind, str(error)))
