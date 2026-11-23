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


BENEISH_THRESHOLD = -1.78


def _soft_assets_share(y: Year) -> float:
    """Assets other than current assets and PP&E, as a share of total assets."""
    return 1 - div(y("current_assets") + y("ppe_net"), y("total_assets"), "Total Assets")


def _depreciation_rate(y: Year) -> float:
    da = y("depreciation_amortization")
    return div(da, da + y("ppe_net"), "D&A plus PP&E")


def _leverage_share(y: Year) -> float:
    return div(y("current_liabilities") + y("long_term_debt"), y("total_assets"), "Total Assets")


def _index(now: float, before: float, what: str) -> float:
    return div(now, before, f"The prior year's {what}")


def beneish_m(y: Year) -> WithDetails:
    """Beneish M-Score, the 1999 eight-variable model. Each index compares this
    year with the prior one: DSRI (receivables / sales), GMI (prior gross margin
    / this year's), AQI (non-current, non-PP&E assets share), SGI (sales growth),
    DEPI (prior depreciation rate / this year's), SGAI (SG&A / sales), TATA
    (net income minus operating cash flow, over total assets) and LVGI ((current
    liabilities + long-term debt) / total assets). Above -1.78 flags a likely
    earnings manipulator."""
    p = y.last_year()
    dsri = _index(
        div(y("receivables"), y("revenue"), "Revenue"), div(p("receivables"), p("revenue"), "Revenue"),
        "receivables to sales",
    )
    gmi = _index(_gross_margin(p), _gross_margin(y), "gross margin")
    aqi = _index(_soft_assets_share(y), _soft_assets_share(p), "asset quality")
    sgi = _index(y("revenue"), p("revenue"), "revenue")
    depi = _index(_depreciation_rate(p), _depreciation_rate(y), "depreciation rate")
    sgai = _index(
        div(y("selling_general_administrative"), y("revenue"), "Revenue"),
        div(p("selling_general_administrative"), p("revenue"), "Revenue"),
        "SG&A to sales",
    )
    tata = div(y("net_income") - y("operating_cash_flow"), y("total_assets"), "Total Assets")
    lvgi = _index(_leverage_share(y), _leverage_share(p), "leverage")
    m = (
        -4.84
        + 0.920 * dsri
        + 0.528 * gmi
        + 0.404 * aqi
        + 0.892 * sgi
        + 0.115 * depi
        - 0.172 * sgai
        + 4.679 * tata
        - 0.327 * lvgi
    )
    zone = "likely" if m > BENEISH_THRESHOLD else "unlikely"
    return WithDetails(
        m,
        {"zone": zone, "dsri": dsri, "gmi": gmi, "aqi": aqi, "sgi": sgi, "depi": depi, "sgai": sgai, "tata": tata, "lvgi": lvgi},
    )


MODELS: tuple[Ratio, ...] = (
    ALTMAN_Z,
    Ratio("piotroski_f", "scores", "score", piotroski_f),
    Ratio("beneish_m", "scores", "score", beneish_m),
    *PIOTROSKI_SIGNALS,
)
"""Every model, in display order: the scores, then the Piotroski signals, then
the DuPont burdens."""
