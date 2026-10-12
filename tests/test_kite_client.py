from __future__ import annotations

from src.investing.kite_client import KiteReadOnlyClient
from src.investing.kite_config import KiteCredentials


def test_kite_read_only_client_parses_holdings() -> None:
    client = KiteReadOnlyClient(
        KiteCredentials(api_key="key", access_token="token"),
        session=_FakeKiteSession(),
    )
    equity = client.equity_holdings_frame()
    mf = client.mf_holdings_frame()

    assert equity.iloc[0]["symbol"] == "RELIANCE"
    assert equity.iloc[0]["quantity"] == 10
    assert mf.iloc[0]["units"] == 125.5


class _FakeKiteSession:
    def get(self, url: str, headers: dict, timeout: int = 30) -> _FakeResponse:
        if url.endswith("/portfolio/holdings"):
            payload = {
                "status": "success",
                "data": [
                    {
                        "tradingsymbol": "RELIANCE-EQ",
                        "isin": "INE002A01018",
                        "quantity": 10,
                        "average_price": 2450.5,
                        "product": "CNC",
                        "exchange": "NSE",
                    }
                ],
            }
        else:
            payload = {
                "status": "success",
                "data": [
                    {
                        "fund": "119063",
                        "tradingsymbol": "119063",
                        "folio": "123/45",
                        "quantity": 125.5,
                        "average_price": 850.0,
                    }
                ],
            }
        return _FakeResponse(payload)


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload
