"""Point-in-time NSE financial-result filing metadata and storage."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable, Iterator, Protocol
from zoneinfo import ZoneInfo

import requests

from .fundamentals import CanonicalFactMapper, MAPPING_VERSION
from .providers import DataProviderError
from .xbrl import DownloadedXbrl, ParsedXbrl, XbrlParser

IST = ZoneInfo("Asia/Kolkata")


class JsonResponse(Protocol):
    def raise_for_status(self) -> None: ...

    def json(self) -> Any: ...


class JsonSession(Protocol):
    def get(
        self, url: str, *, params: dict[str, str], timeout: float
    ) -> JsonResponse: ...


@dataclass(frozen=True)
class FinancialResultFiling:
    filing_key: str
    source_sequence: str
    symbol: str
    company_name: str | None
    isin: str | None
    period_type: str
    relating_to: str | None
    financial_year: str | None
    period_start: str | None
    period_end: str | None
    filing_at: str | None
    broadcast_at: str | None
    disseminated_at: str | None
    consolidated: str | None
    audited: str | None
    cumulative: str | None
    accounting_standard: str | None
    entity_type: str
    is_revision: int
    xbrl_url: str | None
    detailed_data_url: str | None

    @classmethod
    def from_nse(cls, record: dict[str, Any]) -> "FinancialResultFiling":
        symbol = _required_text(record, "symbol").upper()
        filing_at = _optional_datetime(record.get("filingDate"))
        period_type = _required_text(record, "period")
        source_sequence = str(record.get("seqNumber") or "").strip()
        identity = "|".join(
            [
                source_sequence,
                symbol,
                str(record.get("toDate") or ""),
                str(record.get("consolidated") or ""),
                filing_at or "",
            ]
        )
        return cls(
            filing_key=sha256(identity.encode("utf-8")).hexdigest(),
            source_sequence=source_sequence,
            symbol=symbol,
            company_name=_optional_text(record.get("companyName")),
            isin=_optional_text(record.get("isin")),
            period_type=period_type,
            relating_to=_optional_text(record.get("relatingTo")),
            financial_year=_optional_text(record.get("financialYear")),
            period_start=_parse_nse_date(record.get("fromDate")),
            period_end=_parse_nse_date(record.get("toDate")),
            filing_at=filing_at,
            broadcast_at=_optional_datetime(record.get("broadCastDate")),
            disseminated_at=_optional_datetime(record.get("exchdisstime")),
            consolidated=_optional_text(record.get("consolidated")),
            audited=_optional_text(record.get("audited")),
            cumulative=_optional_text(record.get("cumulative")),
            accounting_standard=_optional_text(record.get("indAs")),
            entity_type=_entity_type(record.get("bank")),
            is_revision=int(
                str(record.get("reInd", "N")).upper() == "Y"
                or str(record.get("oldNewFlag", "N")).upper() == "O"
            ),
            xbrl_url=_optional_text(record.get("xbrl")),
            detailed_data_url=_optional_text(record.get("resultDetailedDataLink")),
        )


class NseFinancialResultsClient:
    """Fetch financial-result metadata from NSE's public website endpoint."""

    ENDPOINT = "https://www.nseindia.com/api/corporates-financial-results"

    def __init__(
        self,
        *,
        session: JsonSession | None = None,
        timeout: float = 30.0,
        attempts: int = 2,
    ) -> None:
        if attempts < 1:
            raise ValueError("attempts must be at least 1")
        if session is None:
            real_session = requests.Session()
            real_session.headers.update(
                {
                    "Accept": "application/json,text/plain,*/*",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-financial-results",
                    "User-Agent": "Mozilla/5.0 (compatible; AIInvestmentResearch/0.1)",
                }
            )
            session = real_session
        self.session = session
        self.timeout = timeout
        self.attempts = attempts

    def fetch(self, symbol: str, period: str = "Quarterly") -> list[dict[str, Any]]:
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise ValueError("symbol cannot be blank")
        normalized_period = period.strip().title()
        if normalized_period not in {"Quarterly", "Annual"}:
            raise ValueError("period must be Quarterly or Annual")

        last_error: Exception | None = None
        for _attempt in range(self.attempts):
            try:
                response = self.session.get(
                    self.ENDPOINT,
                    params={
                        "index": "equities",
                        "symbol": normalized_symbol,
                        "period": normalized_period,
                    },
                    timeout=self.timeout,
                )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, list):
                    raise ValueError(
                        "NSE returned a non-list financial-results payload"
                    )
                if not all(isinstance(item, dict) for item in payload):
                    raise ValueError("NSE returned invalid financial-result records")
                return payload
            except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
                last_error = exc
        raise DataProviderError(
            f"Could not load {normalized_period} filings for {normalized_symbol}: {last_error}"
        ) from last_error


