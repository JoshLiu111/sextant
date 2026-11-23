"""Every tool's AI Explain endpoint: its request model, how to recompute its
result, and a short guide to its metric ids and units for the model.

Imported by ``ai/api.py`` (last line), so the routes exist before the router is mounted.
"""

from __future__ import annotations

from uuid import UUID

from sextant_compute.ai.api import ToolInputs, add_explainer
from sextant_compute.company.api import StatementsRequest, statements
from sextant_compute.company.ratios import RatiosRequest, ratios
from sextant_compute.envelope import ResultEnvelope
from sextant_compute.options.api import OptionsRequest
from sextant_compute.options.api import price as options_price
from sextant_compute.portfolio.api import AnalysisSettings, PortfolioRequest, portfolio_metrics
from sextant_compute.portfolio.saved import saved_portfolio_metrics
from sextant_compute.risk.api import RiskRequest, risk_metrics
from sextant_compute.valuation.api import DcfRequest, dcf

OPTIONS_GUIDE = """
Options Calculator: European Black-Scholes prices and Greeks for one option.
Inputs (meta.parameters) are decimals: volatility 0.2 means 20%, rates and dividend
yield likewise; time_to_expiry is in years. option_type selects the chart and the
implied volatility; prices and Greeks are given for both the call and the put.
Units: currency = price per share; per_dollar = change per $1 move in the spot
(Delta, Gamma); per_vol_point = price change per 1 percentage point of volatility
(Vega); per_day = price change per calendar day (Theta, usually negative);
per_rate_point = price change per 1 percentage point of the risk-free rate (Rho);
decimal = a fraction (implied volatility 0.25 means 25%). implied_volatility is
missing_data unless a market price was entered. Series: payoff_at_expiry and
theoretical_value across spot prices (x = spot, y = option value).
"""

RISK_METRICS = """
Metric names: annualized_return (compound annual total return), annualized_volatility
(standard deviation of daily returns, annualized), max_drawdown (largest fall from a
peak, as a positive fraction; details give the peak, trough and recovery dates, recovery
null = not yet recovered), sharpe and sortino (excess return per unit of total / downside
risk, using meta.parameters.risk_free_rate), var and cvar (historical one-day Value at
Risk and Conditional VaR at meta.parameters.confidence, as positive losses: var 0.03 =
on the worst days the loss is at least 3%), beta (sensitivity to the benchmark's daily
returns). Units: decimal = a fraction (0.12 means 12%); ratio = a plain number.
"""

RISK_GUIDE = f"""
Risk & Performance: return and risk of each ticker, and of the benchmark, over
meta.parameters.start to end. Metric ids are "<metric>:<ticker>".
{RISK_METRICS.strip()}
Series: drawdown:<ticker> is the fall below the running peak on each date (0 = at a peak).
"""

add_explainer("options", OptionsRequest, lambda req, _: options_price(req), OPTIONS_GUIDE)
add_explainer("risk", RiskRequest, lambda req, i: risk_metrics(req, i.data, i.ctx), RISK_GUIDE)


PORTFOLIO_GUIDE = f"""
My Portfolio: one portfolio (meta.parameters.holdings: tickers with weights as
decimals, 0.6 = 60%, rebalanced daily) against meta.parameters.benchmark over start to
end. Metric ids are "<metric>:portfolio" and "<metric>:benchmark".
{RISK_METRICS.strip()}
Series: cumulative_return:portfolio and cumulative_return:benchmark (0.25 = up 25% since the start).
"""

SAVED_PORTFOLIO_GUIDE = f"""
My Portfolio, a saved portfolio: the user's holdings (meta.parameters.holdings: ticker,
quantity, cost_price per unit, currency) held at those quantities (buy and hold) against
meta.parameters.benchmark over start to end. Metric ids are "<metric>:portfolio" and
"<metric>:benchmark". market_value:portfolio, cost_basis:portfolio and
unrealized_pnl:portfolio are money in the holdings' currency (valued at the last close
in the range); unrealized_return:portfolio is a decimal.
{RISK_METRICS.strip()}
Series: cumulative_return:portfolio and cumulative_return:benchmark (0.25 = up 25% since the start).
"""


