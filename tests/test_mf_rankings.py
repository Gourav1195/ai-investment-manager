from __future__ import annotations

import pandas as pd

from src.investing.mf_amfi_master import parse_amfi_nav_all
from src.investing.mf_nav_client import MfNavClient
from src.investing.mf_rankings import normalized_nav_frame, rank_funds_in_category
from src.investing.portfolio_store import PortfolioStore


SAMPLE_AMFI = """Open Ended Schemes ( Equity Scheme - Large Cap Fund )
123456;Demo Large Cap Direct Growth;INF1234567890;123.45;01-Jan-2024
123457;Demo Large Cap Direct Growth 2;INF1234567891;110.00;01-Jan-2024
"""


def _nav_rows(code: str, start: float, steps: int) -> dict:
    import json
    from datetime import date, timedelta

    data = []
    for index in range(steps):
        day = date(2020, 1, 1) + timedelta(days=index * 7)
        data.append(
            {
                "date": day.strftime("%d-%m-%Y"),
                "nav": f"{start + index * 0.05:.4f}",
            }
        )
    return {
        "meta": {
            "scheme_name": f"Fund {code}",
            "scheme_category": "Equity Scheme - Large Cap Fund",
        },
        "data": data,
    }


class _FakeSession:
    def get(self, url: str, *, timeout: float):
        class Response:
            def __init__(self, payload: dict | str) -> None:
                self._payload = payload

            def raise_for_status(self) -> None:
                return None

            @property
            def text(self) -> str:
                return str(self._payload)

            def json(self) -> dict:
                return self._payload  # type: ignore[return-value]

        if "NAVAll" in url:
            return Response(SAMPLE_AMFI)
        code = url.rstrip("/").split("/")[-1]
        return Response(_nav_rows(code, 100.0, 120))


def test_normalized_nav_frame_indexes_to_100() -> None:
    nav = pd.DataFrame({"nav_date": ["2020-01-01", "2021-01-01"], "nav": [10.0, 20.0]})
    wide = normalized_nav_frame({"1": nav}, {"1": "Demo"})
    assert wide.iloc[0]["Demo"] == 100.0
    assert wide.iloc[-1]["Demo"] == 200.0


def test_rank_funds_in_category_with_mock_nav(tmp_path) -> None:
    store = PortfolioStore(tmp_path / "portfolio.db")
    client = MfNavClient(store, session=_FakeSession())  # type: ignore[arg-type]
    client.sync_scheme_master_from_amfi()
    result = rank_funds_in_category(
        store,
        category="Equity Scheme - Large Cap Fund",
        plan_type="Direct",
        option_type="Growth",
        client=client,
        max_candidates=5,
        top_n=2,
    )
    assert not result.table.empty
    assert "rank" in result.table.columns
