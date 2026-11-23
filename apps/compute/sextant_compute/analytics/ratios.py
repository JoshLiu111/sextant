"""Financial ratios and the Altman Z-Score on standardized annual statements.

Formulas follow FinanceToolkit's ratio models (MIT): balance-sheet items in a
ratio with a flow (income or cash flow) use the average of the opening and
closing balance, so a period's ratio needs the prior fiscal year too; the
earliest year of the data gets ``MissingData`` naming the prior year. EBITDA
is operating income + D&A. Total debt is current debt + long-term debt.

Each ratio reads line items through ``Year``, which raises ``MissingData``
naming the item (from ``FinancialStatements.value``), so only the ratios that
need a missing item are affected. Division by zero raises ``MissingData``
naming the zero item; a ratio that isn't meaningful (P/B on negative book
value, EV/EBITDA on negative EBITDA) raises ``MetricError``.

Valuation multiples need a share price. There is no public price source, so
the caller passes an optional price for the latest fiscal year; earlier years
(and the latest year without a price) get ``MissingData`` saying a price is
required.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from sextant_compute.analytics.errors import MissingData
from sextant_compute.analytics.guards import positive
from sextant_compute.data.statements import FinancialStatements, FiscalPeriod
from sextant_compute.envelope import Detailed

Category = Literal["efficiency", "liquidity", "profitability", "solvency", "valuation", "distress"]
CATEGORIES: tuple[Category, ...] = ("efficiency", "liquidity", "profitability", "solvency", "valuation", "distress")
DAYS = 365


class Year:
    """One fiscal period's view of the statements, with the prior period for averages."""

    def __init__(
        self,
        statements: FinancialStatements,
        index: int,
        *,
        price: float | None = None,
    ) -> None:
        self.st = statements
        self.index = index
        self.period: FiscalPeriod = statements.periods[index]
        self.prior: FiscalPeriod | None = statements.periods[index - 1] if index > 0 else None
        self.is_latest = index == len(statements.periods) - 1
        self._price = price

    def __call__(self, item_id: str) -> float:
        """The period's reported value (``MissingData`` names the item if absent)."""
        return self.st.value(item_id, self.period.id)

    def label(self, item_id: str) -> str:
        return self.st.item(item_id).label

    def avg(self, item_id: str) -> float:
        """Average of the opening (prior year end) and closing balance."""
        if self.prior is None:
            raise MissingData(
                f"Needs the prior year's {self.label(item_id)} for the average balance, "
                f"and {self.period.label} is the earliest year in the data."
            )
        return (self.st.value(item_id, self.prior.id) + self(item_id)) / 2

    def total_debt(self) -> float:
        return self("current_debt") + self("long_term_debt")

    def avg_total_debt(self) -> float:
        return self.avg("current_debt") + self.avg("long_term_debt")

    def ebitda(self) -> float:
        return self("operating_income") + self("depreciation_amortization")

    def free_cash_flow(self) -> float:
        return self("operating_cash_flow") - self("capital_expenditure")

    def price(self, ratio: str) -> float:
        if not self.is_latest:
            raise MissingData(
                f"{ratio} needs the share price at the end of {self.period.label}. Sextant has no price "
                "source, so only the latest fiscal year is valued, with the price you enter."
            )
        if self._price is None:
            raise MissingData(f"A share price is required: enter the current share price to compute {ratio}.")
        return self._price

    def market_cap(self, ratio: str) -> float:
        return self.price(ratio) * self("shares_outstanding")


def div(numerator: float, denominator: float, what: str) -> float:
    """``numerator / denominator``; a zero denominator is ``MissingData`` naming ``what``."""
    if denominator == 0:
        raise MissingData(f"{what} is zero, so the ratio is undefined.")
    return numerator / denominator


@dataclass(frozen=True)
class Ratio:
    id: str
    category: Category
    unit: str  # envelope unit: ratio | decimal | days | currency | per_share
    compute: Callable[[Year], float | Detailed]


def _tax_rate(y: Year) -> float:
    """Effective tax rate clipped to [0, 1]; 0 when pretax income is not positive."""
    pretax = y("pretax_income")
    if pretax <= 0:
        return 0.0
    return min(max(y("income_tax") / pretax, 0.0), 1.0)


