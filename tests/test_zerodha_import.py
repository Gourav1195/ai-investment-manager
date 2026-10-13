from __future__ import annotations

from pathlib import Path

from src.investing.portfolio_store import PortfolioStore
from src.investing.zerodha_import import (
    parse_equity_holdings,
    parse_mf_holdings,
    parse_mf_transactions,
    parse_tradebook,
)

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "zerodha_portfolio"


def test_parse_equity_holdings_example() -> None:
    frame = parse_equity_holdings(EXAMPLES / "equity_holdings.example.csv")
    assert len(frame) == 3
    assert frame.iloc[0]["symbol"] == "RELIANCE"
    assert frame.iloc[0]["quantity"] == 10.0


def test_parse_tradebook_example() -> None:
    frame = parse_tradebook(EXAMPLES / "tradebook.example.csv")
    assert len(frame) == 4
    assert frame.iloc[0]["side"] == "buy"
    assert frame.iloc[0]["trade_date"] == "2024-01-15"


def test_parse_mf_holdings_example() -> None:
    frame = parse_mf_holdings(EXAMPLES / "mf_holdings.example.csv")
    assert len(frame) == 2
    assert frame.iloc[0]["scheme_code"] == "119063"
    assert frame.iloc[0]["units"] > 0


def test_parse_mf_transactions_example() -> None:
    frame = parse_mf_transactions(EXAMPLES / "mf_transactions.example.csv")
    assert len(frame) == 3
    assert frame.iloc[0]["txn_type"] == "sip"
    assert frame.iloc[0]["txn_date"] == "2024-02-01"
    assert (frame["txn_type"] == "sip").sum() == 2
    assert frame["amount"].sum() == 45000.0


def test_portfolio_store_round_trip(tmp_path) -> None:
    store = PortfolioStore(tmp_path / "portfolio.db")
    equity = parse_equity_holdings(EXAMPLES / "equity_holdings.example.csv")
    trades = parse_tradebook(EXAMPLES / "tradebook.example.csv")
    mf = parse_mf_holdings(EXAMPLES / "mf_holdings.example.csv")
    mf_txns = parse_mf_transactions(EXAMPLES / "mf_transactions.example.csv")

    key = store.record_import(
        source="zerodha_csv",
        kind="equity_holdings",
        file_name="equity_holdings.example.csv",
        row_count=len(equity),
    )
    store.replace_equity_holdings(equity, source="zerodha_csv", import_key=key)
    store.append_equity_trades(
        trades, source="zerodha_csv", import_key=key, replace_existing=True
    )
    store.replace_mf_holdings(mf, source="zerodha_csv", import_key=key)
    store.append_mf_transactions(
        mf_txns, source="zerodha_csv", import_key=key, replace_existing=True
    )

    assert len(store.list_equity_holdings()) == 3
    assert len(store.list_equity_trades()) == 4
    assert len(store.list_mf_holdings()) == 2
    assert len(store.list_mf_transactions()) == 3
