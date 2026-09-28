from __future__ import annotations

import pytest

from src.investing.fundamentals import CanonicalFactMapper
from src.investing.xbrl import XbrlFact


def fact(
    concept: str,
    *,
    order: int = 0,
    duration: bool = True,
    dimensions: str = "{}",
    value: str | None = "100.00",
) -> XbrlFact:
    return XbrlFact(
        fact_order=order,
        namespace="https://example.test/taxonomy",
        concept=concept,
        context_id=f"context-{order}",
        entity_identifier="TEST",
        entity_scheme="https://www.nseindia.com/NSESymbol",
        period_start="2024-04-01" if duration else None,
        period_end="2025-03-31" if duration else None,
        instant=None if duration else "2025-03-31",
        dimensions_json=dimensions,
        unit="{http://www.xbrl.org/2003/iso4217}INR",
        decimals="-7",
        precision=None,
        context_inferred=0,
        value_text=value,
        value_numeric=value,
    )


def test_non_bank_mapping_separates_primary_and_dimensional_facts() -> None:
    mapped = CanonicalFactMapper().map(
        [
            fact("RevenueFromOperations"),
            fact(
                "RevenueFromOperations",
                order=1,
                dimensions='{"segment":"retail"}',
            ),
            fact("Equity", order=2, duration=False),
            fact("UnknownConcept", order=3),
        ],
        entity_type="non_bank",
    )

    assert [(item.metric, item.is_primary) for item in mapped] == [
        ("revenue", 1),
        ("revenue", 0),
        ("total_equity", 1),
    ]


def test_mapping_rejects_a_concept_in_the_wrong_period_kind() -> None:
    mapped = CanonicalFactMapper().map(
        [fact("Equity", duration=True)], entity_type="non_bank"
    )

    assert mapped == []


def test_bank_and_nbfc_taxonomies_use_company_specific_mappings() -> None:
    mapper = CanonicalFactMapper()

    bank = mapper.map(
        [fact("InterestExpended"), fact("GrossNonPerformingAssets", order=1)],
        entity_type="bank",
    )
    nbfc = mapper.map(
        [fact("InterestEarned"), fact("Borrowings", order=1, duration=False)],
        entity_type="nbfc",
    )

    assert [item.metric for item in bank] == [
        "interest_expense",
        "gross_nonperforming_assets",
    ]
    assert [item.metric for item in nbfc] == ["interest_income", "borrowings"]


def test_unsupported_company_type_is_explicit() -> None:
    with pytest.raises(ValueError, match="Unsupported XBRL entity type"):
        CanonicalFactMapper().map([], entity_type="insurance")
