"""Historical Nifty index constituent membership for point-in-time benchmarking."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Iterable, Iterator

import pandas as pd

from .filings import IST

CONSTITUENT_STORE_VERSION = 1
SUPPORTED_INDICES = ("NIFTY 50", "NIFTY 100", "NIFTY 200")


@dataclass(frozen=True)
class ConstituentSnapshot:
    index_name: str
    effective_date: str
    symbols: tuple[str, ...]
    source: str

    def to_record(self) -> dict[str, object]:
        return {
            "index_name": self.index_name,
            "effective_date": self.effective_date,
            "symbols": ";".join(self.symbols),
            "symbol_count": len(self.symbols),
            "source": self.source,
        }


class ConstituentHistoryStore:
    """Persist official Nifty constituent snapshots for as-of lookups."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def record_snapshot(
        self,
        index_name: str,
        symbols: list[str],
        *,
        effective_date: date,
        source: str,
    ) -> str:
        normalized_index = index_name.strip().upper()
        normalized_symbols = _normalize_symbols(symbols)
        if not normalized_symbols:
            raise ValueError("At least one constituent symbol is required")
        snapshot_key = _snapshot_key(normalized_index, effective_date.isoformat())
        created_at = datetime.now(tz=IST).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO nifty_constituent_snapshots (
                    snapshot_key,
                    index_name,
                    effective_date,
                    symbols_json,
                    symbol_count,
                    source,
                    store_version,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_key,
                    normalized_index,
                    effective_date.isoformat(),
                    json.dumps(normalized_symbols),
                    len(normalized_symbols),
                    source.strip(),
                    CONSTITUENT_STORE_VERSION,
                    created_at,
                ),
            )
        return snapshot_key

    def members_as_of(self, index_name: str, as_of: date) -> list[str] | None:
        """Return the latest recorded membership on or before ``as_of``."""

        normalized_index = index_name.strip().upper()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT symbols_json
                FROM nifty_constituent_snapshots
                WHERE index_name = ?
                  AND effective_date <= ?
                ORDER BY effective_date DESC, created_at DESC
                LIMIT 1
                """,
                (normalized_index, as_of.isoformat()),
            ).fetchone()
        if row is None:
            return None
        return _parse_symbols_json(row["symbols_json"])

    def list_snapshots(self, index_name: str | None = None) -> pd.DataFrame:
        query = "SELECT * FROM nifty_constituent_snapshots"
        params: list[object] = []
        if index_name is not None:
            query += " WHERE index_name = ?"
            params.append(index_name.strip().upper())
        query += " ORDER BY effective_date DESC, index_name"
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return (
            pd.DataFrame([dict(row) for row in rows], columns=rows[0].keys())
            if rows
            else pd.DataFrame()
        )

    def counts(self) -> dict[str, int]:
        with self._connect() as connection:
            snapshots = connection.execute(
                "SELECT COUNT(*) FROM nifty_constituent_snapshots"
            ).fetchone()[0]
        return {"constituent_snapshots": snapshots}

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS nifty_constituent_snapshots (
                    snapshot_key TEXT PRIMARY KEY,
                    index_name TEXT NOT NULL,
                    effective_date TEXT NOT NULL,
                    symbols_json TEXT NOT NULL,
                    symbol_count INTEGER NOT NULL CHECK (symbol_count > 0),
                    source TEXT NOT NULL,
                    store_version INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE (index_name, effective_date)
                );

                CREATE INDEX IF NOT EXISTS idx_nifty_constituents_index_date
                ON nifty_constituent_snapshots(index_name, effective_date);
                """)


@dataclass(frozen=True)
class ConstituentArchiveResult:
    index_name: str
    effective_date: str
    symbol_count: int
    status: str


def latest_fiscal_quarter_end(as_of: date | None = None) -> date:
    """Return the latest Indian fiscal quarter-end on or before ``as_of``."""

    from .research import fiscal_quarter_end_dates

    reference = as_of or datetime.now(tz=IST).date()
    candidates = fiscal_quarter_end_dates(
        date(reference.year - 1, reference.month, reference.day),
        reference,
    )
    if not candidates:
        return reference
    return candidates[-1].date()