class FilingStore:
    """Persist immutable raw responses and normalized filing metadata in SQLite."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def ingest(
        self,
        records: Iterable[dict[str, Any]],
        *,
        request_symbol: str,
        request_period: str,
        fetched_at: datetime | None = None,
    ) -> int:
        materialized = list(records)
        fetched = (fetched_at or datetime.now(tz=IST)).astimezone(IST).isoformat()
        raw_json = json.dumps(materialized, sort_keys=True, separators=(",", ":"))
        snapshot_hash = sha256(raw_json.encode("utf-8")).hexdigest()
        filings = [FinancialResultFiling.from_nse(record) for record in materialized]

        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO raw_filing_snapshots
                    (snapshot_hash, request_symbol, request_period, fetched_at, payload_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    snapshot_hash,
                    request_symbol.strip().upper(),
                    request_period.strip().title(),
                    fetched,
                    raw_json,
                ),
            )
            before = connection.total_changes
            connection.executemany(
                """
                INSERT OR IGNORE INTO financial_result_filings (
                    filing_key, source_sequence, symbol, company_name, isin,
                    period_type, relating_to, financial_year, period_start, period_end,
                    filing_at, broadcast_at, disseminated_at, consolidated, audited,
                    cumulative, accounting_standard, entity_type, is_revision,
                    xbrl_url, detailed_data_url
                ) VALUES (
                    :filing_key, :source_sequence, :symbol, :company_name, :isin,
                    :period_type, :relating_to, :financial_year, :period_start, :period_end,
                    :filing_at, :broadcast_at, :disseminated_at, :consolidated, :audited,
                    :cumulative, :accounting_standard, :entity_type, :is_revision,
                    :xbrl_url, :detailed_data_url
                )
                """,
                [asdict(filing) for filing in filings],
            )
            inserted = connection.total_changes - before
        return inserted

    def list_as_of(
        self, as_of: datetime, *, symbol: str | None = None
    ) -> list[sqlite3.Row]:
        cutoff = as_of.astimezone(IST).isoformat()
        query = (
            "SELECT * FROM financial_result_filings "
            "WHERE filing_at IS NOT NULL AND filing_at <= ?"
        )
        parameters: list[str] = [cutoff]
        if symbol:
            query += " AND symbol = ?"
            parameters.append(symbol.strip().upper())
        query += " ORDER BY filing_at, symbol, consolidated"
        with self._connect() as connection:
            return list(connection.execute(query, parameters).fetchall())

    def counts(self) -> dict[str, int]:
        with self._connect() as connection:
            raw = connection.execute(
                "SELECT COUNT(*) FROM raw_filing_snapshots"
            ).fetchone()[0]
            normalized = connection.execute(
                "SELECT COUNT(*) FROM financial_result_filings"
            ).fetchone()[0]
        return {"raw_snapshots": raw, "normalized_filings": normalized}

    def pending_xbrl(
        self,
        *,
        symbol: str | None = None,
        period: str | None = None,
        as_of: datetime | None = None,
    ) -> list[sqlite3.Row]:
        """Return timestamped filings with an XBRL link not yet archived."""

        query = """
            SELECT f.*
            FROM financial_result_filings AS f
            LEFT JOIN filing_xbrl_documents AS linked
                ON linked.filing_key = f.filing_key
            WHERE f.xbrl_url IS NOT NULL
              AND f.filing_at IS NOT NULL
              AND linked.filing_key IS NULL
        """
        parameters: list[str] = []
        if symbol:
            query += " AND f.symbol = ?"
            parameters.append(symbol.strip().upper())
        if period:
            normalized_period = period.strip().title()
            if normalized_period not in {"Quarterly", "Annual"}:
                raise ValueError("period must be Quarterly or Annual")
            query += " AND f.period_type = ?"
            parameters.append(normalized_period)
        if as_of is not None:
            query += " AND f.filing_at <= ?"
            parameters.append(as_of.astimezone(IST).isoformat())
        query += " ORDER BY f.filing_at, f.filing_key"
        with self._connect() as connection:
            return list(connection.execute(query, parameters).fetchall())

    def ingest_xbrl(
        self,
        filing_key: str,
        download: DownloadedXbrl,
        *,
        parser: XbrlParser | None = None,
        fetched_at: datetime | None = None,
    ) -> int:
        """Archive one linked document and persist its context-rich facts atomically."""

        parsed = (parser or XbrlParser()).parse(download.content)
        document_hash = sha256(download.content).hexdigest()
        fetched = (fetched_at or datetime.now(tz=IST)).astimezone(IST).isoformat()
        with self._connect() as connection:
            filing = connection.execute(
                "SELECT xbrl_url FROM financial_result_filings WHERE filing_key = ?",
                (filing_key,),
            ).fetchone()
            if filing is None:
                raise ValueError(f"Unknown filing key: {filing_key}")
            if filing["xbrl_url"] != download.source_url:
                raise ValueError(
                    "Downloaded XBRL URL does not match the stored filing link"
                )

            existing = connection.execute(
                "SELECT document_hash FROM filing_xbrl_documents WHERE filing_key = ?",
                (filing_key,),
            ).fetchone()
            if existing is not None:
                if existing["document_hash"] != document_hash:
                    raise ValueError(
                        "Filing is already linked to different XBRL content"
                    )
                self._normalize_filing(connection, filing_key)
                return 0

            self._insert_document(
                connection, document_hash, download, parsed, fetched_at=fetched
            )
            connection.execute(
                """
                INSERT INTO filing_xbrl_documents (filing_key, document_hash)
                VALUES (?, ?)
                """,
                (filing_key, document_hash),
            )
            self._normalize_filing(connection, filing_key)
        return len(parsed.facts)

    def xbrl_counts(self) -> dict[str, int]:
        with self._connect() as connection:
            documents = connection.execute(
                "SELECT COUNT(*) FROM xbrl_documents"
            ).fetchone()[0]
            linked = connection.execute(
                "SELECT COUNT(*) FROM filing_xbrl_documents"
            ).fetchone()[0]
            facts = connection.execute("SELECT COUNT(*) FROM xbrl_facts").fetchone()[0]
        return {"documents": documents, "linked_filings": linked, "facts": facts}

    def list_xbrl_facts(
        self, filing_key: str, *, concept: str | None = None
    ) -> list[sqlite3.Row]:
        query = """
            SELECT facts.*
            FROM xbrl_facts AS facts
            JOIN filing_xbrl_documents AS linked
                ON linked.document_hash = facts.document_hash
            WHERE linked.filing_key = ?
        """
        parameters = [filing_key]
        if concept:
            query += " AND facts.concept = ?"
            parameters.append(concept)
        query += " ORDER BY facts.fact_order"
        with self._connect() as connection:
            return list(connection.execute(query, parameters).fetchall())

    def normalize_xbrl(
        self,
        *,
        filing_key: str | None = None,
        symbol: str | None = None,
        period: str | None = None,
    ) -> int:
        """Refresh canonical mappings for archived XBRL documents."""

        query = """
            SELECT f.filing_key
            FROM financial_result_filings AS f
            JOIN filing_xbrl_documents AS linked
                ON linked.filing_key = f.filing_key
            WHERE 1 = 1
        """
        parameters: list[str] = []
        if filing_key:
            query += " AND f.filing_key = ?"
            parameters.append(filing_key)
        if symbol:
            query += " AND f.symbol = ?"
            parameters.append(symbol.strip().upper())
        if period:
            normalized_period = period.strip().title()
            if normalized_period not in {"Quarterly", "Annual"}:
                raise ValueError("period must be Quarterly or Annual")
            query += " AND f.period_type = ?"
            parameters.append(normalized_period)
        query += " ORDER BY f.filing_at, f.filing_key"

        inserted = 0
        with self._connect() as connection:
            keys = [row["filing_key"] for row in connection.execute(query, parameters)]
            for key in keys:
                connection.execute(
                    "DELETE FROM canonical_financial_facts WHERE filing_key = ?", (key,)
                )
                inserted += self._normalize_filing(connection, key)
        return inserted

    def canonical_counts(self) -> dict[str, int]:
        with self._connect() as connection:
            facts = connection.execute(
                "SELECT COUNT(*) FROM canonical_financial_facts"
            ).fetchone()[0]
            primary = connection.execute(
                "SELECT COUNT(*) FROM canonical_financial_facts WHERE is_primary = 1"
            ).fetchone()[0]
        return {"canonical_facts": facts, "primary_facts": primary}

    def list_canonical_facts(
        self,
        filing_key: str,
        *,
        metric: str | None = None,
        primary_only: bool = True,
    ) -> list[sqlite3.Row]:
        query = """
            SELECT canonical.*, filing.symbol, filing.entity_type,
                   filing.consolidated, filing.audited, filing.filing_at,
                   facts.namespace AS source_namespace,
                   facts.concept AS source_concept,
                   facts.context_id, facts.period_start, facts.period_end,
                   facts.instant, facts.dimensions_json, facts.unit,
                   facts.decimals, facts.precision, facts.value_numeric
            FROM canonical_financial_facts AS canonical
            JOIN financial_result_filings AS filing
                ON filing.filing_key = canonical.filing_key
            JOIN xbrl_facts AS facts
                ON facts.document_hash = canonical.document_hash
               AND facts.fact_order = canonical.source_fact_order
            WHERE canonical.filing_key = ?
        """
        parameters = [filing_key]
        if metric:
            query += " AND canonical.metric = ?"
            parameters.append(metric)
        if primary_only:
            query += " AND canonical.is_primary = 1"
        query += " ORDER BY facts.period_end, facts.instant, canonical.metric, canonical.mapping_priority"
        with self._connect() as connection:
            return list(connection.execute(query, parameters).fetchall())

    def canonical_observations_as_of(
        self, symbol: str, as_of: datetime
    ) -> list[dict[str, Any]]:
        """Return primary canonical observations public by the cutoff."""

        if as_of.tzinfo is None:
            raise ValueError("as_of must include a timezone")
        cutoff = as_of.astimezone(IST).isoformat()
        query = """
            SELECT canonical.*, filing.symbol, filing.entity_type,
                   filing.consolidated, filing.audited, filing.is_revision,
                   filing.filing_at, facts.period_start, facts.period_end,
                   facts.instant, facts.unit, facts.value_numeric
            FROM canonical_financial_facts AS canonical
            JOIN financial_result_filings AS filing
                ON filing.filing_key = canonical.filing_key
            JOIN xbrl_facts AS facts
                ON facts.document_hash = canonical.document_hash
               AND facts.fact_order = canonical.source_fact_order
            WHERE filing.symbol = ?
              AND filing.filing_at IS NOT NULL
              AND filing.filing_at <= ?
              AND canonical.is_primary = 1
              AND facts.value_numeric IS NOT NULL
            ORDER BY filing.filing_at, canonical.metric, facts.fact_order
        """
        with self._connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    query, (symbol.strip().upper(), cutoff)
                ).fetchall()
            ]

    @staticmethod
    def _normalize_filing(connection: sqlite3.Connection, filing_key: str) -> int:
        filing = connection.execute(
            "SELECT entity_type FROM financial_result_filings WHERE filing_key = ?",
            (filing_key,),
        ).fetchone()
        if filing is None:
            raise ValueError(f"Unknown filing key: {filing_key}")
        linked = connection.execute(
            "SELECT document_hash FROM filing_xbrl_documents WHERE filing_key = ?",
            (filing_key,),
        ).fetchone()
        if linked is None:
            raise ValueError(f"Filing has no archived XBRL document: {filing_key}")
        mapper = CanonicalFactMapper()
        if filing["entity_type"] not in mapper.SUPPORTED_ENTITY_TYPES:
            return 0
        source_facts = list(
            connection.execute(
                "SELECT * FROM xbrl_facts WHERE document_hash = ? ORDER BY fact_order",
                (linked["document_hash"],),
            )
        )
        mapped = mapper.map(source_facts, entity_type=filing["entity_type"])
        before = connection.total_changes
        connection.executemany(
            """
            INSERT OR IGNORE INTO canonical_financial_facts (
                filing_key, document_hash, source_fact_order, metric, statement,
                period_kind, is_primary, mapping_priority, mapping_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    filing_key,
                    linked["document_hash"],
                    fact.source_fact_order,
                    fact.metric,
                    fact.statement,
                    fact.period_kind,
                    fact.is_primary,
                    fact.mapping_priority,
                    MAPPING_VERSION,
                )
                for fact in mapped
            ],
        )
        return connection.total_changes - before

    @staticmethod
    def _insert_document(
        connection: sqlite3.Connection,
        document_hash: str,
        download: DownloadedXbrl,
        parsed: ParsedXbrl,
        *,
        fetched_at: str,
    ) -> None:
        exists = connection.execute(
            "SELECT 1 FROM xbrl_documents WHERE document_hash = ?", (document_hash,)
        ).fetchone()
        if exists is not None:
            return
        connection.execute(
            """
            INSERT INTO xbrl_documents (
                document_hash, source_url, final_url, fetched_at, content_type,
                byte_length, schema_refs_json, content
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document_hash,
                download.source_url,
                download.final_url,
                fetched_at,
                download.content_type,
                len(download.content),
                json.dumps(parsed.schema_refs, separators=(",", ":")),
                download.content,
            ),
        )
        connection.executemany(
            """
            INSERT INTO xbrl_facts (
                document_hash, fact_order, namespace, concept, context_id,
                entity_identifier, entity_scheme, period_start, period_end,
                instant, dimensions_json, unit, decimals, precision,
                context_inferred, value_text, value_numeric
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    document_hash,
                    fact.fact_order,
                    fact.namespace,
                    fact.concept,
                    fact.context_id,
                    fact.entity_identifier,
                    fact.entity_scheme,
                    fact.period_start,
                    fact.period_end,
                    fact.instant,
                    fact.dimensions_json,
                    fact.unit,
                    fact.decimals,
                    fact.precision,
                    fact.context_inferred,
                    fact.value_text,
                    fact.value_numeric,
                )
                for fact in parsed.facts
            ],
        )

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
                CREATE TABLE IF NOT EXISTS raw_filing_snapshots (
                    snapshot_hash TEXT PRIMARY KEY,
                    request_symbol TEXT NOT NULL,
                    request_period TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS financial_result_filings (
                    filing_key TEXT PRIMARY KEY,
                    source_sequence TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    company_name TEXT,
                    isin TEXT,
                    period_type TEXT NOT NULL,
                    relating_to TEXT,
                    financial_year TEXT,
                    period_start TEXT,
                    period_end TEXT,
                    filing_at TEXT,
                    broadcast_at TEXT,
                    disseminated_at TEXT,
                    consolidated TEXT,
                    audited TEXT,
                    cumulative TEXT,
                    accounting_standard TEXT,
                    entity_type TEXT NOT NULL,
                    is_revision INTEGER NOT NULL CHECK (is_revision IN (0, 1)),
                    xbrl_url TEXT,
                    detailed_data_url TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_filings_point_in_time
                ON financial_result_filings(symbol, filing_at, period_end);

                CREATE TABLE IF NOT EXISTS xbrl_documents (
                    document_hash TEXT PRIMARY KEY,
                    source_url TEXT NOT NULL,
                    final_url TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    content_type TEXT,
                    byte_length INTEGER NOT NULL CHECK (byte_length > 0),
                    schema_refs_json TEXT NOT NULL,
                    content BLOB NOT NULL
                );

                CREATE TABLE IF NOT EXISTS filing_xbrl_documents (
                    filing_key TEXT PRIMARY KEY,
                    document_hash TEXT NOT NULL,
                    FOREIGN KEY (filing_key)
                        REFERENCES financial_result_filings(filing_key),
                    FOREIGN KEY (document_hash)
                        REFERENCES xbrl_documents(document_hash)
                );

                CREATE TABLE IF NOT EXISTS xbrl_facts (
                    document_hash TEXT NOT NULL,
                    fact_order INTEGER NOT NULL,
                    namespace TEXT NOT NULL,
                    concept TEXT NOT NULL,
                    context_id TEXT NOT NULL,
                    entity_identifier TEXT,
                    entity_scheme TEXT,
                    period_start TEXT,
                    period_end TEXT,
                    instant TEXT,
                    dimensions_json TEXT NOT NULL,
                    unit TEXT,
                    decimals TEXT,
                    precision TEXT,
                    context_inferred INTEGER NOT NULL DEFAULT 0 CHECK (
                        context_inferred IN (0, 1)
                    ),
                    value_text TEXT,
                    value_numeric TEXT,
                    PRIMARY KEY (document_hash, fact_order),
                    FOREIGN KEY (document_hash)
                        REFERENCES xbrl_documents(document_hash)
                );

                CREATE INDEX IF NOT EXISTS idx_xbrl_facts_concept_period
                ON xbrl_facts(concept, period_end, instant);

                CREATE TABLE IF NOT EXISTS canonical_financial_facts (
                    filing_key TEXT NOT NULL,
                    document_hash TEXT NOT NULL,
                    source_fact_order INTEGER NOT NULL,
                    metric TEXT NOT NULL,
                    statement TEXT NOT NULL CHECK (
                        statement IN ('income', 'balance_sheet', 'cash_flow', 'prudential')
                    ),
                    period_kind TEXT NOT NULL CHECK (
                        period_kind IN ('duration', 'instant')
                    ),
                    is_primary INTEGER NOT NULL CHECK (is_primary IN (0, 1)),
                    mapping_priority INTEGER NOT NULL,
                    mapping_version INTEGER NOT NULL,
                    PRIMARY KEY (filing_key, source_fact_order, metric),
                    FOREIGN KEY (filing_key)
                        REFERENCES financial_result_filings(filing_key),
                    FOREIGN KEY (document_hash, source_fact_order)
                        REFERENCES xbrl_facts(document_hash, fact_order)
                );

                CREATE INDEX IF NOT EXISTS idx_canonical_facts_metric_period
                ON canonical_financial_facts(metric, period_kind, is_primary);
                """)
            xbrl_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(xbrl_facts)")
            }
            if "precision" not in xbrl_columns:
                connection.execute("ALTER TABLE xbrl_facts ADD COLUMN precision TEXT")
            if "context_inferred" not in xbrl_columns:
                connection.execute("""
                    ALTER TABLE xbrl_facts
                    ADD COLUMN context_inferred INTEGER NOT NULL DEFAULT 0
                    CHECK (context_inferred IN (0, 1))
                    """)


def _required_text(record: dict[str, Any], key: str) -> str:
    value = _optional_text(record.get(key))
    if value is None:
        raise ValueError(f"NSE financial-result record is missing {key}")
    return value


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.upper() in {"-", "--", "NA", "N/A", "NONE", "NULL"}:
        return None
    return text


def _entity_type(value: Any) -> str:
    code = str(value or "").strip().upper()
    return {"B": "bank", "F": "nbfc", "I": "insurance"}.get(code, "non_bank")


def _parse_nse_datetime(value: str) -> datetime:
    for pattern in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M"):
        try:
            return datetime.strptime(value, pattern).replace(tzinfo=IST)
        except ValueError:
            continue
    raise ValueError(f"Unsupported NSE datetime: {value}")


def _optional_datetime(value: Any) -> str | None:
    text = _optional_text(value)
    return _parse_nse_datetime(text).isoformat() if text else None


def _parse_nse_date(value: Any) -> str | None:
    text = _optional_text(value)
    if text is None:
        return None
    try:
        return datetime.strptime(text, "%d-%b-%Y").date().isoformat()
    except ValueError as exc:
        raise ValueError(f"Unsupported NSE date: {text}") from exc
