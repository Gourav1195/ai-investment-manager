from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from src.investing.portfolio_analytics import (
    build_portfolio_summary,
    compute_portfolio_xirr,
    xirr,
)
from src.investing.portfolio_pricing import AmfiNavProvider
from src.investing.portfolio_store import PortfolioStore
from src.investing.zerodha_import import (
    parse_equity_holdings,
    parse_mf_holdings,
    parse_tradebook,
)

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "zerodha_portfolio"


def _seed_store(path: Path) -> PortfolioStore:
    store = PortfolioStore(path)
    key = store.record_import(
        source="example",
        kind="bundle",
        file_name="examples",
        row_count=3,
    )
    store.replace_equity_holdings(
        parse_equity_holdings(EXAMPLES / "equity_holdings.example.csv"),
        source="example",
        import_key=key,
    )
    store.replace_mf_holdings(
        parse_mf_holdings(EXAMPLES / "mf_holdings.example.csv"),
        source="example",
        import_key=key,
    )
    store.append_equity_trades(
        parse_tradebook(EXAMPLES / "tradebook.example.csv"),
        source="example",
        import_key=key,
        replace_existing=True,
    )
    return store


def test_build_portfolio_summary_pnl(tmp_path) -> None:
    store = _seed_store(tmp_path / "portfolio.db")
    stock_prices = {"RELIANCE": 2600.0, "INFY": 1500.0, "HDFCBANK": 1700.0}
    navs = {"119063": 900.0, "122639": 80.0}
    summary = build_portfolio_summary(store, stock_prices=stock_prices, navs=navs)

    assert summary.totals["invested"] is not None
    assert summary.totals["current_value"] is not None
    assert summary.totals["pnl"] is not None
    assert len(summary.equity) == 3
    assert len(summary.mutual_funds) == 2
    reliance = summary.equity[summary.equity["identifier"] == "RELIANCE"].iloc[0]
    assert reliance["pnl"] == 10 * (2600.0 - 2450.5)


def test_xirr_known_cashflows() -> None:
    flows = [
        (date(2024, 1, 1), -1000.0),
        (date(2024, 7, 1), 1100.0),
    ]
    rate = xirr(flows)
    assert rate is not None
    assert abs(rate - 0.21) < 0.02


def test_compute_portfolio_xirr_from_tradebook(tmp_path) -> None:
    store = _seed_store(tmp_path / "portfolio.db")
    trades = store.list_equity_trades()
    rate = compute_portfolio_xirr(
        trades,
        equity_terminal_value=100000.0,
        mf_terminal_value=50000.0,
        as_of=date(2025, 1, 1),
    )
    assert rate is not None
    assert rate > 0


def test_amfi_nav_parser_parses_sample_text() -> None:
    sample = """
Open Ended Schemes(Debt Scheme - Banking and PSU Fund)
119063;HDFC Banking and PSU Debt Fund - Direct Plan - Growth;INF179K01XZ2;Growth;912.3450;08-10-2026
"""
    provider = AmfiNavProvider(session=_FakeSession(sample))
    navs = provider.latest_navs(["119063"])
    assert navs["119063"] == 912.345


class _FakeSession:
    def __init__(self, text: str) -> None:
        self.text = text

    def get(self, url: str, timeout: int = 60) -> _FakeResponse:
        return _FakeResponse(self.text)


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text
