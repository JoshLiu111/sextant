"""Quality and manipulation scores, and the DuPont decomposition, on ``Year``.

Pure, like ``ratios``: each model reads line items through ``Year``, so a
missing item raises ``MissingData`` naming it and only the models that read it
are affected.

Piotroski F-Score (2000): nine pass/fail signals, each its own metric (1 = pass)
so one missing item marks only its signal, and the score, as missing. Following
the paper, ROA, cash-flow ROA and asset turnover scale by the opening (prior year
end) total assets, and leverage is long-term debt over average total assets.
"No dilution" compares weighted-average basic shares, which every filer reports.
Year-over-year signals need the prior year's measure too, so they need two
years of history before the year scored. Zones: 8-9 strong, 0-2 weak.

Beneish M-Score (1999, eight variables): see ``beneish_m``.

DuPont: ROE = net margin x asset turnover x equity multiplier (three-step), and
net margin = tax burden x interest burden x operating (EBIT) margin (five-step).
The margins, turnover and multiplier are the ratios in ``ratios.RATIOS``; this
module adds only the two burdens. With operating income as EBIT and the same
averaged balances as ROE, the components multiply back to ROE exactly.
"""

from __future__ import annotations

from collections.abc import Callable

from sextant_compute.analytics.ratios import ALTMAN_Z, Ratio, WithDetails, Year, div

PIOTROSKI_STRONG = 8
PIOTROSKI_WEAK = 2


def _roa(y: Year) -> float:
    return div(y("net_income"), y.opening("total_assets"), "Opening Total Assets")


def _cash_roa(y: Year) -> float:
    return div(y("operating_cash_flow"), y.opening("total_assets"), "Opening Total Assets")


def _leverage(y: Year) -> float:
    return div(y("long_term_debt"), y.avg("total_assets"), "Average Total Assets")


def _current_ratio(y: Year) -> float:
    return div(y("current_assets"), y("current_liabilities"), "Current Liabilities")


def _gross_margin(y: Year) -> float:
    return div(y("gross_profit"), y("revenue"), "Revenue")


def _asset_turnover(y: Year) -> float:
    return div(y("revenue"), y.opening("total_assets"), "Opening Total Assets")


def _signal(passed: bool, measure: float, compared_with: float | None = None) -> WithDetails:
    details: dict[str, float | None] = {"measure": measure}
    if compared_with is not None:
        details["compared_with"] = compared_with
    return WithDetails(1.0 if passed else 0.0, details)


def _rose(measure: Callable[[Year], float]) -> Callable[[Year], WithDetails]:
    """Pass when ``measure`` is higher than the prior year's."""

    def signal(y: Year) -> WithDetails:
        now, before = measure(y), measure(y.last_year())
        return _signal(now > before, now, before)

    return signal


def _did_not_rise(measure: Callable[[Year], float]) -> Callable[[Year], WithDetails]:
    """Pass when ``measure`` is no higher than the prior year's."""

    def signal(y: Year) -> WithDetails:
        now, before = measure(y), measure(y.last_year())
        return _signal(now <= before, now, before)

    return signal


def _positive_roa(y: Year) -> WithDetails:
    roa = _roa(y)
    return _signal(roa > 0, roa)


def _positive_cfo(y: Year) -> WithDetails:
    cash_roa = _cash_roa(y)
    return _signal(y("operating_cash_flow") > 0, cash_roa)


def _accrual(y: Year) -> WithDetails:
    cash_roa, roa = _cash_roa(y), _roa(y)
    return _signal(cash_roa > roa, cash_roa, roa)


PIOTROSKI_SIGNALS: tuple[Ratio, ...] = (
    Ratio("piotroski_roa", "piotroski", "signal", _positive_roa),
    Ratio("piotroski_cfo", "piotroski", "signal", _positive_cfo),
    Ratio("piotroski_delta_roa", "piotroski", "signal", _rose(_roa)),
    Ratio("piotroski_accrual", "piotroski", "signal", _accrual),
    Ratio("piotroski_delta_leverage", "piotroski", "signal", _did_not_rise(_leverage)),
    Ratio("piotroski_delta_current_ratio", "piotroski", "signal", _rose(_current_ratio)),
    Ratio("piotroski_no_dilution", "piotroski", "signal", _did_not_rise(lambda y: y("shares_basic"))),
    Ratio("piotroski_delta_gross_margin", "piotroski", "signal", _rose(_gross_margin)),
    Ratio("piotroski_delta_asset_turnover", "piotroski", "signal", _rose(_asset_turnover)),
)


def piotroski_f(y: Year) -> WithDetails:
    """The number of signals passed (0-9); missing if any signal is."""
    passed = {s.id: s.compute(y).value for s in PIOTROSKI_SIGNALS}
    score = sum(passed.values())
    zone = "strong" if score >= PIOTROSKI_STRONG else "weak" if score <= PIOTROSKI_WEAK else "neutral"
    return WithDetails(score, {"zone": zone, **passed})


MODELS: tuple[Ratio, ...] = (
    ALTMAN_Z,
    Ratio("piotroski_f", "scores", "score", piotroski_f),
    *PIOTROSKI_SIGNALS,
)
"""Every model, in display order: the scores, then the Piotroski signals, then
the DuPont burdens."""
