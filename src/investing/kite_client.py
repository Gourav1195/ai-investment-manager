"""Read-only Kite Connect client for portfolio holdings sync."""

from __future__ import annotations

from typing import Any

import pandas as pd
import requests

from .kite_config import KiteCredentials

KITE_API_BASE = "https://api.kite.trade"
ALLOWED_GET_PATHS = frozenset({"/portfolio/holdings", "/mf/holdings"})


class KiteReadOnlyClient:
    """Fetch holdings from Kite Connect without placing orders."""

    def __init__(
        self,
        credentials: KiteCredentials,
        session: requests.Session | None = None,
    ) -> None:
        self.credentials = credentials
        self._session = session or requests.Session()

    def equity_holdings_frame(self) -> pd.DataFrame:
        payload = self._get("/portfolio/holdings")
        rows = payload.get("data", [])
        records: list[dict[str, object]] = []
        for item in rows:
            records.append(
                {
                    "symbol": _equity_symbol(item),
                    "isin": item.get("isin"),
                    "quantity": float(item.get("quantity") if item.get("quantity") is not None else item.get("opening_quantity") or 0),
                    "average_price": float(item.get("average_price") or 0),
                    "product": item.get("product"),
                    "exchange": item.get("exchange"),
                    "last_price": _optional_float(item.get("last_price")),
                }
            )
        frame = pd.DataFrame(records, columns=["symbol", "isin", "quantity", "average_price", "product", "exchange", "last_price"])
        return frame[frame["quantity"] > 0].reset_index(drop=True)

    def mf_holdings_frame(self) -> pd.DataFrame:
        payload = self._get("/mf/holdings")
        rows = payload.get("data", [])
        records: list[dict[str, object]] = []
        for item in rows:
            records.append(
                {
                    "scheme_code": _mf_identifier(item),
                    "scheme_name": str(item.get("fund") or item.get("tradingsymbol") or ""),
                    "folio": item.get("folio"),
                    "units": float(item.get("quantity") or 0),
                    "average_nav": _optional_float(item.get("average_price")),
                    "last_price": _optional_float(item.get("last_price")),
                }
            )
        frame = pd.DataFrame(records, columns=["scheme_code", "scheme_name", "folio", "units", "average_nav", "last_price"])
        return frame[frame["units"] > 0].reset_index(drop=True)

    def _get(self, path: str) -> dict[str, Any]:
        if path not in ALLOWED_GET_PATHS:
            raise ValueError(f"Blocked Kite endpoint (read-only client): {path}")
        response = self._session.get(
            f"{KITE_API_BASE}{path}",
            headers={
                "Authorization": f"token {self.credentials.api_key}:{self.credentials.access_token}",
                "X-Kite-Version": "3",
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != "success":
            raise ValueError(payload.get("message") or "Kite API request failed")
        return payload


def _equity_symbol(item: dict[str, Any]) -> str:
    symbol = str(item.get("tradingsymbol") or item.get("instrument_token") or "")
    if symbol.endswith("-BE") or symbol.endswith("-EQ"):
        symbol = symbol.rsplit("-", 1)[0]
    return symbol.upper()


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _mf_identifier(item: dict[str, Any]) -> str:
    # Kite identifies Coin holdings by ISIN; fund is a display name, not an AMFI code.
    code = str(item.get("scheme_code") or "").strip()
    if code.isdigit():
        return code
    symbol = str(item.get("tradingsymbol") or "").strip()
    if symbol:
        return symbol
    fund = str(item.get("fund") or "").strip()
    return fund if fund.isdigit() else ""
