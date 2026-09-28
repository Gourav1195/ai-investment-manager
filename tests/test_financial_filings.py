from __future__ import annotations

from datetime import datetime

import requests

from src.investing.filings import (
    FilingStore,
    FinancialResultFiling,
    IST,
    NseFinancialResultsClient,
)


def filing_record(**overrides):
    record = {
        "audited": "Audited",
        "bank": "N",
        "broadCastDate": "16-Jan-2025 19:42:10",
        "companyName": "Infosys Limited",
        "consolidated": "Consolidated",
        "cumulative": "Non-cumulative",
        "exchdisstime": "16-Jan-2025 19:42:44",
        "filingDate": "16-Jan-2025 19:42",
        "financialYear": "01-Apr-2024 To 31-Mar-2025",
        "fromDate": "01-Oct-2024",
        "indAs": "Ind-AS New",
        "isin": "INE009A01021",
        "oldNewFlag": "N",
        "period": "Quarterly",
        "reInd": "N",
        "relatingTo": "Third Quarter",
        "resultDetailedDataLink": None,
        "seqNumber": "1189815",
        "symbol": "INFY",
        "toDate": "31-Dec-2024",
        "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/example.xml",
    }
    record.update(overrides)
    return record


class FakeResponse:
    def __init__(self, payload) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self.payload


class FlakySession:
    def __init__(self, payload) -> None:
        self.payload = payload
        self.calls = []

    def get(self, url, *, params, timeout):
        self.calls.append((url, params, timeout))
        if len(self.calls) == 1:
            raise requests.Timeout("temporary")
        return FakeResponse(self.payload)


def test_client_normalizes_query_and_retries() -> None:
    session = FlakySession([filing_record()])

    records = NseFinancialResultsClient(session=session).fetch(" infy ", "quarterly")

    assert len(records) == 1
    assert len(session.calls) == 2
    assert session.calls[-1][1] == {
        "index": "equities",
        "symbol": "INFY",
        "period": "Quarterly",
    }


def test_store_is_idempotent_and_supports_point_in_time_queries(tmp_path) -> None:
    store = FilingStore(tmp_path / "research.db")
    records = [
        filing_record(),
        filing_record(
            seqNumber="1189816",
            filingDate="17-Apr-2025 15:00",
            broadCastDate="17-Apr-2025 15:00:05",
            exchdisstime="17-Apr-2025 15:00:20",
            fromDate="01-Jan-2025",
            toDate="31-Mar-2025",
            relatingTo="Fourth Quarter",
            reInd="Y",
        ),
    ]

    first_insert = store.ingest(
        records,
        request_symbol="INFY",
        request_period="Quarterly",
        fetched_at=datetime(2025, 4, 18, tzinfo=IST),
    )
    second_insert = store.ingest(
        records,
        request_symbol="INFY",
        request_period="Quarterly",
        fetched_at=datetime(2025, 4, 19, tzinfo=IST),
    )

    assert first_insert == 2
    assert second_insert == 0
    assert store.counts() == {"raw_snapshots": 1, "normalized_filings": 2}
    visible = store.list_as_of(datetime(2025, 1, 31, tzinfo=IST), symbol="infy")
    assert len(visible) == 1
    assert visible[0]["period_end"] == "2024-12-31"
    assert visible[0]["filing_at"] == "2025-01-16T19:42:00+05:30"
    assert visible[0]["is_revision"] == 0


def test_raw_snapshot_changes_are_retained(tmp_path) -> None:
    store = FilingStore(tmp_path / "research.db")
    store.ingest([filing_record()], request_symbol="INFY", request_period="Quarterly")
    store.ingest(
        [filing_record(resultDescription="Updated by NSE")],
        request_symbol="INFY",
        request_period="Quarterly",
    )

    assert store.counts() == {"raw_snapshots": 2, "normalized_filings": 1}


def test_filing_without_publication_time_is_retained_but_not_visible_as_of(
    tmp_path,
) -> None:
    store = FilingStore(tmp_path / "research.db")
    store.ingest(
        [
            filing_record(
                seqNumber="old-record",
                filingDate="-",
                broadCastDate=None,
                exchdisstime=None,
                toDate="31-Dec-2006",
                xbrl="-",
            )
        ],
        request_symbol="INFY",
        request_period="Quarterly",
    )

    assert store.counts()["normalized_filings"] == 1
    assert store.list_as_of(datetime(2020, 1, 1, tzinfo=IST)) == []


def test_nse_entity_codes_distinguish_banks_and_nbfcs() -> None:
    bank = filing_record(bank="B")
    nbfc = filing_record(bank="F", seqNumber="nbfc")

    assert FinancialResultFiling.from_nse(bank).entity_type == "bank"
    assert FinancialResultFiling.from_nse(nbfc).entity_type == "nbfc"
