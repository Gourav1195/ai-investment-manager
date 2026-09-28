from __future__ import annotations

from datetime import datetime
from io import BytesIO
from zipfile import ZipFile

import pytest
import requests

from src.investing.filings import FilingStore, IST
from src.investing.providers import DataProviderError
from src.investing.xbrl import DownloadedXbrl, NseXbrlClient, XbrlParser

XBRL = b"""<?xml version="1.0" encoding="UTF-8"?>
<xbrli:xbrl
    xmlns:xbrli="http://www.xbrl.org/2003/instance"
    xmlns:xbrldi="http://xbrl.org/2006/xbrldi"
    xmlns:link="http://www.xbrl.org/2003/linkbase"
    xmlns:xlink="http://www.w3.org/1999/xlink"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:iso4217="http://www.xbrl.org/2003/iso4217"
    xmlns:fin="https://example.test/taxonomy">
  <link:schemaRef xlink:type="simple" xlink:href="Ind-AS.xsd"/>
  <xbrli:context id="duration">
    <xbrli:entity>
      <xbrli:identifier scheme="https://www.nseindia.com/NSESymbol">TEST</xbrli:identifier>
    </xbrli:entity>
    <xbrli:period>
      <xbrli:startDate>2024-04-01</xbrli:startDate>
      <xbrli:endDate>2025-03-31</xbrli:endDate>
    </xbrli:period>
    <xbrli:scenario>
      <xbrldi:explicitMember dimension="fin:StatementAxis">fin:ConsolidatedMember</xbrldi:explicitMember>
    </xbrli:scenario>
  </xbrli:context>
  <xbrli:context id="instant">
    <xbrli:entity>
      <xbrli:identifier scheme="https://www.nseindia.com/NSESymbol">TEST</xbrli:identifier>
    </xbrli:entity>
    <xbrli:period><xbrli:instant>2025-03-31</xbrli:instant></xbrli:period>
  </xbrli:context>
  <xbrli:unit id="INR"><xbrli:measure>iso4217:INR</xbrli:measure></xbrli:unit>
  <fin:RevenueFromOperations contextRef="duration" unitRef="INR" decimals="-7">1230000000.00</fin:RevenueFromOperations>
  <fin:Equity contextRef="instant" unitRef="INR" decimals="-7">456000000.00</fin:Equity>
  <fin:OptionalFact contextRef="instant" unitRef="INR" xsi:nil="true"/>
  <fin:AuditStatus contextRef="duration">Audited</fin:AuditStatus>
</xbrli:xbrl>
"""


def filing_record(**overrides):
    record = {
        "audited": "Audited",
        "bank": "N",
        "broadCastDate": "16-Jan-2025 19:42:10",
        "companyName": "Test Limited",
        "consolidated": "Consolidated",
        "cumulative": "Non-cumulative",
        "exchdisstime": "16-Jan-2025 19:42:44",
        "filingDate": "16-Jan-2025 19:42",
        "financialYear": "01-Apr-2024 To 31-Mar-2025",
        "fromDate": "01-Oct-2024",
        "indAs": "Ind-AS New",
        "isin": "INE000A01000",
        "oldNewFlag": "N",
        "period": "Quarterly",
        "reInd": "N",
        "relatingTo": "Third Quarter",
        "resultDetailedDataLink": None,
        "seqNumber": "1",
        "symbol": "TEST",
        "toDate": "31-Dec-2024",
        "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/example.xml",
    }
    record.update(overrides)
    return record


class FakeBinaryResponse:
    def __init__(self, content: bytes, *, url: str) -> None:
        self.content = content
        self.url = url
        self.headers = {"Content-Type": "application/xml; charset=UTF-8"}

    def raise_for_status(self) -> None:
        return None

    def iter_content(self, chunk_size: int):
        for offset in range(0, len(self.content), chunk_size):
            yield self.content[offset : offset + chunk_size]

    def close(self) -> None:
        return None


class FlakyBinarySession:
    def __init__(self, content: bytes, *, final_url: str | None = None) -> None:
        self.content = content
        self.final_url = final_url
        self.calls = 0

    def get(self, url, *, timeout, stream, allow_redirects):
        assert timeout == 30.0
        assert stream is True
        assert allow_redirects is True
        self.calls += 1
        if self.calls == 1:
            raise requests.Timeout("temporary")
        return FakeBinaryResponse(self.content, url=self.final_url or url)


def test_parser_preserves_context_dimensions_units_and_numeric_values() -> None:
    parsed = XbrlParser().parse(XBRL)

    assert parsed.schema_refs == ("Ind-AS.xsd",)
    assert len(parsed.facts) == 4
    revenue = parsed.facts[0]
    assert revenue.concept == "RevenueFromOperations"
    assert revenue.period_start == "2024-04-01"
    assert revenue.period_end == "2025-03-31"
    assert revenue.instant is None
    assert revenue.dimensions_json == (
        '{"{https://example.test/taxonomy}StatementAxis":'
        '"{https://example.test/taxonomy}ConsolidatedMember"}'
    )
    assert revenue.unit == "{http://www.xbrl.org/2003/iso4217}INR"
    assert revenue.value_numeric == "1230000000.00"
    assert parsed.facts[1].instant == "2025-03-31"
    assert parsed.facts[2].value_text is None
    assert parsed.facts[3].value_numeric is None


