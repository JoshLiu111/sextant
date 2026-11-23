"""Discounted cash flow valuation and WACC (pure functions, numbers in and out).

Conventions follow FinanceToolkit's ``models/valuation`` (MIT): the base cash
flow is the latest actual year and is not discounted; year t's cash flow is
``FCF0 · (1 + g)^t`` for t = 1..N, discounted at ``(1 + r)^t``; the terminal value
is the Gordon growth value at year N, ``CF_N · (1 + g∞) / (r − g∞)``, discounted
at ``(1 + r)^N``. Rates are decimals (0.08 = 8%).
"""

from __future__ import annotations

from dataclasses import dataclass

from sextant_compute.analytics.errors import MetricError, MissingData


@dataclass(frozen=True)
class Dcf:
    projected: tuple[float, ...]  # CF_1 .. CF_N
    pv_forecast: float  # Σ CF_t / (1 + r)^t
    terminal_value: float  # undiscounted, at year N
    pv_terminal: float
    enterprise_value: float


def terminal_check(discount_rate: float, terminal_growth: float) -> None:
    if terminal_growth >= discount_rate:
        raise MetricError(
            f"Terminal growth ({terminal_growth:.2%}) must be below the discount rate ({discount_rate:.2%})."
        )


def dcf(base_fcf: float, *, growth: float, terminal_growth: float, discount_rate: float, years: int) -> Dcf:
    """Enterprise value of a free cash flow stream growing at ``growth`` for ``years``
    years, then at ``terminal_growth`` forever, discounted at ``discount_rate``."""
    terminal_check(discount_rate, terminal_growth)
    if discount_rate <= -1:
        raise MetricError("The discount rate must be above -100%.")
    projected = tuple(base_fcf * (1 + growth) ** t for t in range(1, years + 1))
    pv_forecast = sum(cf / (1 + discount_rate) ** t for t, cf in enumerate(projected, start=1))
    terminal_value = projected[-1] * (1 + terminal_growth) / (discount_rate - terminal_growth)
    pv_terminal = terminal_value / (1 + discount_rate) ** years
    return Dcf(projected, pv_forecast, terminal_value, pv_terminal, pv_forecast + pv_terminal)


def equity_value(enterprise_value: float, *, cash: float, total_debt: float) -> float:
    """Equity = EV + cash − total debt."""
    return enterprise_value + cash - total_debt


def per_share(equity: float, shares: float) -> float:
    if shares <= 0:
        raise MissingData("Common Shares Outstanding is zero or negative.")
    return equity / shares


def cost_of_equity(*, risk_free_rate: float, beta: float, equity_risk_premium: float) -> float:
    """CAPM: Re = rf + β · ERP."""
    return risk_free_rate + beta * equity_risk_premium


def cost_of_debt(*, interest_expense: float, total_debt: float) -> float:
    """Rd = interest expense / total debt (book)."""
    if total_debt <= 0:
        raise MetricError("The company reports no debt, so there is no cost of debt to derive. Enter one.")
    return abs(interest_expense) / total_debt


def tax_rate(*, income_tax: float, pretax_income: float) -> float:
    """Effective rate = income tax / pre-tax income, clipped to [0, 1]; 0 on a pre-tax loss."""
    if pretax_income <= 0:
        return 0.0
    return min(max(income_tax / pretax_income, 0.0), 1.0)


def debt_weight(*, equity: float, debt: float) -> float:
    """D / (D + E)."""
    if equity + debt <= 0:
        raise MetricError("Equity plus debt is zero or negative, so the capital structure is undefined.")
    if equity < 0:
        raise MetricError("The value of equity is negative. Enter a share price or a debt weight.")
    return debt / (equity + debt)


def wacc(*, cost_of_equity: float, cost_of_debt: float, tax_rate: float, debt_weight: float) -> float:
    """WACC = E/V · Re + D/V · Rd · (1 − t)."""
    return (1 - debt_weight) * cost_of_equity + debt_weight * cost_of_debt * (1 - tax_rate)