def archive_current_constituents(
    store: ConstituentHistoryStore,
    provider,
    *,
    effective_date: date | None = None,
    skip_existing: bool = True,
    source: str = "scheduled_archive",
) -> list[ConstituentArchiveResult]:
    """Download and record the current official index membership."""

    effective = effective_date or latest_fiscal_quarter_end()
    frame = provider.fetch()
    symbols = frame["symbol"].tolist()
    if skip_existing:
        existing = store.list_snapshots(provider.index_name)
        if (
            not existing.empty
            and effective.isoformat() in existing["effective_date"].astype(str).tolist()
        ):
            return [
                ConstituentArchiveResult(
                    index_name=provider.index_name,
                    effective_date=effective.isoformat(),
                    symbol_count=len(symbols),
                    status="skipped",
                )
            ]
    store.record_snapshot(
        provider.index_name,
        symbols,
        effective_date=effective,
        source=source,
    )
    return [
        ConstituentArchiveResult(
            index_name=provider.index_name,
            effective_date=effective.isoformat(),
            symbol_count=len(symbols),
            status="recorded",
        )
    ]


def import_snapshots_csv(
    store: ConstituentHistoryStore,
    path: str | Path,
    *,
    index_name: str,
    source: str = "csv_import",
) -> int:
    """Import constituent snapshots from a long-format CSV file.

    Required columns: ``effective_date``, ``symbol``.
    """

    frame = pd.read_csv(path)
    required = {"effective_date", "symbol"}
    missing = required - {column.strip().lower() for column in frame.columns}
    if missing:
        raise ValueError(
            f"Constituent CSV must include columns: {', '.join(sorted(required))}"
        )
    normalized = frame.rename(
        columns={column: column.strip().lower() for column in frame.columns}
    )
    imported = 0
    for effective_date, group in normalized.groupby("effective_date"):
        symbols = [
            str(symbol).strip().upper()
            for symbol in group["symbol"].tolist()
            if str(symbol).strip()
        ]
        store.record_snapshot(
            index_name,
            symbols,
            effective_date=_parse_effective_date(effective_date),
            source=source,
        )
        imported += 1
    return imported


def constituent_coverage(
    store: ConstituentHistoryStore,
    index_name: str,
    as_of_dates: Iterable[date],
) -> pd.DataFrame:
    """Report whether historical membership exists for each as-of date."""

    records: list[dict[str, object]] = []
    for as_of in as_of_dates:
        members = store.members_as_of(index_name, as_of)
        records.append(
            {
                "index_name": index_name.strip().upper(),
                "as_of": as_of.isoformat(),
                "has_snapshot": members is not None,
                "symbol_count": len(members) if members else 0,
            }
        )
    return pd.DataFrame(records)


def resolve_portfolio_symbols(
    *,
    benchmark_index: str,
    as_of: date,
    store: ConstituentHistoryStore | None,
    use_historical: bool,
    fallback_symbols: list[str] | None,
) -> tuple[list[str], str]:
    """Resolve portfolio benchmark members and describe the membership source."""

    if use_historical and store is not None:
        historical = store.members_as_of(benchmark_index, as_of)
        if historical:
            return historical, "historical_constituents"
    if fallback_symbols:
        return _normalize_symbols(fallback_symbols), "current_constituents"
    return [], "none"


def _normalize_symbols(symbols: list[str]) -> list[str]:
    normalized = [symbol.strip().upper() for symbol in symbols]
    if any(not symbol for symbol in normalized):
        raise ValueError("Symbols cannot be blank")
    return list(dict.fromkeys(normalized))


def _snapshot_key(index_name: str, effective_date: str) -> str:
    payload = f"{index_name}|{effective_date}|{CONSTITUENT_STORE_VERSION}"
    return sha256(payload.encode("utf-8")).hexdigest()


def _parse_effective_date(value: object) -> date:
    text = str(value).strip()
    if "T" in text:
        text = text.split("T", 1)[0]
    return date.fromisoformat(text)


def _parse_symbols_json(value: str) -> list[str]:
    parsed = json.loads(value)
    if not isinstance(parsed, list):
        raise ValueError("Stored constituent snapshot is not a symbol list")
    return [str(symbol).strip().upper() for symbol in parsed if str(symbol).strip()]