def test_parser_finds_instance_inside_zip() -> None:
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("taxonomy.xsd", b"<schema/>")
        archive.writestr("reports/instance.xml", XBRL)

    parsed = XbrlParser().parse(output.getvalue())

    assert parsed.facts[0].concept == "RevenueFromOperations"


def test_client_retries_and_rejects_redirects_outside_nse() -> None:
    url = "https://nsearchives.nseindia.com/corporate/xbrl/example.xml"
    session = FlakyBinarySession(XBRL)

    download = NseXbrlClient(session=session).fetch(url)

    assert download.content == XBRL
    assert download.content_type == "application/xml"
    assert session.calls == 2

    redirected = FlakyBinarySession(XBRL, final_url="https://example.test/file.xml")
    with pytest.raises(DataProviderError, match="approved NSE host"):
        NseXbrlClient(session=redirected).fetch(url)


def test_store_archives_document_and_facts_idempotently(tmp_path) -> None:
    store = FilingStore(tmp_path / "research.db")
    record = filing_record(
        symbol="TEST",
        xbrl="https://nsearchives.nseindia.com/corporate/xbrl/example.xml",
    )
    store.ingest(
        [record],
        request_symbol="TEST",
        request_period="Quarterly",
        fetched_at=datetime(2025, 1, 17, tzinfo=IST),
    )
    pending = store.pending_xbrl(symbol="test", period="quarterly")
    download = DownloadedXbrl(
        source_url=pending[0]["xbrl_url"],
        final_url=pending[0]["xbrl_url"],
        content_type="application/xml",
        content=XBRL,
    )

    inserted = store.ingest_xbrl(pending[0]["filing_key"], download)
    repeated = store.ingest_xbrl(pending[0]["filing_key"], download)

    assert inserted == 4
    assert repeated == 0
    assert store.pending_xbrl(symbol="TEST") == []
    assert store.xbrl_counts() == {
        "documents": 1,
        "linked_filings": 1,
        "facts": 4,
    }
    revenue = store.list_xbrl_facts(
        pending[0]["filing_key"], concept="RevenueFromOperations"
    )
    assert len(revenue) == 1
    assert revenue[0]["value_numeric"] == "1230000000.00"
    assert store.canonical_counts() == {
        "canonical_facts": 2,
        "primary_facts": 1,
    }
    primary = store.list_canonical_facts(pending[0]["filing_key"])
    assert [fact["metric"] for fact in primary] == ["total_equity"]
    all_canonical = store.list_canonical_facts(
        pending[0]["filing_key"], primary_only=False
    )
    assert {fact["metric"] for fact in all_canonical} == {
        "revenue",
        "total_equity",
    }


def test_parser_rejects_external_entity_documents() -> None:
    malicious = b"""<!DOCTYPE xbrl [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
    <xbrl xmlns="http://www.xbrl.org/2003/instance">&xxe;</xbrl>"""

    with pytest.raises(ValueError, match="DOCTYPE"):
        XbrlParser().parse(malicious)


def test_parser_recovers_missing_primary_contexts_in_legacy_nse_files() -> None:
    legacy = b"""<?xml version="1.0"?>
    <xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"
      xmlns:fin="https://example.test/taxonomy"
      xmlns:iso4217="http://www.xbrl.org/2003/iso4217">
      <xbrli:unit id="INR"><xbrli:measure>iso4217:INR</xbrli:measure></xbrli:unit>
      <fin:Symbol contextRef="OneD">TEST</fin:Symbol>
      <fin:DateOfStartOfReportingPeriod contextRef="OneD">2024-04-01</fin:DateOfStartOfReportingPeriod>
      <fin:DateOfEndOfReportingPeriod contextRef="OneD">2025-03-31</fin:DateOfEndOfReportingPeriod>
      <fin:RevenueFromOperations contextRef="OneD" unitRef="INR">100</fin:RevenueFromOperations>
      <fin:Equity contextRef="OneI" unitRef="INR">50</fin:Equity>
    </xbrli:xbrl>"""

    parsed = XbrlParser().parse(legacy)

    revenue = next(
        fact for fact in parsed.facts if fact.concept == "RevenueFromOperations"
    )
    equity = next(fact for fact in parsed.facts if fact.concept == "Equity")
    assert revenue.period_start == "2024-04-01"
    assert revenue.period_end == "2025-03-31"
    assert equity.instant == "2025-03-31"
    assert revenue.context_inferred == 1
    assert equity.context_inferred == 1


def test_parser_repairs_primary_context_dates_from_reported_period_facts() -> None:
    inconsistent = (
        XBRL.replace(b'id="duration"', b'id="FourD"')
        .replace(b'contextRef="duration"', b'contextRef="FourD"')
        .replace(
            b"<xbrli:startDate>2024-04-01</xbrli:startDate>",
            b"<xbrli:startDate>2025-01-01</xbrli:startDate>",
            1,
        )
        .replace(
            b'<fin:AuditStatus contextRef="FourD">Audited</fin:AuditStatus>',
            b'<fin:DateOfStartOfReportingPeriod contextRef="FourD">2024-04-01</fin:DateOfStartOfReportingPeriod>'
            b'<fin:DateOfEndOfReportingPeriod contextRef="FourD">2025-03-31</fin:DateOfEndOfReportingPeriod>',
        )
    )

    parsed = XbrlParser().parse(inconsistent)

    revenue = next(
        fact for fact in parsed.facts if fact.concept == "RevenueFromOperations"
    )
    assert revenue.period_start == "2024-04-01"
    assert revenue.period_end == "2025-03-31"
    assert revenue.context_inferred == 1
