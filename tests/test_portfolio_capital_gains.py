from __future__ import annotations

from datetime import date

import pandas as pd

from src.investing.portfolio_capital_gains import (
    equity_fifo_gains,
    estimate_fy_taxes,
    fiscal_year_label,
    mf_fifo_gains,
)


def test_fiscal_year_label() -> None:
    assert fiscal_year_label(date(2024, 6, 1)) == "FY2024-25"
    assert fiscal_year_label(date(2025, 1, 15)) == "FY2024-25"


def test_equity_fifo_realized_stcg_vs_ltcg() -> None:
    trades = pd.DataFrame(
        [
            {"trade_date": "2024-01-01", "symbol": "AAA", "side": "buy", "quantity": 10, "price": 100},
            {"trade_date": "2024-06-01", "symbol": "AAA", "side": "sell", "quantity": 5, "price": 120},
            {"trade_date": "2025-06-01", "symbol": "AAA", "side": "sell", "quantity": 5, "price": 150},
        ]
    )
    holdings = pd.DataFrame()
    realized, unrealized = equity_fifo_gains(trades, holdings, market_prices={})
    assert len(realized) == 2
    assert realized.iloc[0]["gain_type"] == "equity_stcg"
    assert realized.iloc[0]["gain"] == 100.0
    assert realized.iloc[1]["gain_type"] == "equity_ltcg"
    assert unrealized.empty


def test_equity_fifo_unrealized() -> None:
    trades = pd.DataFrame(
        [
            {"trade_date": "2024-01-01", "symbol": "AAA", "side": "buy", "quantity": 10, "price": 100},
        ]
    )
    holdings = pd.DataFrame([{"symbol": "AAA", "quantity": 10, "average_price": 100}])
    _, unrealized = equity_fifo_gains(trades, holdings, market_prices={"AAA": 110})
    assert len(unrealized) == 1
    assert unrealized.iloc[0]["gain"] == 100.0


def test_mf_fifo_sip_and_redemption() -> None:
    txns = pd.DataFrame(
        [
            {
                "txn_date": "2024-05-01",
                "scheme_code": "119063",
                "scheme_name": "Test Debt Fund",
                "txn_type": "sip",
                "amount": 10000,
                "units": 100,
                "nav": 100,
            },
            {
                "txn_date": "2025-05-01",
                "scheme_code": "119063",
                "scheme_name": "Test Debt Fund",
                "txn_type": "redemption",
                "amount": 5500,
                "units": 50,
                "nav": 110,
            },
        ]
    )
    holdings = pd.DataFrame(
        [{"scheme_code": "119063", "scheme_name": "Test Debt Fund", "units": 50, "average_nav": 100}]
    )
    realized, unrealized = mf_fifo_gains(
        txns,
        holdings,
        navs={"119063": 115},
        scheme_categories={"119063": "Debt Scheme - Corporate Bond"},
    )
    assert len(realized) == 1
    assert realized.iloc[0]["gain_type"] == "debt"
    assert realized.iloc[0]["gain"] == 500.0
    assert len(unrealized) == 1


def test_estimate_fy_taxes_equity() -> None:
    realized = pd.DataFrame(
        [
            {
                "fiscal_year": "FY2024-25",
                "gain_type": "equity_stcg",
                "gain": 100_000,
            },
            {
                "fiscal_year": "FY2024-25",
                "gain_type": "equity_ltcg",
                "gain": 200_000,
            },
        ]
    )
    fy = estimate_fy_taxes(realized)
    assert len(fy) == 1
    row = fy.iloc[0]
    assert row["equity_stcg"] == 100_000
    taxable_ltcg = 200_000 - 125_000
    assert row["estimated_tax"] == 100_000 * 0.20 + taxable_ltcg * 0.125
