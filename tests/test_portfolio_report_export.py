from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path

from src.investing.portfolio_analytics import build_portfolio_summary
from src.investing.portfolio_report_export import build_portfolio_report_zip
from src.investing.portfolio_store import PortfolioStore
from src.investing.zerodha_import import (
    parse_equity_holdings,
    parse_mf_holdings,
    parse_tradebook,
)

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "zerodha_portfolio"


def _seed_store(path: Path) -> PortfolioStore:
    store = PortfolioStore(path)
    key = store.record_import(source="example", kind="bundle", file_name="x", row_count=1)
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


def test_build_portfolio_report_zip(tmp_path) -> None:
    store = _seed_store(tmp_path / "portfolio.db")
    summary = build_portfolio_summary(
        store,
        stock_prices={"RELIANCE": 2600.0, "INFY": 1500.0, "HDFCBANK": 1700.0},
        navs={"119063": 900.0, "122639": 80.0},
    )
    payload = build_portfolio_report_zip(summary, store)
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        names = set(archive.namelist())
    assert "summary_totals.csv" in names
    assert "equity_holdings.csv" in names