class SavedPortfolioRequest(AnalysisSettings):
    """A saved portfolio's result is asked for by its id (the rest of its
    ``meta.parameters``, name and holdings, is reloaded from the database)."""

    portfolio_id: UUID


def _saved_portfolio(req: SavedPortfolioRequest, i: ToolInputs) -> ResultEnvelope:
    settings = AnalysisSettings(**req.model_dump(exclude={"portfolio_id"}))
    return saved_portfolio_metrics(req.portfolio_id, settings, i.user, i.db, i.data, i.ctx)


add_explainer("portfolio", PortfolioRequest, lambda req, i: portfolio_metrics(req, i.data, i.ctx), PORTFOLIO_GUIDE)
add_explainer("portfolio-saved", SavedPortfolioRequest, _saved_portfolio, SAVED_PORTFOLIO_GUIDE)


EDGAR_UNITS = """
Units: currency = US dollars (a full number, not millions); per_share = dollars per
share; shares = a share count; decimal = a fraction (0.25 means 25%); ratio = a plain
multiple; days = a number of days; score = Altman Z points. Figures come from the
company's own SEC filings (fiscal years, not calendar years).
"""

COMPANY_GUIDE = f"""
Company Health Check, standardized financial statements of one US company from its SEC
filings. Each metric "<item id>:<period id>" is one line item for one fiscal year (the
period id is the fiscal year end); "items" lists the line items with their statement
(income, balance, cash_flow) and "periods" the fiscal years. A missing_data cell means
the company did not report that item (details.missing: not_reported) or not for that year.
{EDGAR_UNITS.strip()}
"""

COMPANY_RATIOS_GUIDE = f"""
Company Health Check, financial ratios of one or more US companies from their SEC
filings, in five categories: efficiency, liquidity, profitability, solvency, valuation.
Each metric is "<ratio id>:<TICKER>:<period id>" (the period id is the fiscal year end);
"ratios" lists the ratio ids with category and unit, "companies" each company's fiscal
years and the optional share price the user entered. Valuation ratios that need a share
price (price_to_earnings and so on) are missing_data unless a price was entered.
altman_z is the Altman Z-Score with details.zone (safe, grey or distress) and its five
inputs x1..x5. With several companies, compare them on the same ratios and years.
{EDGAR_UNITS.strip()}
"""

VALUATION_GUIDE = f"""
Valuation Calculator: a discounted free cash flow (DCF) valuation of one US company.
Free cash flow = operating cash flow - capital expenditure, from the base fiscal year
(base_period) in its SEC filings, grown at meta.parameters.growth_rate for
forecast_years, then at terminal_growth forever, discounted at discount_rate (the WACC
unless overridden). WACC metrics: cost_of_equity (CAPM from risk_free_rate, beta and
equity_risk_premium), cost_of_debt (interest expense / total debt), tax_rate,
after_tax_cost_of_debt, debt_weight, equity_weight, wacc; details.basis says whether a
component was derived from the filings or overridden by the user. Results:
pv_forecast_fcf, terminal_value, pv_terminal_value, enterprise_value, equity_value
(enterprise value + cash and short-term investments - total debt),
intrinsic_value_per_share. "sensitivity:<i>:<j>" is the value per share at
sensitivity.growth_rates[i] and sensitivity.discount_rates[j]; the center cell is the
base case. Series: projected_fcf by forecast year, historical_fcf by fiscal year end.
The result depends heavily on the assumptions; it is a model, not a price target.
{EDGAR_UNITS.strip()}
"""

add_explainer("company", StatementsRequest, lambda req, i: statements(req, i.data, i.ctx), COMPANY_GUIDE)
add_explainer("company-ratios", RatiosRequest, lambda req, i: ratios(req, i.data, i.ctx), COMPANY_RATIOS_GUIDE)
add_explainer("valuation", DcfRequest, lambda req, i: dcf(req, i.data, i.ctx), VALUATION_GUIDE)
