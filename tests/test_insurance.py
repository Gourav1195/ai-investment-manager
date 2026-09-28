from __future__ import annotations

import pytest

from src.investing.filings import FilingStore
from src.investing.insurance import (
    CORE_INSURANCE_CONCEPTS,
    GENERAL_INSURANCE_CONCEPTS,
    LIFE_INSURANCE_CONCEPTS,
    InsuranceTaxonomyValidator,
)
from tests.test_financial_filings import filing_record


def _seed_insurance_filing(store: FilingStore, *, concepts: set[str]) -> str:
    record = filing_record(
        symbol="HDFCLIFE",
        bank="I",
        toDate="31-Dec-2024",
        filingDate="15-Jan-2025 19:42",
    )
    filing = store.ingest([record], request_symbol="HDFCLIFE", request_period="Quarterly")
    assert filing == 1
    with store._connect() as connection:
        row = connection.execute(
            "SELECT filing_key FROM financial_result_filings WHERE symbol = ?",
            ("HDFCLIFE",),
        ).fetchone()
    assert row is not None
    filing_key = row["filing_key"]
    with store._connect() as connection:
        connection.execute(
            """
            INSERT INTO xbrl_documents (
                document_hash, source_url, final_url, fetched_at, content_type,
                byte_length, schema_refs_json, content
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "doc-hash",
                record["xbrl"],
                record["xbrl"],
                "2025-01-15T19:42:00+05:30",
                "application/xml",
                10,
                "[]",
                b"<xbrl/>",
            ),
        )
        connection.execute(
            """
            INSERT INTO filing_xbrl_documents (filing_key, document_hash)
            VALUES (?, ?)
            """,
            (filing_key, "doc-hash"),
        )
        connection.executemany(
            """
            INSERT INTO xbrl_facts (
                document_hash, fact_order, namespace, concept, context_id,
                entity_identifier, entity_scheme, period_start, period_end, instant,
                dimensions_json, unit, decimals, precision, context_inferred,
                value_text, value_numeric
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "doc-hash",
                    index,
                    "https://example.test/taxonomy",
                    concept,
                    f"context-{index}",
                    "HDFCLIFE",
                    "https://www.nseindia.com/NSESymbol",
                    "2024-10-01",
                    "2024-12-31",
                    None,
                    "{}",
                    "INR",
                    "-7",
                    None,
                    0,
                    "100",
                    "100",
                )
                for index, concept in enumerate(sorted(concepts))
            ],
        )
    return filing_key


def test_life_insurance_taxonomy_validation(tmp_path) -> None:
    store = FilingStore(tmp_path / "research.db")
    concepts = set(LIFE_INSURANCE_CONCEPTS)
    _seed_insurance_filing(store, concepts=concepts)

    reports = InsuranceTaxonomyValidator().validate_symbol(store, "HDFCLIFE")

    assert len(reports) == 1
    report = reports[0]
    assert report.insurance_kind == "life"
    assert report.is_validated
    assert report.missing_core_concepts == ()
    assert report.coverage_ratio == 1.0


def test_general_insurance_taxonomy_reports_missing_core(tmp_path) -> None:
    store = FilingStore(tmp_path / "research.db")
    concepts = set(GENERAL_INSURANCE_CONCEPTS) - {"Equity"}
    _seed_insurance_filing(store, concepts=concepts)

    report = InsuranceTaxonomyValidator().validate_symbol(store, "HDFCLIFE")[0]

    assert report.insurance_kind == "general"
    assert not report.is_validated
    assert report.missing_core_concepts == ("Equity",)


def test_insurance_validation_rejects_non_insurance_entity() -> None:
    with pytest.raises(ValueError, match="entity_type='insurance'"):
        InsuranceTaxonomyValidator().validate_concepts(
            symbol="TEST",
            filing_key="abc",
            entity_type="non_bank",
            concepts=CORE_INSURANCE_CONCEPTS,
        )
