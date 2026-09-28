"""Expand historical Nifty constituent coverage from change logs and intervals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Iterable, Literal

import pandas as pd
import requests

from .constituents import ConstituentHistoryStore, SUPPORTED_INDICES
from .research import fiscal_quarter_end_dates

NSE_INDEX_CHANGES_URL = (
    "https://archives.nseindia.com/content/indices/IndexInclExcl.xls"
)
NSE_INDEX_SHEET_NAMES = {
    "NIFTY 50": "Nifty 50",
    "NIFTY 100": "Nifty 100",
    "NIFTY 200": "Nifty 200",
}

ChangeAction = Literal["add", "remove"]


@dataclass(frozen=True)
class ReconstitutionChange:
    effective_date: date
    symbol: str
    action: ChangeAction
    index_name: str | None = None


@dataclass(frozen=True)
class MembershipInterval:
    symbol: str
    valid_from: date
    valid_to: date | None
    index_name: str | None = None


@dataclass(frozen=True)
class BackfillResult:
    index_name: str
    snapshots_written: int
    quarter_dates: tuple[str, ...]
    source: str


def load_reconstitution_changes_csv(path: str | Path) -> list[ReconstitutionChange]:
    """Load index change events from a CSV file.

    Required columns: ``effective_date``, ``symbol``, ``action``.
    Optional column: ``index_name``.
    """

    frame = _normalize_columns(pd.read_csv(path))
    required = {"effective_date", "symbol", "action"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(
            "Reconstitution CSV must include columns: "
            f"{', '.join(sorted(required))}"
        )
    changes: list[ReconstitutionChange] = []
    for row in frame.itertuples(index=False):
        action = str(row.action).strip().lower()
        if action not in {"add", "remove"}:
            raise ValueError(
                f"Unsupported reconstitution action '{row.action}'. Use add or remove."
            )
        index_name = (
            str(row.index_name).strip().upper()
            if hasattr(row, "index_name") and pd.notna(row.index_name)
            else None
        )
        changes.append(
            ReconstitutionChange(
                effective_date=_parse_date(row.effective_date),
                symbol=str(row.symbol).strip().upper(),
                action=action,
                index_name=index_name or None,
            )
        )
    return sorted(changes, key=lambda change: (change.effective_date, change.symbol))


def load_membership_intervals_csv(path: str | Path) -> list[MembershipInterval]:
    """Load membership intervals from a CSV file.

    Required columns: ``symbol``, ``valid_from``.
    Optional columns: ``valid_to``, ``index_name``.
    """

    frame = _normalize_columns(pd.read_csv(path))
    required = {"symbol", "valid_from"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(
            "Membership interval CSV must include columns: "
            f"{', '.join(sorted(required))}"
        )
    intervals: list[MembershipInterval] = []
    for row in frame.itertuples(index=False):
        valid_to = None
        if hasattr(row, "valid_to") and pd.notna(row.valid_to) and str(row.valid_to).strip():
            valid_to = _parse_date(row.valid_to)
        index_name = (
            str(row.index_name).strip().upper()
            if hasattr(row, "index_name") and pd.notna(row.index_name)
            else None
        )
        intervals.append(
            MembershipInterval(
                symbol=str(row.symbol).strip().upper(),
                valid_from=_parse_date(row.valid_from),
                valid_to=valid_to,
                index_name=index_name or None,
            )
        )
    return intervals


def load_snapshots_wide_csv(path: str | Path) -> dict[date, list[str]]:
    """Load wide membership snapshots where date columns contain active markers."""

    frame = _normalize_columns(pd.read_csv(path))
    if "symbol" not in frame.columns:
        raise ValueError("Wide constituent CSV must include a symbol column")
    date_columns = [
        column
        for column in frame.columns
        if column != "symbol" and _looks_like_date_column(column)
    ]
    if not date_columns:
        raise ValueError("Wide constituent CSV must include at least one date column")
    snapshots: dict[date, list[str]] = {}
    for column in date_columns:
        effective_date = _parse_date(column)
        active = frame[column].map(_is_active_member)
        members = frame.loc[active, "symbol"].astype(str).str.strip().str.upper().tolist()
        snapshots[effective_date] = _dedupe_symbols(members)
    return snapshots


def members_on_date(intervals: Iterable[MembershipInterval], as_of: date) -> list[str]:
    """Return symbols active on ``as_of`` using half-open ``[valid_from, valid_to)`` intervals."""

    members = [
        interval.symbol
        for interval in intervals
        if interval.valid_from <= as_of
        and (interval.valid_to is None or as_of < interval.valid_to)
    ]
    return _dedupe_symbols(members)


def members_at_date_from_changes(
    anchor_members: Iterable[str],
    changes: Iterable[ReconstitutionChange],
    as_of: date,
    *,
    anchor_date: date | None = None,
) -> list[str]:
    """Reconstruct membership on ``as_of`` by replaying changes around an anchor."""

    if anchor_date is None:
        anchor_date = max((change.effective_date for change in changes), default=as_of)
    members = set(_dedupe_symbols(list(anchor_members)))
    if as_of == anchor_date:
        return sorted(members)
    if as_of > anchor_date:
        for change in sorted(changes, key=lambda item: item.effective_date):
            if change.effective_date <= anchor_date:
                continue
            if change.effective_date > as_of:
                break
            _apply_change(members, change)
        return sorted(members)

    for change in sorted(changes, key=lambda item: item.effective_date, reverse=True):
        if change.effective_date <= as_of:
            continue
        _reverse_change(members, change)
    return sorted(members)


def quarter_end_dates_between(start: date, end: date) -> list[date]:
    return [candidate.date() for candidate in fiscal_quarter_end_dates(start, end)]


def backfill_quarter_snapshots_from_intervals(
    store: ConstituentHistoryStore,
    index_name: str,
    intervals: Iterable[MembershipInterval],
    *,
    quarter_range_start: date,
    quarter_range_end: date,
    source: str = "interval_backfill",
    skip_existing: bool = True,
) -> BackfillResult:
    filtered = [
        interval
        for interval in intervals
        if interval.index_name in {None, index_name.strip().upper()}
    ]
    return _backfill_quarter_snapshots(
        store,
        index_name,
        quarter_range_start=quarter_range_start,
        quarter_range_end=quarter_range_end,
        source=source,
        skip_existing=skip_existing,
        members_for_date=lambda as_of: members_on_date(filtered, as_of),
    )


def backfill_quarter_snapshots_from_changes(
    store: ConstituentHistoryStore,
    index_name: str,
    changes: Iterable[ReconstitutionChange],
    *,
    anchor_members: Iterable[str],
    anchor_date: date,
    quarter_range_start: date,
    quarter_range_end: date,
    source: str = "change_backfill",
    skip_existing: bool = True,
) -> BackfillResult:
    filtered = [
        change
        for change in changes
        if change.index_name in {None, index_name.strip().upper()}
    ]
    return _backfill_quarter_snapshots(
        store,
        index_name,
        quarter_range_start=quarter_range_start,
        quarter_range_end=quarter_range_end,
        source=source,
        skip_existing=skip_existing,
        members_for_date=lambda as_of: members_at_date_from_changes(
            anchor_members,
            filtered,
            as_of,
            anchor_date=anchor_date,
        ),
    )


def import_wide_snapshots_csv(
    store: ConstituentHistoryStore,
    path: str | Path,
    *,
    index_name: str,
    source: str = "wide_csv_import",
    skip_existing: bool = True,
) -> int:
    snapshots = load_snapshots_wide_csv(path)
    written = 0
    for effective_date, symbols in sorted(snapshots.items()):
        if skip_existing and _snapshot_exists(store, index_name, effective_date):
            continue
        store.record_snapshot(
            index_name,
            symbols,
            effective_date=effective_date,
            source=source,
        )
        written += 1
    return written


def normalize_nse_changes_frame(frame: pd.DataFrame, *, index_name: str) -> pd.DataFrame:
    """Normalize a parsed NSE inclusion/exclusion sheet into change events."""

    normalized = _normalize_columns(frame)
    symbol_column = _first_present(
        normalized,
        ("symbol", "security_symbol", "company_name"),
    )
    if symbol_column is None:
        raise ValueError("NSE change sheet must include a symbol or company column")
    inclusion_column = _first_present(
        normalized,
        ("inclusion_date", "date_of_inclusion", "date"),
    )
    exclusion_column = _first_present(
        normalized,
        ("exclusion_date", "date_of_exclusion"),
    )
    action_column = _first_present(normalized, ("action", "change", "remarks", "type"))
    records: list[dict[str, str]] = []
    for row in normalized.to_dict(orient="records"):
        raw_symbol = row.get(symbol_column)
        if pd.isna(raw_symbol):
            continue
        symbol = str(raw_symbol).strip().upper()
        if not symbol or symbol in {"SYMBOL", "COMPANY NAME"}:
            continue
        if inclusion_column and not pd.isna(row.get(inclusion_column)):
            records.append(
                _change_record(row[inclusion_column], symbol, "add", index_name)
            )
        if exclusion_column and not pd.isna(row.get(exclusion_column)):
            records.append(
                _change_record(row[exclusion_column], symbol, "remove", index_name)
            )
        if inclusion_column or exclusion_column:
            continue
        raw_action = row.get(action_column) if action_column else None
        raw_date = row.get(inclusion_column or exclusion_column or "date")
        action = _infer_action_text(raw_action)
        if action is None or raw_date is None or pd.isna(raw_date):
            continue
        records.append(_change_record(raw_date, symbol, action, index_name))
    return pd.DataFrame(records).drop_duplicates()


def download_nse_index_changes_csv(
    output: str | Path,
    *,
    index_name: str,
    session: requests.Session | None = None,
) -> int:
    """Download and normalize the official NSE inclusion/exclusion workbook."""

    http = session or requests.Session()
    http.headers.setdefault(
        "User-Agent",
        "Mozilla/5.0 (compatible; AIInvestmentResearch/0.1)",
    )
    response = http.get(NSE_INDEX_CHANGES_URL, timeout=30)
    response.raise_for_status()
    sheet_name = NSE_INDEX_SHEET_NAMES.get(index_name.strip().upper(), index_name)
    return export_nse_changes_csv(
        BytesIO(response.content),
        output,
        index_name=index_name,
        sheet_name=sheet_name,
    )


def export_nse_changes_csv(
    source: str | Path,
    output: str | Path,
    *,
    index_name: str,
    sheet_name: str | int | None = None,
) -> int:
    """Normalize an NSE ``IndexInclExcl`` workbook sheet to a change-event CSV."""

    frame = pd.read_excel(source, sheet_name=sheet_name)
    normalized = normalize_nse_changes_frame(frame, index_name=index_name)
    if normalized.empty:
        raise ValueError("No inclusion/exclusion events were parsed from the workbook")
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    normalized.to_csv(output_path, index=False)
    return len(normalized)


def _backfill_quarter_snapshots(
    store: ConstituentHistoryStore,
    index_name: str,
    *,
    quarter_range_start: date,
    quarter_range_end: date,
    source: str,
    skip_existing: bool,
    members_for_date,
) -> BackfillResult:
    normalized_index = index_name.strip().upper()
    if normalized_index not in SUPPORTED_INDICES:
        raise ValueError(f"Unsupported index '{index_name}'")
    quarter_dates = quarter_end_dates_between(quarter_range_start, quarter_range_end)
    written = 0
    for quarter_date in quarter_dates:
        if skip_existing and _snapshot_exists(store, normalized_index, quarter_date):
            continue
        members = members_for_date(quarter_date)
        if not members:
            continue
        store.record_snapshot(
            normalized_index,
            members,
            effective_date=quarter_date,
            source=source,
        )
        written += 1
    return BackfillResult(
        index_name=normalized_index,
        snapshots_written=written,
        quarter_dates=tuple(item.isoformat() for item in quarter_dates),
        source=source,
    )


def _snapshot_exists(
    store: ConstituentHistoryStore,
    index_name: str,
    effective_date: date,
) -> bool:
    existing = store.list_snapshots(index_name)
    return (
        not existing.empty
        and effective_date.isoformat()
        in existing["effective_date"].astype(str).tolist()
    )


def _apply_change(members: set[str], change: ReconstitutionChange) -> None:
    if change.action == "add":
        members.add(change.symbol)
    else:
        members.discard(change.symbol)


def _reverse_change(members: set[str], change: ReconstitutionChange) -> None:
    if change.action == "add":
        members.discard(change.symbol)
    else:
        members.add(change.symbol)


def _normalize_columns(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.rename(
        columns={column: column.strip().lower().replace(" ", "_") for column in frame.columns}
    )


def _parse_date(value: object) -> date:
    text = str(value).strip()
    if "T" in text:
        text = text.split("T", 1)[0]
    return pd.Timestamp(text).date()


def _looks_like_date_column(column: str) -> bool:
    text = str(column).strip()
    if not text:
        return False
    try:
        _parse_date(text)
    except (ValueError, TypeError):
        return False
    return True


def _is_active_member(value: object) -> bool:
    if pd.isna(value):
        return False
    text = str(value).strip().lower()
    return text in {"1", "x", "y", "yes", "true", "active", "member"}


def _dedupe_symbols(symbols: list[str]) -> list[str]:
    return list(dict.fromkeys(symbol.strip().upper() for symbol in symbols if str(symbol).strip()))


def _first_present(frame: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
    for candidate in candidates:
        if candidate in frame.columns:
            return candidate
    return None


def _change_record(
    raw_date: object,
    symbol: str,
    action: ChangeAction,
    index_name: str,
) -> dict[str, str]:
    return {
        "effective_date": _parse_date(raw_date).isoformat(),
        "symbol": symbol,
        "action": action,
        "index_name": index_name.strip().upper(),
    }


def _infer_action_text(raw_action: object) -> ChangeAction | None:
    if raw_action is None or pd.isna(raw_action):
        return None
    text = str(raw_action).strip().lower()
    if "incl" in text or text in {"add", "added", "inclusion"}:
        return "add"
    if "excl" in text or text in {"remove", "removed", "exclusion", "delete"}:
        return "remove"
    return None
