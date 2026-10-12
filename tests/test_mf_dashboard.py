from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.investing.mf_amfi_master import parse_amfi_nav_all
from src.investing.mf_nav_client import MfNavClient
from src.investing.portfolio_dashboard_data import (
    format_mf_returns_table,
    load_mf_peer_reports,
    load_manual_mf_comparison,
)
from src.investing.portfolio_service import load_example_portfolio
from src.investing.portfolio_store import PortfolioStore
from tests.test_mf_peer_comparison import _FixtureSession, _MFAPI_FIXTURES

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "zerodha_portfolio"


def test_dashboard_mf_peer_helpers(tmp_path) -> None:
    store = PortfolioStore(tmp_path / "portfolio.db")
    load_example_portfolio(store)
    amfi = (EXAMPLES / "amfi_nav_sample.txt").read_text(encoding="utf-8")
    store.replace_scheme_master(parse_amfi_nav_all(amfi))
    client = MfNavClient(store, session=_FixtureSession())
    for code in ("119063", "119064", "119065"):
        client.sync_scheme_nav(code)

    reports = load_mf_peer_reports(tmp_path / "portfolio.db", sync_master=False)
    assert reports
    table = format_mf_returns_table(pd.DataFrame([reports[0].held_fund.__dict__]))
    assert "cagr_3y" in table.columns

    manual = load_manual_mf_comparison(tmp_path / "portfolio.db", ["119063", "119064"])
    assert len(manual) == 2
