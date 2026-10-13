"""FIFO realized/unrealized gains and illustrative FY tax estimates (not tax advice)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable

import pandas as pd

TAX_DISCLAIMER = (
    "Illustrative estimates only — not tax advice. "
    "Confirm figures with your CA before filing."
)

EQUITY_LTCG_EXEMPTION_INR = 125_000.0
EQUITY_STCG_RATE = 0.20
EQUITY_LTCG_RATE = 0.125
DEBT_SLAB_NOTE = (
    "Debt mutual fund gains are taxed at your income-tax slab rate "
    "(no separate LTCG rate assumed here)."
)


@dataclass(frozen=True)
class FifoLot:
    acquired: date
    quantity: float
    cost_per_unit: float

    @property
    def cost(self) -> float:
        return self.quantity * self.cost_per_unit


@dataclass(frozen=True)
class RealizedGainLine:
    asset_class: str
    identifier: str
    name: str
    sell_date: date
    quantity: float
    proceeds: float
    cost: float
    gain: float
    holding_days: int
    gain_type: str  # equity_stcg | equity_ltcg | debt | other


@dataclass(frozen=True)
class UnrealizedGainLine:
    asset_class: str
    identifier: str
    name: str
    quantity: float
    cost: float
    market_value: float
    gain: float
    gain_pct: float | None


@dataclass(frozen=True)
class FiscalYearTaxEstimate:
    fiscal_year: str
    equity_stcg: float
    equity_ltcg: float
    debt_and_other: float
    estimated_tax: float
    notes: tuple[str, ...]


def fiscal_year_label(when: date) -> str:
    """Indian financial year label (Apr–Mar), e.g. FY2024-25."""

    start_year = when.year if when.month >= 4 else when.year - 1
    end_year = start_year + 1
    return f"FY{start_year}-{str(end_year)[-2:]}"


def _parse_date(value: object) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _fifo_sell(
    lots: list[FifoLot],
    quantity: float,
    sell_price: float,
    *,
    asset_class: str,
    identifier: str,
    name: str,
    sell_date: date,
    debt_fund: bool,
) -> tuple[list[RealizedGainLine], list[FifoLot]]:
    remaining = quantity
    realized: list[RealizedGainLine] = []
    updated: list[FifoLot] = []
    for lot in lots:
        if remaining <= 0:
            updated.append(lot)
            continue
        take = min(lot.quantity, remaining)
        cost = take * lot.cost_per_unit
        proceeds = take * sell_price
        gain = proceeds - cost
        holding_days = (sell_date - lot.acquired).days
        if debt_fund:
            gain_type = "debt"
        elif holding_days < 365:
            gain_type = "equity_stcg"
        else:
            gain_type = "equity_ltcg"
        realized.append(
            RealizedGainLine(
                asset_class=asset_class,
                identifier=identifier,
                name=name,
                sell_date=sell_date,
                quantity=take,
                proceeds=proceeds,
                cost=cost,
                gain=gain,
                holding_days=holding_days,
                gain_type=gain_type,
            )
        )
        remaining -= take
        leftover = lot.quantity - take
        if leftover > 0:
            updated.append(
                FifoLot(lot.acquired, leftover, lot.cost_per_unit)
            )
    if remaining > 1e-9:
        raise ValueError(
            f"Sell quantity exceeds holdings for {identifier}: short {remaining}"
        )
    return realized, updated


def equity_fifo_gains(
    trades: pd.DataFrame,
    holdings: pd.DataFrame,
    *,
    market_prices: dict[str, float],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """FIFO realized lines from sells; unrealized from open lots."""

    realized_rows: list[dict[str, object]] = []
    lots_by_symbol: dict[str, list[FifoLot]] = {}

    if not trades.empty:
        ordered = trades.sort_values("trade_date")
        for record in ordered.to_dict(orient="records"):
            symbol = str(record["symbol"])
            side = str(record["side"]).lower()
            qty = float(record["quantity"])
            price = float(record["price"])
            when = _parse_date(record["trade_date"])
            bucket = lots_by_symbol.setdefault(symbol, [])
            if side == "buy":
                bucket.append(FifoLot(when, qty, price))
            elif side == "sell":
                lines, bucket = _fifo_sell(
                    bucket,
                    qty,
                    price,
                    asset_class="equity",
                    identifier=symbol,
                    name=symbol,
                    sell_date=when,
                    debt_fund=False,
                )
                lots_by_symbol[symbol] = bucket
                for line in lines:
                    realized_rows.append(_realized_row(line))

    unrealized_rows: list[dict[str, object]] = []
    symbols = set(lots_by_symbol.keys())
    if not holdings.empty:
        symbols |= set(holdings["symbol"].astype(str))
    for symbol in sorted(symbols):
        lots = lots_by_symbol.get(symbol, [])
        if not lots and not holdings.empty:
            row = holdings.loc[holdings["symbol"].astype(str) == symbol]
            if not row.empty:
                rec = row.iloc[0]
                qty = float(rec["quantity"])
                avg = float(rec["average_price"])
                lots = [FifoLot(date.today(), qty, avg)]
        qty = sum(lot.quantity for lot in lots)
        if qty <= 0:
            continue
        cost = sum(lot.cost for lot in lots)
        mkt = market_prices.get(symbol)
        if mkt is None:
            continue
        value = qty * mkt
        unrealized_rows.append(
            {
                "asset_class": "equity",
                "identifier": symbol,
                "name": symbol,
                "quantity": qty,
                "cost": cost,
                "market_value": value,
                "gain": value - cost,
                "gain_pct": (value - cost) / cost if cost else None,
            }
        )

    return pd.DataFrame(realized_rows), pd.DataFrame(unrealized_rows)


def _is_debt_mf_category(category: str | None) -> bool:
    if not category:
        return False
    text = category.lower()
    return "debt" in text or "liquid" in text or "money market" in text


def mf_fifo_gains(
    transactions: pd.DataFrame,
    holdings: pd.DataFrame,
    *,
    navs: dict[str, float],
    scheme_categories: dict[str, str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    scheme_categories = scheme_categories or {}
    realized_rows: list[dict[str, object]] = []
    lots_by_key: dict[str, list[FifoLot]] = {}

    if not transactions.empty:
        ordered = transactions.sort_values("txn_date")
        for record in ordered.to_dict(orient="records"):
            code = str(record.get("scheme_code") or "")
            name = str(record.get("scheme_name") or code)
            key = code or name
            txn_type = str(record["txn_type"]).lower()
            when = _parse_date(record["txn_date"])
            units = float(record["units"]) if record.get("units") not in (None, "") else None
            amount = float(record["amount"])
            nav = float(record["nav"]) if record.get("nav") not in (None, "") else None
            if units is None or units <= 0:
                if nav and nav > 0:
                    units = abs(amount) / nav
                else:
                    units = abs(amount)
            cost_per = nav if nav and nav > 0 else abs(amount) / units if units else abs(amount)
            bucket = lots_by_key.setdefault(key, [])
            category = scheme_categories.get(code) or scheme_categories.get(name)
            debt = _is_debt_mf_category(category)
            if txn_type in {"purchase", "sip"}:
                bucket.append(FifoLot(when, units, cost_per))
            elif txn_type in {"redemption", "sell"}:
                sell_nav = nav if nav and nav > 0 else cost_per
                lines, bucket = _fifo_sell(
                    bucket,
                    units,
                    sell_nav,
                    asset_class="mutual_fund",
                    identifier=code or name,
                    name=name,
                    sell_date=when,
                    debt_fund=debt,
                )
                lots_by_key[key] = bucket
                for line in lines:
                    realized_rows.append(_realized_row(line))

    unrealized_rows: list[dict[str, object]] = []
    if not holdings.empty:
        for record in holdings.to_dict(orient="records"):
            code = str(record.get("scheme_code") or "")
            name = str(record.get("scheme_name") or code)
            key = code or name
            lots = lots_by_key.get(key, [])
            units = float(record.get("units") or record.get("quantity") or 0)
            if not lots and units > 0:
                avg = float(record.get("average_nav") or 0)
                lots = [FifoLot(date.today(), units, avg)]
            qty = sum(lot.quantity for lot in lots) if lots else units
            if qty <= 0:
                continue
            cost = sum(lot.cost for lot in lots) if lots else units * float(
                record.get("average_nav") or 0
            )
            nav = navs.get(code) if code else None
            if nav is None:
                continue
            value = qty * nav
            unrealized_rows.append(
                {
                    "asset_class": "mutual_fund",
                    "identifier": code or name,
                    "name": name,
                    "quantity": qty,
                    "cost": cost,
                    "market_value": value,
                    "gain": value - cost,
                    "gain_pct": (value - cost) / cost if cost else None,
                }
            )

    return pd.DataFrame(realized_rows), pd.DataFrame(unrealized_rows)


def _realized_row(line: RealizedGainLine) -> dict[str, object]:
    return {
        "asset_class": line.asset_class,
        "identifier": line.identifier,
        "name": line.name,
        "sell_date": line.sell_date.isoformat(),
        "quantity": line.quantity,
        "proceeds": line.proceeds,
        "cost": line.cost,
        "gain": line.gain,
        "holding_days": line.holding_days,
        "gain_type": line.gain_type,
        "fiscal_year": fiscal_year_label(line.sell_date),
    }


def estimate_fy_taxes(realized: pd.DataFrame) -> pd.DataFrame:
    """Roll up realized gains by FY with simple equity rates (post-2018, no grandfathering)."""

    if realized.empty:
        return pd.DataFrame(
            columns=[
                "fiscal_year",
                "equity_stcg",
                "equity_ltcg",
                "debt_and_other",
                "estimated_tax",
                "notes",
            ]
        )
    rows: list[dict[str, object]] = []
    for fy, group in realized.groupby("fiscal_year", sort=True):
        stcg = float(group.loc[group["gain_type"] == "equity_stcg", "gain"].sum())
        ltcg = float(group.loc[group["gain_type"] == "equity_ltcg", "gain"].sum())
        debt = float(
            group.loc[group["gain_type"].isin({"debt", "other"}), "gain"].sum()
        )
        taxable_ltcg = max(0.0, ltcg - EQUITY_LTCG_EXEMPTION_INR)
        tax = stcg * EQUITY_STCG_RATE + taxable_ltcg * EQUITY_LTCG_RATE
        notes: list[str] = []
        if ltcg > 0:
            notes.append(
                f"Equity LTCG exemption ₹{EQUITY_LTCG_EXEMPTION_INR:,.0f} applied once per FY."
            )
        if debt > 0:
            notes.append(DEBT_SLAB_NOTE)
        rows.append(
            {
                "fiscal_year": fy,
                "equity_stcg": stcg,
                "equity_ltcg": ltcg,
                "debt_and_other": debt,
                "estimated_tax": tax,
                "notes": "; ".join(notes) if notes else "",
            }
        )
    return pd.DataFrame(rows)


def build_capital_gains_report(
    store,
    *,
    stock_prices: dict[str, float],
    navs: dict[str, float],
    scheme_categories: dict[str, str] | None = None,
) -> dict[str, pd.DataFrame]:
    eq_realized, eq_unrealized = equity_fifo_gains(
        store.list_equity_trades(),
        store.list_equity_holdings(),
        market_prices=stock_prices,
    )
    mf_realized, mf_unrealized = mf_fifo_gains(
        store.list_mf_transactions(),
        store.list_mf_holdings(),
        navs=navs,
        scheme_categories=scheme_categories,
    )
    realized = pd.concat([eq_realized, mf_realized], ignore_index=True)
    unrealized = pd.concat([eq_unrealized, mf_unrealized], ignore_index=True)
    fy = estimate_fy_taxes(realized)
    return {
        "realized": realized,
        "unrealized": unrealized,
        "fiscal_year_estimates": fy,
    }
