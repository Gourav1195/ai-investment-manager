"""Live network checks (AMFI / mfapi.in). Skip with pytest -m 'not integration'."""

from __future__ import annotations

import pytest

from src.investing.mf_nav_client import MfNavClient
from src.investing.mf_peer_comparison import compare_held_fund_to_peers
from src.investing.portfolio_store import PortfolioStore

PARAG_PARIKH_FLEXI_DIRECT_GROWTH = "122639"

pytestmark = pytest.mark.integration


@pytest.mark.timeout(120)
def test_live_mfapi_nav_for_parag_parikh_flexi_cap(tmp_path) -> None:
    store = PortfolioStore(tmp_path / "portfolio.db")
    client = MfNavClient(store)
    series = client.sync_scheme_nav(PARAG_PARIKH_FLEXI_DIRECT_GROWTH)
    assert not series.nav.empty
    assert series.nav.iloc[-1]["nav"] > 0


@pytest.mark.timeout(180)
def test_live_amfi_master_and_peer_rank(tmp_path) -> None:
    store = PortfolioStore(tmp_path / "portfolio.db")
    client = MfNavClient(store)
    client.sync_scheme_master_from_amfi()
    assert store.scheme_master_count() > 1000
    store.replace_mf_holdings(
        __import__("pandas").DataFrame(
            [
                {
                    "scheme_code": PARAG_PARIKH_FLEXI_DIRECT_GROWTH,
                    "scheme_name": "Parag Parikh Flexi Cap Fund - Direct Plan - Growth",
                    "units": 10.0,
                    "average_nav": 50.0,
                }
            ]
        ),
        source="test",
        import_key="test:mf",
    )
    report = compare_held_fund_to_peers(
        store,
        PARAG_PARIKH_FLEXI_DIRECT_GROWTH,
        client=client,
        sync_master=False,
        max_peers=25,
    )
    assert report is not None
    assert report.held_fund.cagr_3y is not None
