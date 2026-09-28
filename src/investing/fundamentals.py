"""Canonical accounting facts derived from NSE XBRL concepts.

This module maps source concepts; it does not calculate ratios. Every mapped
fact retains its source fact order so later calculations remain auditable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import json
from typing import Any, Iterable, Literal, Mapping, Protocol

from .insurance import GENERAL_INSURANCE_CONCEPTS, LIFE_INSURANCE_CONCEPTS

Statement = Literal["income", "balance_sheet", "cash_flow", "prudential"]
PeriodKind = Literal["duration", "instant"]


class FactLike(Protocol):
    fact_order: int
    concept: str
    period_start: str | None
    period_end: str | None
    instant: str | None
    dimensions_json: str
    value_numeric: str | None


@dataclass(frozen=True)
class ConceptMapping:
    metric: str
    statement: Statement
    period_kind: PeriodKind
    priority: int = 100


@dataclass(frozen=True)
class CanonicalFact:
    source_fact_order: int
    metric: str
    statement: Statement
    period_kind: PeriodKind
    is_primary: int
    mapping_priority: int


MAPPING_VERSION = 3
CALCULATION_VERSION = 1


COMMON_MAPPINGS: dict[str, ConceptMapping] = {
    "Income": ConceptMapping("total_income", "income", "duration"),
    "OtherIncome": ConceptMapping("other_income", "income", "duration"),
    "Expenses": ConceptMapping("total_expenses", "income", "duration"),
    "EmployeeBenefitExpense": ConceptMapping("employee_expense", "income", "duration"),
    "FinanceCosts": ConceptMapping("finance_cost", "income", "duration"),
    "DepreciationDepletionAndAmortisationExpense": ConceptMapping(
        "depreciation_amortisation", "income", "duration"
    ),
    "ProfitBeforeTax": ConceptMapping("profit_before_tax", "income", "duration"),
    "TaxExpense": ConceptMapping("tax_expense", "income", "duration"),
    "ProfitLossForPeriod": ConceptMapping("net_income", "income", "duration", 20),
    "ProfitOrLossAttributableToOwnersOfParent": ConceptMapping(
        "net_income_attributable", "income", "duration", 10
    ),
    "BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations": ConceptMapping(
        "basic_eps", "income", "duration"
    ),
    "DilutedEarningsLossPerShareFromContinuingAndDiscontinuedOperations": ConceptMapping(
        "diluted_eps", "income", "duration"
    ),
    "Assets": ConceptMapping("total_assets", "balance_sheet", "instant"),
    "Equity": ConceptMapping("total_equity", "balance_sheet", "instant"),
    "EquityShareCapital": ConceptMapping(
        "equity_share_capital", "balance_sheet", "instant"
    ),
    "ReserveExcludingRevaluationReserves": ConceptMapping(
        "reserves", "balance_sheet", "instant"
    ),
    "CashAndCashEquivalents": ConceptMapping(
        "cash_and_equivalents", "balance_sheet", "instant"
    ),
    "CurrentAssets": ConceptMapping("current_assets", "balance_sheet", "instant"),
    "CurrentLiabilities": ConceptMapping(
        "current_liabilities", "balance_sheet", "instant"
    ),
    "Inventories": ConceptMapping("inventory", "balance_sheet", "instant"),
    "BorrowingsCurrent": ConceptMapping(
        "borrowings_current", "balance_sheet", "instant"
    ),
    "BorrowingsNoncurrent": ConceptMapping(
        "borrowings_noncurrent", "balance_sheet", "instant"
    ),
    "CashFlowsFromUsedInOperatingActivities": ConceptMapping(
        "operating_cash_flow", "cash_flow", "duration"
    ),
    "CashFlowsFromUsedInInvestingActivities": ConceptMapping(
        "investing_cash_flow", "cash_flow", "duration"
    ),
    "CashFlowsFromUsedInFinancingActivities": ConceptMapping(
        "financing_cash_flow", "cash_flow", "duration"
    ),
    "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities": ConceptMapping(
        "capital_expenditure_ppe", "cash_flow", "duration"
    ),
    "PurchaseOfIntangibleAssetsClassifiedAsInvestingActivities": ConceptMapping(
        "capital_expenditure_intangibles", "cash_flow", "duration"
    ),
}


NON_BANK_MAPPINGS: dict[str, ConceptMapping] = {
    "RevenueFromOperations": ConceptMapping("revenue", "income", "duration"),
    "ProfitBeforeExceptionalItemsAndTax": ConceptMapping(
        "profit_before_exceptional_items_and_tax", "income", "duration"
    ),
}


NBFC_MAPPINGS: dict[str, ConceptMapping] = {
    **NON_BANK_MAPPINGS,
    "InterestEarned": ConceptMapping("interest_income", "income", "duration"),
    "FeesAndCommissionIncome": ConceptMapping(
        "fee_commission_income", "income", "duration"
    ),
    "FeesAndCommissionExpense": ConceptMapping(
        "fee_commission_expense", "income", "duration"
    ),
    "ImpairmentOnFinancialInstruments": ConceptMapping(
        "credit_impairment", "income", "duration"
    ),
    "Borrowings": ConceptMapping("borrowings", "balance_sheet", "instant"),
    "DebtSecurities": ConceptMapping("debt_securities", "balance_sheet", "instant"),
    "Deposits": ConceptMapping("deposits", "balance_sheet", "instant"),
    "SubordinatedLiabilities": ConceptMapping(
        "subordinated_liabilities", "balance_sheet", "instant"
    ),
    "Loans": ConceptMapping("loans", "balance_sheet", "instant"),
}


INSURANCE_COMMON_MAPPINGS: dict[str, ConceptMapping] = {
    "ProfitLossForPeriod": ConceptMapping("net_income", "income", "duration", 20),
    "ProfitOrLossAttributableToOwnersOfParent": ConceptMapping(
        "net_income_attributable", "income", "duration", 10
    ),
    "BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations": ConceptMapping(
        "basic_eps", "income", "duration"
    ),
    "IncomeFromInvestmentsNet": ConceptMapping(
        "investment_income", "income", "duration"
    ),
    "Assets": ConceptMapping("total_assets", "balance_sheet", "instant"),
    "Equity": ConceptMapping("total_equity", "balance_sheet", "instant"),
}

LIFE_INSURANCE_MAPPINGS: dict[str, ConceptMapping] = {
    "GrossPremiumIncome": ConceptMapping("gross_premium_income", "income", "duration"),
    "FirstYearPremium": ConceptMapping("first_year_premium", "income", "duration"),
    "RenewalPremium": ConceptMapping("renewal_premium", "income", "duration"),
    "SinglePremium": ConceptMapping("single_premium", "income", "duration"),
    "NetPremiumIncome": ConceptMapping("net_premium_income", "income", "duration"),
}

GENERAL_INSURANCE_MAPPINGS: dict[str, ConceptMapping] = {
    "GrossPremiumsWritten": ConceptMapping(
        "gross_premiums_written", "income", "duration"
    ),
    "NetPremiumWritten": ConceptMapping("net_premium_written", "income", "duration"),
    "PremiumEarnedNet": ConceptMapping("premium_earned_net", "income", "duration"),
}


BANK_MAPPINGS: dict[str, ConceptMapping] = {
    "Income": ConceptMapping("total_income", "income", "duration"),
    "InterestEarned": ConceptMapping("interest_income", "income", "duration"),
    "InterestExpended": ConceptMapping("interest_expense", "income", "duration"),
    "OtherIncome": ConceptMapping("other_income", "income", "duration"),
    "OperatingExpenses": ConceptMapping("operating_expenses", "income", "duration"),
    "OperatingProfitBeforeProvisionAndContingencies": ConceptMapping(
        "pre_provision_operating_profit", "income", "duration"
    ),
    "ProvisionsOtherThanTaxAndContingencies": ConceptMapping(
        "provisions_contingencies", "income", "duration"
    ),
    "ProfitLossFromOrdinaryActivitiesBeforeTax": ConceptMapping(
        "profit_before_tax", "income", "duration"
    ),
    "TaxExpense": ConceptMapping("tax_expense", "income", "duration"),
    "ProfitLossForThePeriod": ConceptMapping("net_income", "income", "duration", 20),
    "ProfitLossAfterTaxesMinorityInterestAndShareOfProfitLossOfAssociates": ConceptMapping(
        "net_income_attributable", "income", "duration", 10
    ),
    "BasicEarningsPerShareAfterExtraordinaryItems": ConceptMapping(
        "basic_eps", "income", "duration"
    ),
    "DilutedEarningsPerShareAfterExtraordinaryItems": ConceptMapping(
        "diluted_eps", "income", "duration"
    ),
    "CapitalAndLiabilities": ConceptMapping("total_assets", "balance_sheet", "instant"),
    "Capital": ConceptMapping("equity_share_capital", "balance_sheet", "instant"),
    "ReservesAndSurplus": ConceptMapping("reserves", "balance_sheet", "instant"),
    "Deposits": ConceptMapping("deposits", "balance_sheet", "instant"),
    "Borrowings": ConceptMapping("borrowings", "balance_sheet", "instant"),
    "Advances": ConceptMapping("loans_and_advances", "balance_sheet", "instant"),
    "Investments": ConceptMapping("investments", "balance_sheet", "instant"),
    "CashAndBalancesWithReserveBankOfIndia": ConceptMapping(
        "cash_and_central_bank_balances", "balance_sheet", "instant"
    ),
    "CashFlowsFromUsedInOperatingActivities": ConceptMapping(
        "operating_cash_flow", "cash_flow", "duration"
    ),
    "CashFlowsFromUsedInInvestingActivities": ConceptMapping(
        "investing_cash_flow", "cash_flow", "duration"
    ),
    "CashFlowsFromUsedInFinancingActivities": ConceptMapping(
        "financing_cash_flow", "cash_flow", "duration"
    ),
    "PurchaseOfTangibleAssetsClassifiedAsInvestingActivities": ConceptMapping(
        "capital_expenditure_ppe", "cash_flow", "duration"
    ),
    "PurchaseOfIntangibleAssetsClassifiedAsInvestingActivities": ConceptMapping(
        "capital_expenditure_intangibles", "cash_flow", "duration"
    ),
    "GrossNonPerformingAssets": ConceptMapping(
        "gross_nonperforming_assets", "prudential", "duration"
    ),
    "NonPerformingAssets": ConceptMapping(
        "net_nonperforming_assets", "prudential", "duration"
    ),
    "PercentageOfGrossNpa": ConceptMapping("gross_npa_ratio", "prudential", "duration"),
    "CET1Ratio": ConceptMapping("cet1_ratio", "prudential", "duration"),
    "ReturnOnAssets": ConceptMapping(
        "reported_return_on_assets", "prudential", "duration"
    ),
}


class CanonicalFactMapper:
    """Map source concepts to stable metrics for a known company type."""

    SUPPORTED_ENTITY_TYPES = frozenset({"non_bank", "nbfc", "bank", "insurance"})

    def mapping_for(self, entity_type: str) -> Mapping[str, ConceptMapping]:
        normalized = entity_type.strip().lower()
        if normalized == "bank":
            return BANK_MAPPINGS
        if normalized == "nbfc":
            return {**COMMON_MAPPINGS, **NBFC_MAPPINGS}
        if normalized == "non_bank":
            return {**COMMON_MAPPINGS, **NON_BANK_MAPPINGS}
        if normalized == "insurance":
            raise ValueError(
                "Insurance mappings are selected from archived facts; call map() instead"
            )
        raise ValueError(f"Unsupported XBRL entity type: {entity_type}")

    @staticmethod
    def insurance_mappings(
        facts: Iterable[FactLike | Mapping[str, object]],
    ) -> dict[str, ConceptMapping]:
        concepts = {str(_value(fact, "concept")) for fact in facts}
        life_matches = len(concepts & LIFE_INSURANCE_CONCEPTS)
        general_matches = len(concepts & GENERAL_INSURANCE_CONCEPTS)
        if life_matches >= general_matches:
            return {**INSURANCE_COMMON_MAPPINGS, **LIFE_INSURANCE_MAPPINGS}
        return {**INSURANCE_COMMON_MAPPINGS, **GENERAL_INSURANCE_MAPPINGS}

    def map(
        self, facts: Iterable[FactLike | Mapping[str, object]], *, entity_type: str
    ) -> list[CanonicalFact]:
        normalized = entity_type.strip().lower()
        if normalized == "insurance":
            mappings = self.insurance_mappings(facts)
        else:
            mappings = self.mapping_for(entity_type)
        canonical: list[CanonicalFact] = []
        for fact in facts:
            concept = str(_value(fact, "concept"))
            mapping = mappings.get(concept)
            if mapping is None or _value(fact, "value_numeric") is None:
                continue
            actual_period_kind = (
                "instant" if _value(fact, "instant") is not None else "duration"
            )
            if actual_period_kind != mapping.period_kind:
                continue
            dimensions = str(_value(fact, "dimensions_json") or "{}")
            try:
                is_primary = int(not bool(json.loads(dimensions)))
            except (TypeError, json.JSONDecodeError) as exc:
                raise ValueError("XBRL fact contains invalid dimensions JSON") from exc
            canonical.append(
                CanonicalFact(
                    source_fact_order=int(_value(fact, "fact_order")),
                    metric=mapping.metric,
                    statement=mapping.statement,
                    period_kind=mapping.period_kind,
                    is_primary=is_primary,
                    mapping_priority=mapping.priority,
                )
            )
        return canonical


@dataclass(frozen=True)
class FundamentalSnapshot:
    symbol: str
    entity_type: str
    as_of: str
    period_end: str
    roe: float | None = None
    roce: float | None = None
    operating_margin: float | None = None
    revenue_cagr_3y: float | None = None
    earnings_cagr_3y: float | None = None
    debt_to_equity: float | None = None
    interest_coverage: float | None = None
    free_cash_flow: float | None = None
    pre_tax_margin: float | None = None
    return_on_assets: float | None = None
    gross_npa_ratio: float | None = None
    cet1_ratio: float | None = None
    latest_net_income: float | None = None
    basic_eps: float | None = None
    book_equity: float | None = None
    price_date: str | None = None
    price: float | None = None
    shares_outstanding: float | None = None
    pe: float | None = None
    pb: float | None = None
    free_cash_flow_yield: float | None = None
    volatility_1y: float | None = None
    calculation_version: int = CALCULATION_VERSION
    market_join_version: int | None = None
    source_filing_keys: tuple[str, ...] = ()

    def to_record(self) -> dict[str, Any]:
        record = dict(self.__dict__)
        record["source_filing_keys"] = ";".join(self.source_filing_keys)
        return record

    def to_scorer_row(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "roe": self.roe,
            "roce": self.roce,
            "operating_margin": self.operating_margin,
            "revenue_cagr_3y": self.revenue_cagr_3y,
            "earnings_cagr_3y": self.earnings_cagr_3y,
            "debt_to_equity": self.debt_to_equity,
            "interest_coverage": self.interest_coverage,
            "pe": self.pe,
            "pb": self.pb,
            "free_cash_flow_yield": self.free_cash_flow_yield,
            "volatility_1y": self.volatility_1y,
        }


@dataclass(frozen=True)
class _Observation:
    filing_key: str
    symbol: str
    entity_type: str
    consolidated: str | None
    filing_at: datetime
    metric: str
    period_kind: str
    period_start: date | None
    period_end: date | None
    instant: date | None
    mapping_priority: int
    value: Decimal


class FundamentalCalculator:
    """Calculate point-in-time fundamentals from primary canonical facts."""

    def calculate(
        self,
        rows: Iterable[Mapping[str, object]],
        *,
        symbol: str,
        as_of: datetime,
    ) -> FundamentalSnapshot:
        normalized_symbol = symbol.strip().upper()
        observations = [
            observation
            for row in rows
            if (observation := self._observation(row)) is not None
            and observation.symbol == normalized_symbol
            and observation.filing_at <= as_of
        ]
        if not observations:
            raise ValueError(
                f"No canonical financial facts are available for {normalized_symbol} as of "
                f"{as_of.isoformat()}"
            )
        entity_types = {observation.entity_type for observation in observations}
        if len(entity_types) != 1:
            raise ValueError(
                f"Conflicting entity types for {normalized_symbol}: "
                f"{', '.join(sorted(entity_types))}"
            )
        entity_type = entity_types.pop()
        if entity_type not in CanonicalFactMapper.SUPPORTED_ENTITY_TYPES:
            raise ValueError(f"Unsupported fundamental entity type: {entity_type}")

        selected = self._select_best(observations)
        base_metric = "revenue" if entity_type == "non_bank" else "total_income"
        annual_ends = sorted(
            {
                item.period_end
                for item in selected
                if item.metric == base_metric and self._is_full_year(item)
            }
        )
        if not annual_ends:
            raise ValueError(
                f"No full-year {base_metric} fact is available for {normalized_symbol}"
            )
        latest_end = annual_ends[-1]
        prior_end = self._nearest_year_end(annual_ends, latest_end, years=1)
        growth_start = self._nearest_year_end(annual_ends, latest_end, years=3)
        sources: set[str] = set()

        def duration(metric: str, end: date = latest_end) -> Decimal | None:
            item = self._find(
                selected, metric=metric, period_end=end, period_kind="duration"
            )
            if item:
                sources.add(item.filing_key)
                return item.value
            return None

        def instant(metric: str, at: date | None) -> Decimal | None:
            if at is None:
                return None
            item = self._find(
                selected, metric=metric, instant=at, period_kind="instant"
            )
            if item:
                sources.add(item.filing_key)
                return item.value
            return None

        def income(end: date) -> Decimal | None:
            return duration("net_income_attributable", end) or duration(
                "net_income", end
            )

        latest_income = income(latest_end)
        current_equity = self._equity(entity_type, instant, latest_end)
        previous_equity = self._equity(entity_type, instant, prior_end)
        roe = self._ratio(latest_income, self._average(current_equity, previous_equity))

        revenue_latest = duration(base_metric)
        revenue_start = duration(base_metric, growth_start) if growth_start else None
        income_start = income(growth_start) if growth_start else None
        revenue_cagr = self._cagr(revenue_start, revenue_latest, 3)
        earnings_cagr = self._cagr(income_start, latest_income, 3)

        common = dict(
            symbol=normalized_symbol,
            entity_type=entity_type,
            as_of=as_of.isoformat(),
            period_end=latest_end.isoformat(),
            roe=roe,
            revenue_cagr_3y=revenue_cagr,
            earnings_cagr_3y=earnings_cagr,
            latest_net_income=self._float(latest_income),
            basic_eps=self._float(duration("basic_eps")),
            book_equity=self._float(current_equity),
        )
        if entity_type == "non_bank":
            metrics = self._non_bank_metrics(
                duration, instant, latest_end, prior_end, current_equity
            )
        elif entity_type == "nbfc":
            metrics = self._nbfc_metrics(
                duration,
                instant,
                latest_end,
                prior_end,
                current_equity,
                latest_income,
                revenue_latest,
            )
        else:
            metrics = self._bank_metrics(
                selected,
                duration,
                instant,
                latest_end,
                prior_end,
                latest_income,
                revenue_latest,
                sources,
            )
        return FundamentalSnapshot(
            **common,
            **metrics,
            source_filing_keys=tuple(sorted(sources)),
        )

    def _non_bank_metrics(
        self, duration, instant, latest_end, prior_end, current_equity
    ) -> dict[str, float | None]:
        profit_before_tax = duration("profit_before_tax")
        finance_cost = duration("finance_cost")
        other_income = duration("other_income") or Decimal(0)
        revenue = duration("revenue")
        ebit = self._sum_required(profit_before_tax, finance_cost)
        operating_profit = ebit - other_income if ebit is not None else None

        current_debt = self._sum_available(
            instant("borrowings_current", latest_end),
            instant("borrowings_noncurrent", latest_end),
        )
        prior_debt = self._sum_available(
            instant("borrowings_current", prior_end),
            instant("borrowings_noncurrent", prior_end),
        )
        current_capital = self._capital_employed(
            instant, latest_end, current_equity, current_debt
        )
        prior_capital = self._capital_employed(
            instant, prior_end, instant("total_equity", prior_end), prior_debt
        )
        operating_cash_flow = duration("operating_cash_flow")
        capex_values = [
            duration("capital_expenditure_ppe"),
            duration("capital_expenditure_intangibles"),
        ]
        capex_present = [value for value in capex_values if value is not None]
        free_cash_flow = None
        if operating_cash_flow is not None and capex_present:
            free_cash_flow = operating_cash_flow - sum(
                (abs(value) for value in capex_present), Decimal(0)
            )
        return {
            "roce": self._ratio(ebit, self._average(current_capital, prior_capital)),
            "operating_margin": self._ratio(operating_profit, revenue),
            "debt_to_equity": self._ratio(current_debt, current_equity),
            "interest_coverage": self._ratio(ebit, finance_cost),
            "free_cash_flow": self._float(free_cash_flow),
        }

    def _nbfc_metrics(
        self,
        duration,
        instant,
        latest_end,
        prior_end,
        current_equity,
        latest_income,
        total_income,
    ) -> dict[str, float | None]:
        debt = self._sum_available(
            instant("borrowings", latest_end),
            instant("debt_securities", latest_end),
            instant("deposits", latest_end),
            instant("subordinated_liabilities", latest_end),
        )
        average_assets = self._average(
            instant("total_assets", latest_end), instant("total_assets", prior_end)
        )
        return {
            "debt_to_equity": self._ratio(debt, current_equity),
            "pre_tax_margin": self._ratio(duration("profit_before_tax"), total_income),
            "return_on_assets": self._ratio(latest_income, average_assets),
        }

    def _bank_metrics(
        self,
        selected,
        duration,
        instant,
        latest_end,
        prior_end,
        latest_income,
        total_income,
        sources,
    ) -> dict[str, float | None]:
        average_assets = self._average(
            instant("total_assets", latest_end), instant("total_assets", prior_end)
        )

        def latest_reported(metric: str) -> Decimal | None:
            candidates = [
                item
                for item in selected
                if item.metric == metric and item.period_end is not None
            ]
            if not candidates:
                return None
            item = max(candidates, key=lambda candidate: candidate.period_end)
            sources.add(item.filing_key)
            return item.value

        return {
            "operating_margin": self._ratio(
                duration("pre_provision_operating_profit"), total_income
            ),
            "pre_tax_margin": self._ratio(duration("profit_before_tax"), total_income),
            "return_on_assets": self._ratio(latest_income, average_assets),
            "gross_npa_ratio": self._float(latest_reported("gross_npa_ratio")),
            "cet1_ratio": self._float(latest_reported("cet1_ratio")),
        }

    @staticmethod
    def _observation(row: Mapping[str, object]) -> _Observation | None:
        try:
            value = Decimal(str(row["value_numeric"]))
        except (InvalidOperation, KeyError, TypeError):
            return None
        if not value.is_finite() or int(row.get("is_primary", 1)) != 1:
            return None
        return _Observation(
            filing_key=str(row["filing_key"]),
            symbol=str(row["symbol"]).strip().upper(),
            entity_type=str(row["entity_type"]),
            consolidated=(
                str(row["consolidated"]) if row.get("consolidated") else None
            ),
            filing_at=datetime.fromisoformat(str(row["filing_at"])),
            metric=str(row["metric"]),
            period_kind=str(row["period_kind"]),
            period_start=_date(row.get("period_start")),
            period_end=_date(row.get("period_end")),
            instant=_date(row.get("instant")),
            mapping_priority=int(row["mapping_priority"]),
            value=value,
        )

    @staticmethod
    def _select_best(observations: Iterable[_Observation]) -> list[_Observation]:
        selected: dict[tuple[object, ...], _Observation] = {}
        for item in observations:
            key = (
                item.metric,
                item.period_kind,
                item.period_start,
                item.period_end,
                item.instant,
            )
            current = selected.get(key)
            candidate_rank = (
                _is_consolidated(item.consolidated),
                item.filing_at,
                -item.mapping_priority,
            )
            if current is None or candidate_rank > (
                _is_consolidated(current.consolidated),
                current.filing_at,
                -current.mapping_priority,
            ):
                selected[key] = item
        return list(selected.values())

    @staticmethod
    def _find(
        observations: Iterable[_Observation],
        *,
        metric: str,
        period_kind: str,
        period_end: date | None = None,
        instant: date | None = None,
    ) -> _Observation | None:
        candidates = [
            item
            for item in observations
            if item.metric == metric
            and item.period_kind == period_kind
            and (period_end is None or item.period_end == period_end)
            and (instant is None or item.instant == instant)
            and (period_kind != "duration" or FundamentalCalculator._is_full_year(item))
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda item: item.mapping_priority)

    @staticmethod
    def _is_full_year(item: _Observation) -> bool:
        if item.period_start is None or item.period_end is None:
            return False
        days = (item.period_end - item.period_start).days + 1
        return 330 <= days <= 380

    @staticmethod
    def _nearest_year_end(
        ends: Iterable[date], latest: date, *, years: int
    ) -> date | None:
        try:
            target = latest.replace(year=latest.year - years)
        except ValueError:
            target = latest.replace(year=latest.year - years, day=28)
        candidates = list(ends)
        if not candidates:
            return None
        nearest = min(candidates, key=lambda value: abs((value - target).days))
        return nearest if abs((nearest - target).days) <= 60 else None

    @staticmethod
    def _equity(entity_type, instant, at) -> Decimal | None:
        if entity_type == "bank":
            return FundamentalCalculator._sum_available(
                instant("equity_share_capital", at), instant("reserves", at)
            )
        return instant("total_equity", at)

    @staticmethod
    def _capital_employed(instant, at, equity, debt) -> Decimal | None:
        assets = instant("total_assets", at)
        current_liabilities = instant("current_liabilities", at)
        if assets is not None and current_liabilities is not None:
            return assets - current_liabilities
        cash = instant("cash_and_equivalents", at)
        if equity is None or debt is None:
            return None
        return equity + debt - (cash or Decimal(0))

    @staticmethod
    def _average(first: Decimal | None, second: Decimal | None) -> Decimal | None:
        if first is None or second is None:
            return None
        return (first + second) / Decimal(2)

    @staticmethod
    def _sum_required(*values: Decimal | None) -> Decimal | None:
        return sum(values, Decimal(0)) if all(v is not None for v in values) else None

    @staticmethod
    def _sum_available(*values: Decimal | None) -> Decimal | None:
        present = [value for value in values if value is not None]
        return sum(present, Decimal(0)) if present else None

    @staticmethod
    def _ratio(numerator: Decimal | None, denominator: Decimal | None) -> float | None:
        if numerator is None or denominator is None or denominator == 0:
            return None
        return float(numerator / denominator)

    @staticmethod
    def _cagr(start: Decimal | None, end: Decimal | None, years: int) -> float | None:
        if start is None or end is None or start <= 0 or end <= 0:
            return None
        return (float(end / start) ** (1.0 / years)) - 1.0

    @staticmethod
    def _float(value: Decimal | None) -> float | None:
        return float(value) if value is not None else None


def _value(fact: FactLike | Mapping[str, object], name: str) -> object:
    try:
        return fact[name]  # type: ignore[index]
    except TypeError:
        return getattr(fact, name)


def _date(value: object) -> date | None:
    return date.fromisoformat(str(value)) if value else None


def _is_consolidated(value: str | None) -> bool:
    if value is None:
        return False
    normalized = value.strip().lower().replace("_", "-")
    return normalized in {"consolidated", "consol"}