def _effective_tax_rate(y: Year) -> float:
    pretax = positive(y("pretax_income"), "Pretax income", "the effective tax rate")
    return y("income_tax") / pretax


def _dio(y: Year) -> float:
    return div(y.avg("inventory"), y("cost_of_revenue"), "Cost of Revenue") * DAYS


def _dso(y: Year) -> float:
    return div(y.avg("receivables"), y("revenue"), "Revenue") * DAYS


def _dpo(y: Year) -> float:
    return div(y.avg("accounts_payable"), y("cost_of_revenue"), "Cost of Revenue") * DAYS


def _interest_coverage(y: Year) -> float:
    return div(y("operating_income"), y("interest_expense"), "Interest Expense")


def _net_debt_to_ebitda(y: Year) -> float:
    ebitda = positive(y.ebitda(), "EBITDA", "net debt / EBITDA")
    return (y.total_debt() - y("cash")) / ebitda


def _roic(y: Year) -> float:
    nopat = y("operating_income") * (1 - _tax_rate(y))
    return div(nopat, y.avg("total_equity") + y.avg_total_debt(), "Average invested capital")


def _pe(y: Year) -> float:
    eps = positive(y("eps_diluted"), "Diluted EPS", "P/E")
    return y.price("P/E") / eps


def _pb(y: Year) -> float:
    bvps = positive(_bvps(y), "Book value per share", "P/B")
    return y.price("P/B") / bvps


def _bvps(y: Year) -> float:
    return div(y("total_equity"), y("shares_outstanding"), "Shares Outstanding")


def _fcf_per_share(y: Year) -> float:
    return div(y.free_cash_flow(), y("shares_outstanding"), "Shares Outstanding")


def _price_to_fcf(y: Year) -> float:
    fcf = positive(y.free_cash_flow(), "Free cash flow", "P/FCF")
    return y.market_cap("P/FCF") / fcf


def _ev_to_ebitda(y: Year) -> float:
    ebitda = positive(y.ebitda(), "EBITDA", "EV/EBITDA")
    ev = y.market_cap("EV/EBITDA") + y.total_debt() - y("cash")
    return ev / ebitda


def _dividend_yield(y: Year) -> float:
    per_share = div(y("dividends_paid"), y("shares_outstanding"), "Shares Outstanding")
    return per_share / y.price("the dividend yield")


ALTMAN_DISTRESS = 1.23
ALTMAN_SAFE = 2.90


def altman_z(y: Year) -> Detailed:
    """Altman Z' (1983, book-value equity): there is no public market price, so
    X4 uses book equity instead of market capitalization (the 1968 original).
    Zones: distress below 1.23, safe above 2.90, grey in between."""
    ta = y("total_assets")
    working_capital = y("current_assets") - y("current_liabilities")
    x1 = div(working_capital, ta, "Total Assets")
    x2 = div(y("retained_earnings"), ta, "Total Assets")
    x3 = div(y("operating_income"), ta, "Total Assets")
    x4 = div(y("total_equity"), y("total_liabilities"), "Total Liabilities")
    x5 = div(y("revenue"), ta, "Total Assets")
    z = 0.717 * x1 + 0.847 * x2 + 3.107 * x3 + 0.420 * x4 + 0.998 * x5
    zone = "safe" if z > ALTMAN_SAFE else "distress" if z < ALTMAN_DISTRESS else "grey"
    return Detailed(z, {"zone": zone, "x1": x1, "x2": x2, "x3": x3, "x4": x4, "x5": x5})


