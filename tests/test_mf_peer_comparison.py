from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from src.investing.mf_amfi_master import parse_amfi_nav_all
from src.investing.mf_nav_client import MfNavClient
from src.investing.mf_peer_comparison import (
    _cagr,
    compare_held_fund_to_peers,
    compare_manual_funds,
)
from src.investing.portfolio_store import PortfolioStore

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "zerodha_portfolio"


def _nav_series(start_nav: float, end_nav: float, years: int) -> list[tuple[str, float]]:
    end = date(2026, 10, 8)
    start = end - timedelta(days=365 * years)
    points: list[tuple[str, float]] = []
    steps = years * 12
    for step in range(steps + 1):
        when = start + timedelta(days=int((end - start).days * step / steps))
        nav = start_nav + (end_nav - start_nav) * step / steps
        points.append((when.isoformat(), nav))
    return points


def _seed_peer_database(tmp_path) -> tuple[PortfolioStore, MfNavClient]:
    store = PortfolioStore(tmp_path / "portfolio.db")
    amfi = (EXAMPLES / "amfi_nav_sample.txt").read_text(encoding="utf-8")
    store.replace_scheme_master(parse_amfi_nav_all(amfi))
    client = MfNavClient(store, session=_FixtureSession())
    return store, client


class _FixtureSession:
    def get(self, url: str, timeout: int = 60) -> _FixtureResponse:
        scheme_code = url.rstrip("/").split("/")[-1]
        payload = _MFAPI_FIXTURES[scheme_code]
        return _FixtureResponse(payload)


class _FixtureResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def _mfapi_payload(
    scheme_code: str,
    name: str,
    category: str,
    nav_points: list[tuple[str, float]],
) -> dict:
    return {
        "meta": {
            "scheme_name": name,
            "scheme_category": category,
            "scheme_type": "Open Ended Schemes",
        },
        "data": [
            {"date": date.fromisoformat(nav_date).strftime("%d-%m-%Y"), "nav": f"{nav:.4f}"}
            for nav_date, nav in reversed(nav_points)
        ],
    }


_MFAPI_FIXTURES = {
    "119063": _mfapi_payload(
        "119063",
        "HDFC Flexi Cap Fund - Direct Plan - Growth",
        "Equity Scheme - Flexi Cap Fund",
        _nav_series(700.0, 900.0, 5),
    ),
    "119064": _mfapi_payload(
        "119064",
        "Sample Flexi Cap Peer A - Direct Plan - Growth",
        "Equity Scheme - Flexi Cap Fund",
        _nav_series(700.0, 950.0, 5),
    ),
    "119065": _mfapi_payload(
        "119065",
        "Sample Flexi Cap Peer B - Direct Plan - Growth",
        "Equity Scheme - Flexi Cap Fund",
        _nav_series(700.0, 860.0, 5),
    ),
}


def test_cagr_calculation() -> None:
    nav = [
        ("2021-10-08", 100.0),
        ("2026-10-08", 161.05),
    ]
    frame = __import__("pandas").DataFrame(nav, columns=["nav_date", "nav"])
    rate = _cagr(frame, years=5)
    assert rate is not None
    assert abs(rate - 0.10) < 0.02


def test_peer_comparison_ranks_held_fund(tmp_path) -> None:
    store, client = _seed_peer_database(tmp_path)
    report = compare_held_fund_to_peers(
        store,
        "119063",
        client=client,
        sync_master=False,
        max_peers=10,
    )
    assert report is not None
    assert report.held_fund.rank_3y is not None
    assert report.held_fund.peer_count_3y >= 3
    assert not report.top_peers.empty
    assert report.held_fund.cagr_3y is not None


def test_manual_fund_comparison_table(tmp_path) -> None:
    store, client = _seed_peer_database(tmp_path)
    frame = compare_manual_funds(store, ["119063", "119064"], client=client)
    assert len(frame) == 2
    assert frame.iloc[0]["cagr_3y"] >= frame.iloc[1]["cagr_3y"]
