"""Insurance XBRL taxonomy validation separate from canonical scoring mappings.

Insurance filings use NSE integrated-filing taxonomies for life and general
insurance. This module validates source concepts without coercing insurers into
non-financial mappings.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Protocol

INSURANCE_VALIDATION_VERSION = 1

LIFE_INSURANCE_CONCEPTS = frozenset(
    {
        "GrossPremiumIncome",
        "FirstYearPremium",
        "RenewalPremium",
        "SinglePremium",
        "NetPremiumIncome",
        "IncomeFromInvestmentsNet",
        "ProfitLossForPeriod",
        "ProfitOrLossAttributableToOwnersOfParent",
        "BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations",
        "Equity",
        "Assets",
    }
)

GENERAL_INSURANCE_CONCEPTS = frozenset(
    {
        "GrossPremiumsWritten",
        "NetPremiumWritten",
        "PremiumEarnedNet",
        "IncomeFromInvestmentsNet",
        "ProfitLossForPeriod",
        "ProfitOrLossAttributableToOwnersOfParent",
        "BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations",
        "Equity",
        "Assets",
    }
)

CORE_INSURANCE_CONCEPTS = frozenset(
    {
        "ProfitLossForPeriod",
        "ProfitOrLossAttributableToOwnersOfParent",
        "Equity",
        "Assets",
    }
)


class InsuranceFactSource(Protocol):
    def insurance_filings(self, symbol: str) -> list[Mapping[str, Any]]: ...

    def filing_concepts(self, filing_key: str) -> set[str]: ...


@dataclass(frozen=True)
class InsuranceTaxonomyReport:
    symbol: str
    filing_key: str
    insurance_kind: str
    entity_type: str
    consolidated: str | None
    period_end: str | None
    filing_at: str | None
    observed_concepts: tuple[str, ...]
    matched_concepts: tuple[str, ...]
    missing_core_concepts: tuple[str, ...]
    coverage_ratio: float
    is_validated: bool
    validation_version: int = INSURANCE_VALIDATION_VERSION

    def to_record(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "filing_key": self.filing_key,
            "insurance_kind": self.insurance_kind,
            "entity_type": self.entity_type,
            "consolidated": self.consolidated,
            "period_end": self.period_end,
            "filing_at": self.filing_at,
            "observed_concepts": ";".join(self.observed_concepts),
            "matched_concepts": ";".join(self.matched_concepts),
            "missing_core_concepts": ";".join(self.missing_core_concepts),
            "coverage_ratio": self.coverage_ratio,
            "is_validated": int(self.is_validated),
            "validation_version": self.validation_version,
        }


class InsuranceTaxonomyValidator:
    """Validate archived insurance filings against expected NSE taxonomies."""

    def validate_concepts(
        self,
        *,
        symbol: str,
        filing_key: str,
        entity_type: str,
        concepts: Iterable[str],
        consolidated: str | None = None,
        period_end: str | None = None,
        filing_at: str | None = None,
    ) -> InsuranceTaxonomyReport:
        normalized_entity = entity_type.strip().lower()
        if normalized_entity != "insurance":
            raise ValueError(
                f"Insurance validation requires entity_type='insurance', got "
                f"{entity_type!r}"
            )

        observed = tuple(sorted({concept.strip() for concept in concepts if concept}))
        insurance_kind, expected = _expected_concepts(observed)
        matched = tuple(sorted(set(observed) & expected))
        missing_core = tuple(sorted(CORE_INSURANCE_CONCEPTS - set(observed)))
        coverage = len(matched) / len(expected) if expected else 0.0
        is_validated = not missing_core and coverage >= 0.50

        return InsuranceTaxonomyReport(
            symbol=symbol.strip().upper(),
            filing_key=filing_key,
            insurance_kind=insurance_kind,
            entity_type=normalized_entity,
            consolidated=consolidated,
            period_end=period_end,
            filing_at=filing_at,
            observed_concepts=observed,
            matched_concepts=matched,
            missing_core_concepts=missing_core,
            coverage_ratio=coverage,
            is_validated=is_validated,
        )

    def validate_symbol(self, source: InsuranceFactSource, symbol: str) -> list[InsuranceTaxonomyReport]:
        reports: list[InsuranceTaxonomyReport] = []
        for filing in source.insurance_filings(symbol):
            concepts = source.filing_concepts(str(filing["filing_key"]))
            reports.append(
                self.validate_concepts(
                    symbol=symbol,
                    filing_key=str(filing["filing_key"]),
                    entity_type=str(filing["entity_type"]),
                    concepts=concepts,
                    consolidated=(
                        str(filing["consolidated"])
                        if filing.get("consolidated")
                        else None
                    ),
                    period_end=(
                        str(filing["period_end"]) if filing.get("period_end") else None
                    ),
                    filing_at=str(filing["filing_at"]) if filing.get("filing_at") else None,
                )
            )
        if not reports:
            raise ValueError(
                f"No archived insurance filings are available for {symbol.strip().upper()}"
            )
        return reports


def _expected_concepts(observed: Iterable[str]) -> tuple[str, frozenset[str]]:
    observed_set = set(observed)
    life_matches = len(observed_set & LIFE_INSURANCE_CONCEPTS)
    general_matches = len(observed_set & GENERAL_INSURANCE_CONCEPTS)
    if life_matches >= general_matches:
        return "life", LIFE_INSURANCE_CONCEPTS
    return "general", GENERAL_INSURANCE_CONCEPTS