RATIOS: tuple[Ratio, ...] = (
    # Efficiency
    Ratio("asset_turnover", "efficiency", "ratio", lambda y: div(y("revenue"), y.avg("total_assets"), "Average Total Assets")),
    Ratio("fixed_asset_turnover", "efficiency", "ratio", lambda y: div(y("revenue"), y.avg("ppe_net"), "Average Property, Plant and Equipment")),
    Ratio("inventory_turnover", "efficiency", "ratio", lambda y: div(y("cost_of_revenue"), y.avg("inventory"), "Average Inventory")),
    Ratio("receivables_turnover", "efficiency", "ratio", lambda y: div(y("revenue"), y.avg("receivables"), "Average Receivables")),
    Ratio("payables_turnover", "efficiency", "ratio", lambda y: div(y("cost_of_revenue"), y.avg("accounts_payable"), "Average Accounts Payable")),
    Ratio("days_sales_outstanding", "efficiency", "days", _dso),
    Ratio("days_inventory_outstanding", "efficiency", "days", _dio),
    Ratio("days_payables_outstanding", "efficiency", "days", _dpo),
    Ratio("cash_conversion_cycle", "efficiency", "days", lambda y: _dio(y) + _dso(y) - _dpo(y)),
    # Liquidity
    Ratio("current_ratio", "liquidity", "ratio", lambda y: div(y("current_assets"), y("current_liabilities"), "Current Liabilities")),
    Ratio("quick_ratio", "liquidity", "ratio", lambda y: div(y("cash") + y("receivables"), y("current_liabilities"), "Current Liabilities")),
    Ratio("cash_ratio", "liquidity", "ratio", lambda y: div(y("cash"), y("current_liabilities"), "Current Liabilities")),
    Ratio("operating_cash_flow_ratio", "liquidity", "ratio", lambda y: div(y("operating_cash_flow"), y("current_liabilities"), "Current Liabilities")),
    Ratio("working_capital", "liquidity", "currency", lambda y: y("current_assets") - y("current_liabilities")),
    # Profitability
    Ratio("gross_margin", "profitability", "decimal", lambda y: div(y("gross_profit"), y("revenue"), "Revenue")),
    Ratio("operating_margin", "profitability", "decimal", lambda y: div(y("operating_income"), y("revenue"), "Revenue")),
    Ratio("ebitda_margin", "profitability", "decimal", lambda y: div(y.ebitda(), y("revenue"), "Revenue")),
    Ratio("net_margin", "profitability", "decimal", lambda y: div(y("net_income"), y("revenue"), "Revenue")),
    Ratio("free_cash_flow_margin", "profitability", "decimal", lambda y: div(y.free_cash_flow(), y("revenue"), "Revenue")),
    Ratio("effective_tax_rate", "profitability", "decimal", _effective_tax_rate),
    Ratio("return_on_assets", "profitability", "decimal", lambda y: div(y("net_income"), y.avg("total_assets"), "Average Total Assets")),
    Ratio("return_on_equity", "profitability", "decimal", lambda y: div(y("net_income"), y.avg("total_equity"), "Average Total Equity")),
    Ratio("return_on_invested_capital", "profitability", "decimal", _roic),
    # Solvency
    Ratio("debt_to_assets", "solvency", "ratio", lambda y: div(y.total_debt(), y("total_assets"), "Total Assets")),
    Ratio("debt_to_equity", "solvency", "ratio", lambda y: div(y.total_debt(), y("total_equity"), "Total Equity")),
    Ratio("debt_to_capital", "solvency", "ratio", lambda y: div(y.total_debt(), y.total_debt() + y("total_equity"), "Total capital")),
    Ratio("equity_multiplier", "solvency", "ratio", lambda y: div(y.avg("total_assets"), y.avg("total_equity"), "Average Total Equity")),
    Ratio("interest_coverage", "solvency", "ratio", _interest_coverage),
    Ratio("net_debt_to_ebitda", "solvency", "ratio", _net_debt_to_ebitda),
    # Valuation
    Ratio("book_value_per_share", "valuation", "per_share", _bvps),
    Ratio("free_cash_flow_per_share", "valuation", "per_share", _fcf_per_share),
    Ratio("dividend_payout_ratio", "valuation", "decimal", lambda y: div(y("dividends_paid"), y("net_income"), "Net Income")),
    Ratio("price_to_earnings", "valuation", "ratio", _pe),
    Ratio("price_to_book", "valuation", "ratio", _pb),
    Ratio("price_to_sales", "valuation", "ratio", lambda y: div(y.market_cap("P/S"), y("revenue"), "Revenue")),
    Ratio("price_to_free_cash_flow", "valuation", "ratio", _price_to_fcf),
    Ratio("ev_to_ebitda", "valuation", "ratio", _ev_to_ebitda),
    Ratio("dividend_yield", "valuation", "decimal", _dividend_yield),
)

ALTMAN_Z = Ratio("altman_z", "distress", "score", altman_z)
