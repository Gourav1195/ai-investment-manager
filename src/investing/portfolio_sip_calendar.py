"""Infer recurring SIP schedules and upcoming instalment dates from MF history."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd


@dataclass(frozen=True)
class SipSchedule:
    scheme_code: str | None
    scheme_name: str
    day_of_month: int
    typical_amount: float
    last_sip_date: date
    sip_count: int
    source: str = "inferred"


@dataclass(frozen=True)
class SipScheduleOverride:
    scheme_code: str | None
    scheme_name: str
    day_of_month: int
    amount_inr: float
    enabled: bool = True


def infer_sip_schedules(mf_transactions: pd.DataFrame) -> list[SipSchedule]:
    """Build one schedule per fund from labelled SIP rows in transaction history."""

    if mf_transactions.empty:
        return []
    frame = mf_transactions.copy()
    mask = frame["txn_type"].astype(str).str.lower().eq("sip")
    sips = frame.loc[mask]
    if sips.empty:
        return []

    schedules: list[SipSchedule] = []
    group_cols = ["scheme_code", "scheme_name"]
    for (code, name), group in sips.groupby(group_cols, dropna=False):
        dates = [_parse_date(value) for value in group["txn_date"].tolist()]
        dates = [item for item in dates if item is not None]
        if not dates:
            continue
        days = [item.day for item in dates]
        day_of_month = int(pd.Series(days).mode().iloc[0])
        amounts = [float(value) for value in group["amount"].tolist() if value is not None]
        typical = float(pd.Series(amounts).median()) if amounts else 0.0
        schedules.append(
            SipSchedule(
                scheme_code=str(code).strip() if code and str(code).strip() else None,
                scheme_name=str(name),
                day_of_month=day_of_month,
                typical_amount=typical,
                last_sip_date=max(dates),
                sip_count=len(dates),
                source="inferred",
            )
        )
    return sorted(schedules, key=lambda item: item.scheme_name.casefold())


def parse_sip_overrides(raw: list[dict[str, object]]) -> list[SipScheduleOverride]:
    overrides: list[SipScheduleOverride] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("scheme_name") or "").strip()
        if not name:
            continue
        try:
            day = int(item["day_of_month"])
            amount = float(item["amount_inr"])
        except (KeyError, TypeError, ValueError):
            continue
        if day < 1 or day > 31 or amount <= 0:
            continue
        code = str(item.get("scheme_code") or "").strip() or None
        enabled = bool(item.get("enabled", True))
        overrides.append(
            SipScheduleOverride(
                scheme_code=code,
                scheme_name=name,
                day_of_month=day,
                amount_inr=amount,
                enabled=enabled,
            )
        )
    return overrides


def overrides_to_json(overrides: list[SipScheduleOverride]) -> list[dict[str, object]]:
    return [
        {
            "scheme_code": item.scheme_code,
            "scheme_name": item.scheme_name,
            "day_of_month": item.day_of_month,
            "amount_inr": item.amount_inr,
            "enabled": item.enabled,
        }
        for item in overrides
    ]


def resolve_sip_schedules(
    mf_transactions: pd.DataFrame,
    overrides: list[SipScheduleOverride],
) -> list[SipSchedule]:
    """Merge inferred SIP schedules with manual overrides (overrides win)."""

    inferred = infer_sip_schedules(mf_transactions)
    by_key: dict[tuple[str | None, str], SipSchedule] = {}
    for schedule in inferred:
        key = (schedule.scheme_code, schedule.scheme_name.casefold())
        by_key[key] = schedule
    for override in overrides:
        if not override.enabled:
            key = (override.scheme_code, override.scheme_name.casefold())
            by_key.pop(key, None)
            continue
        key = (override.scheme_code, override.scheme_name.casefold())
        by_key[key] = SipSchedule(
            scheme_code=override.scheme_code,
            scheme_name=override.scheme_name,
            day_of_month=override.day_of_month,
            typical_amount=override.amount_inr,
            last_sip_date=date.today(),
            sip_count=0,
            source="manual",
        )
    return sorted(by_key.values(), key=lambda item: item.scheme_name.casefold())


def detect_sip_changes(
    mf_transactions: pd.DataFrame,
    *,
    amount_tolerance: float = 0.10,
) -> pd.DataFrame:
    """Flag recent SIP amount or debit-day shifts per fund."""

    if mf_transactions.empty:
        return pd.DataFrame(columns=["scheme_name", "scheme_code", "change_type", "detail"])
    mask = mf_transactions["txn_type"].astype(str).str.lower().eq("sip")
    sips = mf_transactions.loc[mask].copy()
    if sips.empty:
        return pd.DataFrame(columns=["scheme_name", "scheme_code", "change_type", "detail"])

    rows: list[dict[str, str]] = []
    group_cols = ["scheme_code", "scheme_name"]
    for (code, name), group in sips.groupby(group_cols, dropna=False):
        ordered = group.sort_values("txn_date")
        if len(ordered) < 3:
            continue
        amounts = [float(value) for value in ordered["amount"].tolist() if value is not None]
        dates = [_parse_date(value) for value in ordered["txn_date"].tolist()]
        dates = [item for item in dates if item is not None]
        if len(amounts) < 3 or len(dates) < 3:
            continue
        recent_amt = float(pd.Series(amounts[-2:]).median())
        prior_amt = float(pd.Series(amounts[:-2]).median())
        if prior_amt > 0 and abs(recent_amt - prior_amt) / prior_amt >= amount_tolerance:
            rows.append(
                {
                    "scheme_name": str(name),
                    "scheme_code": str(code).strip() if code else "",
                    "change_type": "amount",
                    "detail": f"SIP amount moved from about ₹{prior_amt:,.0f} to ₹{recent_amt:,.0f}",
                }
            )
        recent_days = [item.day for item in dates[-2:]]
        prior_days = [item.day for item in dates[:-2]]
        recent_dom = int(pd.Series(recent_days).mode().iloc[0])
        prior_dom = int(pd.Series(prior_days).mode().iloc[0])
        if recent_dom != prior_dom:
            rows.append(
                {
                    "scheme_name": str(name),
                    "scheme_code": str(code).strip() if code else "",
                    "change_type": "debit_day",
                    "detail": f"SIP debit day shifted from {prior_dom} to {recent_dom}",
                }
            )
    return pd.DataFrame(rows)


def upcoming_sip_dates(
    schedules: list[SipSchedule],
    *,
    as_of: date | None = None,
    horizon_days: int = 90,
) -> pd.DataFrame:
    """List expected SIP debits between ``as_of`` and ``as_of + horizon_days``."""

    as_of = as_of or date.today()
    end = as_of + timedelta(days=horizon_days)
    rows: list[dict[str, object]] = []
    for schedule in schedules:
        cursor = _next_sip_on_or_after(as_of, schedule.day_of_month)
        while cursor <= end:
            rows.append(
                {
                    "due_date": cursor.isoformat(),
                    "scheme_name": schedule.scheme_name,
                    "scheme_code": schedule.scheme_code,
                    "amount_inr": schedule.typical_amount,
                    "typical_day": schedule.day_of_month,
                }
            )
            cursor = _add_one_month(cursor, schedule.day_of_month)
    if not rows:
        return pd.DataFrame(
            columns=["due_date", "scheme_name", "scheme_code", "amount_inr", "typical_day"]
        )
    frame = pd.DataFrame(rows)
    return frame.sort_values(["due_date", "scheme_name"]).reset_index(drop=True)


def monthly_sip_total(schedules: list[SipSchedule]) -> float:
    return sum(schedule.typical_amount for schedule in schedules)


def _parse_date(value: object) -> date | None:
    text = str(value).strip()
    if not text:
        return None
    if "T" in text:
        text = text.split("T", 1)[0]
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _clamp_day(year: int, month: int, day: int) -> date:
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(day, last))


def _next_sip_on_or_after(as_of: date, day_of_month: int) -> date:
    candidate = _clamp_day(as_of.year, as_of.month, day_of_month)
    if candidate < as_of:
        month = as_of.month + 1
        year = as_of.year
        if month > 12:
            month = 1
            year += 1
        candidate = _clamp_day(year, month, day_of_month)
    return candidate


def _add_one_month(current: date, day_of_month: int) -> date:
    month = current.month + 1
    year = current.year
    if month > 12:
        month = 1
        year += 1
    return _clamp_day(year, month, day_of_month)
