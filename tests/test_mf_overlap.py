from __future__ import annotations

from pathlib import Path

from src.investing.mf_overlap import compute_pairwise_overlap
from src.investing.portfolio_service import import_mf_portfolio_disclosure_file
from src.investing.portfolio_store import PortfolioStore

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "zerodha_portfolio"


def test_pairwise_overlap_from_disclosure_uploads(tmp_path) -> None:
    store = PortfolioStore(tmp_path / "portfolio.db")
    import_mf_portfolio_disclosure_file(
        store, EXAMPLES / "mf_disclosure_flexi.example.csv", source="example"
    )
    import_mf_portfolio_disclosure_file(
        store, EXAMPLES / "mf_disclosure_ppfas.example.csv", source="example"
    )
    holdings = {
        "119063": store.get_mf_disclosure_holdings("119063", as_of="2024-08-31"),
        "122639": store.get_mf_disclosure_holdings("122639", as_of="2024-08-31"),
    }
    overlap = compute_pairwise_overlap(holdings)
    assert len(overlap) == 1
    assert float(overlap.iloc[0]["overlap_pct"]) > 0.10
    assert int(overlap.iloc[0]["shared_holdings"]) >= 2
