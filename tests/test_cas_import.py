from __future__ import annotations

from pathlib import Path

from src.investing.cas_import import parse_cas_transactions_table
from src.investing.portfolio_service import import_cas_transactions_file
from src.investing.portfolio_store import PortfolioStore

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "zerodha_portfolio"


def test_parse_cas_transactions_csv() -> None:
    frame = parse_cas_transactions_table(EXAMPLES / "cas_transactions.example.csv")
    assert len(frame) == 3
    assert set(frame["txn_type"].tolist()) >= {"sip", "purchase"}


def test_import_cas_into_store(tmp_path) -> None:
    store = PortfolioStore(tmp_path / "portfolio.db")
    count = import_cas_transactions_file(
        store,
        EXAMPLES / "cas_transactions.example.csv",
        source="example",
        replace_existing=True,
    )
    assert count == 3
    assert len(store.list_mf_transactions()) == 3
