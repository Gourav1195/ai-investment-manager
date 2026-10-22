"""Local SQLite storage for Zerodha portfolio imports and sync snapshots."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
import sqlite3
from pathlib import Path
from typing import Iterator

import pandas as pd

from .filings import IST

PORTFOLIO_STORE_VERSION = 4


@dataclass(frozen=True)
class ImportSummary:
    import_key: str
    source: str
    kind: str
    file_name: str
    row_count: int
    imported_at: str


class PortfolioStore:
    """Persist equity holdings, mutual fund holdings, and equity trades."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def record_import(
        self,
        *,
        source: str,
        kind: str,
        file_name: str,
        row_count: int,
    ) -> str:
        imported_at = datetime.now(tz=IST).isoformat()
        import_key = f"{kind}:{file_name}:{imported_at}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO portfolio_imports (
                    import_key, source, kind, file_name, row_count, imported_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (import_key, source, kind, file_name, row_count, imported_at),
            )
        return import_key

    def replace_equity_holdings(
        self,
        frame: pd.DataFrame,
        *,
        source: str,
        import_key: str,
    ) -> int:
        """Replace the current equity holdings snapshot."""

        required = {"symbol", "quantity", "average_price"}
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(f"Equity holdings missing columns: {sorted(missing)}")
        imported_at = datetime.now(tz=IST).isoformat()
        rows = 0
        with self._connect() as connection:
            connection.execute("DELETE FROM equity_holdings")
            for record in frame.to_dict(orient="records"):
                connection.execute(
                    """
                    INSERT INTO equity_holdings (
                        symbol, isin, quantity, average_price, product,
                        exchange, source, import_key, imported_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(record.get("symbol", "")).strip().upper(),
                        _optional_str(record.get("isin")),
                        float(record["quantity"]),
                        float(record["average_price"]),
                        _optional_str(record.get("product")),
                        _optional_str(record.get("exchange")),
                        source,
                        import_key,
                        imported_at,
                    ),
                )
                rows += 1
        return rows

    def replace_mf_holdings(
        self,
        frame: pd.DataFrame,
        *,
        source: str,
        import_key: str,
    ) -> int:
        required = {"scheme_name", "units"}
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(f"MF holdings missing columns: {sorted(missing)}")
        imported_at = datetime.now(tz=IST).isoformat()
        rows = 0
        with self._connect() as connection:
            connection.execute("DELETE FROM mf_holdings")
            for record in frame.to_dict(orient="records"):
                connection.execute(
                    """
                    INSERT INTO mf_holdings (
                        scheme_code, scheme_name, folio, units, average_nav,
                        source, import_key, imported_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        _optional_str(record.get("scheme_code")),
                        str(record["scheme_name"]).strip(),
                        _optional_str(record.get("folio")),
                        float(record["units"]),
                        _optional_float(record.get("average_nav")),
                        source,
                        import_key,
                        imported_at,
                    ),
                )
                rows += 1
        return rows

    def append_equity_trades(
        self,
        frame: pd.DataFrame,
        *,
        source: str,
        import_key: str,
        replace_existing: bool = False,
    ) -> int:
        required = {"trade_date", "symbol", "side", "quantity", "price"}
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(f"Tradebook missing columns: {sorted(missing)}")
        imported_at = datetime.now(tz=IST).isoformat()
        rows = 0
        with self._connect() as connection:
            if replace_existing:
                connection.execute("DELETE FROM equity_trades")
            for record in frame.to_dict(orient="records"):
                connection.execute(
                    """
                    INSERT INTO equity_trades (
                        trade_date, symbol, side, quantity, price, exchange,
                        trade_id, source, import_key, imported_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(record["trade_date"]),
                        str(record["symbol"]).strip().upper(),
                        str(record["side"]).strip().lower(),
                        float(record["quantity"]),
                        float(record["price"]),
                        _optional_str(record.get("exchange")),
                        _optional_str(record.get("trade_id")),
                        source,
                        import_key,
                        imported_at,
                    ),
                )
                rows += 1
        return rows

    def list_equity_holdings(self) -> pd.DataFrame:
        return self._read_table("equity_holdings")

    def list_mf_holdings(self) -> pd.DataFrame:
        return self._read_table("mf_holdings")

    def list_equity_trades(self) -> pd.DataFrame:
        return self._read_table("equity_trades", order_by="trade_date")

    def append_mf_transactions(
        self,
        frame: pd.DataFrame,
        *,
        source: str,
        import_key: str,
        replace_existing: bool = False,
    ) -> int:
        imported_at = datetime.now(tz=IST).isoformat()
        rows = 0
        with self._connect() as connection:
            if replace_existing:
                connection.execute("DELETE FROM mf_transactions")
            for record in frame.to_dict(orient="records"):
                txn_key = (
                    f"{record.get('txn_date')}:{record.get('scheme_code') or record.get('scheme_name')}:"
                    f"{record.get('txn_type')}:{record.get('amount')}:{rows}"
                )
                connection.execute(
                    """
                    INSERT OR REPLACE INTO mf_transactions (
                        txn_key, scheme_code, scheme_name, txn_date, txn_type,
                        amount, units, nav, source, import_key, imported_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        txn_key,
                        _optional_str(record.get("scheme_code")),
                        str(record.get("scheme_name", "")),
                        str(record["txn_date"]),
                        str(record["txn_type"]),
                        float(record["amount"]),
                        _optional_float(record.get("units")),
                        _optional_float(record.get("nav")),
                        source,
                        import_key,
                        imported_at,
                    ),
                )
                rows += 1
        return rows

    def list_mf_transactions(self) -> pd.DataFrame:
        return self._read_table("mf_transactions", order_by="txn_date")

    def list_imports(self) -> pd.DataFrame:
        return self._read_table("portfolio_imports", order_by="imported_at DESC")

    def latest_price_cache(self) -> dict[str, float]:
        frame = self._read_table("price_cache", order_by="price_date DESC")
        if frame.empty:
            return {}
        latest = frame.sort_values("price_date").groupby("symbol", as_index=False).tail(1)
        return {
            str(row["symbol"]): float(row["price"])
            for row in latest.to_dict(orient="records")
        }

    def latest_nav_cache(self) -> dict[str, float]:
        frame = self._read_table("nav_cache", order_by="nav_date DESC")
        if frame.empty:
            return {}
        latest = frame.sort_values("nav_date").groupby("scheme_code", as_index=False).tail(1)
        return {
            str(row["scheme_code"]): float(row["nav"])
            for row in latest.to_dict(orient="records")
        }

    def latest_market_data_dates(self) -> tuple[str | None, str | None]:
        """Return (latest_stock_price_date, latest_nav_date) from SQLite cache."""

        prices = self._read_table("price_cache", order_by="price_date DESC")
        navs = self._read_table("nav_cache", order_by="nav_date DESC")
        stock_date = str(prices.iloc[0]["price_date"])[:10] if not prices.empty else None
        nav_date = str(navs.iloc[0]["nav_date"])[:10] if not navs.empty else None
        return stock_date, nav_date

    def replace_scheme_master(self, frame: pd.DataFrame) -> int:
        imported_at = datetime.now(tz=IST).isoformat()
        with self._connect() as connection:
            connection.execute("DELETE FROM mf_scheme_master")
            for record in frame.to_dict(orient="records"):
                connection.execute(
                    """
                    INSERT INTO mf_scheme_master (
                        scheme_code, scheme_name, category, plan_type, option_type,
                        is_direct, is_growth, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(record["scheme_code"]),
                        str(record["scheme_name"]),
                        str(record["category"]),
                        str(record["plan_type"]),
                        str(record["option_type"]),
                        int(record["is_direct"]),
                        int(record["is_growth"]),
                        imported_at,
                    ),
                )
        return len(frame)

    def upsert_scheme_meta(
        self,
        scheme_code: str,
        *,
        scheme_name: str,
        category: str | None,
        plan_type: str | None,
        option_type: str | None,
    ) -> None:
        updated_at = datetime.now(tz=IST).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO mf_scheme_meta (
                    scheme_code, scheme_name, category, plan_type, option_type, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(scheme_code) DO UPDATE SET
                    scheme_name = excluded.scheme_name,
                    category = COALESCE(excluded.category, mf_scheme_meta.category),
                    plan_type = COALESCE(excluded.plan_type, mf_scheme_meta.plan_type),
                    option_type = COALESCE(excluded.option_type, mf_scheme_meta.option_type),
                    updated_at = excluded.updated_at
                """,
                (
                    scheme_code,
                    scheme_name,
                    category,
                    plan_type,
                    option_type,
                    updated_at,
                ),
            )

    def get_scheme_master_row(self, scheme_code: str) -> dict[str, str | None]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT scheme_code, scheme_name, category, plan_type, option_type
                FROM mf_scheme_master
                WHERE scheme_code = ?
                """,
                (scheme_code,),
            ).fetchone()
        if not row:
            return {}
        return {key: row[key] for key in row.keys()}

    def get_scheme_meta(self, scheme_code: str) -> dict[str, str | None]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT scheme_code, scheme_name, category, plan_type, option_type
                FROM mf_scheme_meta
                WHERE scheme_code = ?
                """,
                (scheme_code,),
            ).fetchone()
            if row:
                return {key: row[key] for key in row.keys()}
            master = connection.execute(
                """
                SELECT scheme_code, scheme_name, category, plan_type, option_type
                FROM mf_scheme_master
                WHERE scheme_code = ?
                """,
                (scheme_code,),
            ).fetchone()
            if not master:
                return {}
            return {key: master[key] for key in master.keys()}

    def list_peer_scheme_codes(
        self,
        *,
        category: str,
        plan_type: str,
        option_type: str,
        exclude_code: str,
        limit: int = 60,
    ) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT scheme_code
                FROM mf_scheme_master
                WHERE category = ?
                  AND plan_type = ?
                  AND option_type = ?
                  AND scheme_code != ?
                ORDER BY scheme_name
                LIMIT ?
                """,
                (category, plan_type, option_type, exclude_code, limit),
            ).fetchall()
        return [str(row["scheme_code"]) for row in rows]

    def scheme_master_count(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM mf_scheme_master"
            ).fetchone()
        return int(row["count"]) if row else 0

    def list_scheme_master_options(self, *, query: str = "", limit: int = 200) -> pd.DataFrame:
        with self._connect() as connection:
            if query:
                return pd.read_sql_query(
                    """
                    SELECT scheme_code, scheme_name, category, plan_type, option_type
                    FROM mf_scheme_master
                    WHERE scheme_name LIKE ? OR scheme_code LIKE ?
                    ORDER BY scheme_name
                    LIMIT ?
                    """,
                    connection,
                    params=(f"%{query}%", f"%{query}%", limit),
                )
            return pd.read_sql_query(
                """
                SELECT scheme_code, scheme_name, category, plan_type, option_type
                FROM mf_scheme_master
                ORDER BY scheme_name
                LIMIT ?
                """,
                connection,
                params=(limit,),
            )

    def upsert_nav_history(
        self,
        scheme_code: str,
        rows: list[tuple[str, float]],
    ) -> int:
        with self._connect() as connection:
            for nav_date, nav in rows:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO nav_cache (scheme_code, nav_date, nav)
                    VALUES (?, ?, ?)
                    """,
                    (scheme_code, nav_date, float(nav)),
                )
        return len(rows)

    def has_nav_history(self, scheme_code: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM nav_cache WHERE scheme_code = ? LIMIT 1",
                (scheme_code,),
            ).fetchone()
        return row is not None

    def get_nav_history(self, scheme_code: str) -> pd.DataFrame:
        with self._connect() as connection:
            return pd.read_sql_query(
                """
                SELECT nav_date, nav
                FROM nav_cache
                WHERE scheme_code = ?
                ORDER BY nav_date
                """,
                connection,
                params=(scheme_code,),
            )

    def replace_mf_disclosure_holdings(
        self,
        scheme_code: str,
        as_of: str,
        frame: pd.DataFrame,
        *,
        source: str,
        import_key: str,
    ) -> int:
        code = str(scheme_code).strip()
        if not code:
            raise ValueError("scheme_code is required for portfolio disclosure holdings.")
        imported_at = datetime.now(tz=IST).isoformat()
        rows = 0
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM mf_disclosure_holdings WHERE scheme_code = ? AND as_of = ?",
                (code, as_of),
            )
            for record in frame.to_dict(orient="records"):
                connection.execute(
                    """
                    INSERT OR REPLACE INTO mf_disclosure_holdings (
                        scheme_code, as_of, isin, security_name, pct_nav, instrument_type,
                        source, import_key, imported_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        code,
                        as_of,
                        str(record["isin"]).strip().upper(),
                        str(record.get("security_name") or record["isin"]),
                        float(record["pct_nav"]),
                        _optional_str(record.get("instrument_type")),
                        source,
                        import_key,
                        imported_at,
                    ),
                )
                rows += 1
        return rows

    def get_mf_disclosure_holdings(self, scheme_code: str, *, as_of: str | None = None) -> pd.DataFrame:
        code = str(scheme_code).strip()
        with self._connect() as connection:
            if as_of:
                return pd.read_sql_query(
                    """
                    SELECT isin, security_name, pct_nav, instrument_type, as_of
                    FROM mf_disclosure_holdings
                    WHERE scheme_code = ? AND as_of = ?
                    ORDER BY pct_nav DESC
                    """,
                    connection,
                    params=(code, as_of),
                )
            return pd.read_sql_query(
                """
                SELECT isin, security_name, pct_nav, instrument_type, as_of
                FROM mf_disclosure_holdings
                WHERE scheme_code = ?
                ORDER BY as_of DESC, pct_nav DESC
                """,
                connection,
                params=(code,),
            )

    def list_mf_disclosure_scheme_codes(self) -> list[str]:
        frame = self._read_table("mf_disclosure_holdings")
        if frame.empty:
            return []
        return sorted(frame["scheme_code"].astype(str).unique().tolist())

    def latest_disclosure_as_of(self, scheme_code: str) -> str | None:
        frame = self.get_mf_disclosure_holdings(scheme_code)
        if frame.empty:
            return None
        return str(frame.iloc[0]["as_of"])[:10]

    def _read_table(self, table: str, order_by: str = "rowid") -> pd.DataFrame:
        with self._connect() as connection:
            return pd.read_sql_query(
                f"SELECT * FROM {table} ORDER BY {order_by}",
                connection,
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS portfolio_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS portfolio_imports (
                    import_key TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    row_count INTEGER NOT NULL,
                    imported_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS equity_holdings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    isin TEXT,
                    quantity REAL NOT NULL,
                    average_price REAL NOT NULL,
                    product TEXT,
                    exchange TEXT,
                    source TEXT NOT NULL,
                    import_key TEXT NOT NULL,
                    imported_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS mf_holdings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scheme_code TEXT,
                    scheme_name TEXT NOT NULL,
                    folio TEXT,
                    units REAL NOT NULL,
                    average_nav REAL,
                    source TEXT NOT NULL,
                    import_key TEXT NOT NULL,
                    imported_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS equity_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trade_date TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    price REAL NOT NULL,
                    exchange TEXT,
                    trade_id TEXT,
                    source TEXT NOT NULL,
                    import_key TEXT NOT NULL,
                    imported_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS mf_transactions (
                    txn_key TEXT PRIMARY KEY,
                    scheme_code TEXT,
                    scheme_name TEXT NOT NULL,
                    txn_date TEXT NOT NULL,
                    txn_type TEXT NOT NULL,
                    amount REAL NOT NULL,
                    units REAL,
                    nav REAL,
                    source TEXT NOT NULL,
                    import_key TEXT NOT NULL,
                    imported_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS nav_cache (
                    scheme_code TEXT NOT NULL,
                    nav_date TEXT NOT NULL,
                    nav REAL NOT NULL,
                    PRIMARY KEY (scheme_code, nav_date)
                );

                CREATE TABLE IF NOT EXISTS price_cache (
                    symbol TEXT NOT NULL,
                    price_date TEXT NOT NULL,
                    price REAL NOT NULL,
                    PRIMARY KEY (symbol, price_date)
                );

                CREATE TABLE IF NOT EXISTS mf_scheme_master (
                    scheme_code TEXT PRIMARY KEY,
                    scheme_name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    plan_type TEXT NOT NULL,
                    option_type TEXT NOT NULL,
                    is_direct INTEGER NOT NULL,
                    is_growth INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS mf_scheme_meta (
                    scheme_code TEXT PRIMARY KEY,
                    scheme_name TEXT NOT NULL,
                    category TEXT,
                    plan_type TEXT,
                    option_type TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS mf_disclosure_holdings (
                    scheme_code TEXT NOT NULL,
                    as_of TEXT NOT NULL,
                    isin TEXT NOT NULL,
                    security_name TEXT NOT NULL,
                    pct_nav REAL NOT NULL,
                    instrument_type TEXT,
                    source TEXT NOT NULL,
                    import_key TEXT NOT NULL,
                    imported_at TEXT NOT NULL,
                    PRIMARY KEY (scheme_code, as_of, isin)
                );
                """
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO portfolio_meta (key, value)
                VALUES ('store_version', ?)
                """,
                (str(PORTFOLIO_STORE_VERSION),),
            )
            connection.execute(
                """
                UPDATE portfolio_meta SET value = ?
                WHERE key = 'store_version' AND CAST(value AS INTEGER) < ?
                """,
                (str(PORTFOLIO_STORE_VERSION), PORTFOLIO_STORE_VERSION),
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS mf_transactions (
                    txn_key TEXT PRIMARY KEY,
                    scheme_code TEXT,
                    scheme_name TEXT NOT NULL,
                    txn_date TEXT NOT NULL,
                    txn_type TEXT NOT NULL,
                    amount REAL NOT NULL,
                    units REAL,
                    nav REAL,
                    source TEXT NOT NULL,
                    import_key TEXT NOT NULL,
                    imported_at TEXT NOT NULL
                )
                """
            )


def _optional_str(value: object) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    return text or None


def _optional_float(value: object) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return float(value)
