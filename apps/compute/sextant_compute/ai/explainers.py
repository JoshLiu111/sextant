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
from sextant_compute.macro.api import IndicatorsRequest, RatesRequest, headline_indicators, treasury_rates
from sextant_compute.options.api import AmericanRequest, OptionsRequest, StrategyRequest, american, strategy
from sextant_compute.options.api import price as options_price
from sextant_compute.portfolio.api import PortfolioRequest, portfolio_metrics
from sextant_compute.portfolio.saved import SavedAnalysisSettings, saved_portfolio_metrics
from sextant_compute.risk.api import RiskRequest, risk_metrics
from sextant_compute.screener.api import FilingsRequest, ScreenRequest, filings, screen
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
(standard deviation of returns, annualized), max_drawdown (largest fall from a
peak, as a positive fraction; details give the peak, trough and recovery dates, recovery
null = not yet recovered), sharpe and sortino (excess return per unit of total / downside
risk, using meta.parameters.risk_free_rate), var and cvar (historical Value at Risk and
Conditional VaR over one return period at meta.parameters.confidence, as positive losses:
var 0.03 = in the worst periods the loss is at least 3%), parametric_var/cvar (normal
distribution) and cornish_fisher_var/cvar (adjusted for skew and fat tails), beta
(sensitivity to the benchmark's returns), alpha (CAPM, annualized), treynor,
information_ratio, upside_capture and downside_capture (vs the benchmark). Units:
decimal = a fraction (0.12 means 12%); ratio = a plain number.
"""

RISK_GUIDE = f"""
Risk & Performance: return and risk of each ticker, and of the benchmark, over
meta.parameters.start to end, using meta.parameters.period returns (daily, weekly or
monthly). Metric ids are "<metric>:<ticker>".
{RISK_METRICS.strip()}
Also: skewness and excess_kurtosis of the returns; factor regressions ff3_* (Fama-French
3-factor) and carhart_* (adds momentum): <model>_alpha (annualized decimal), the factor
loadings (details.t_stat) and <model>_r_squared; VaR backtests backtest_var,
backtest_parametric_var and backtest_cornish_fisher_var (value = breaches counted;
details give expected_breaches, the Kupiec statistic, p_value and result accept or
reject); garch_volatility (GARCH(1,1) current annualized volatility; details give the
fitted omega, alpha, beta, persistence and long_run_volatility).
Series: drawdown:<ticker> is the fall below the running peak on each date (0 = at a
peak); rolling_volatility, rolling_sharpe and rolling_beta over
meta.parameters.rolling_window trading days; return_distribution is a histogram;
garch_volatility is the conditional volatility over time.
"""

OPTIONS_STRATEGY_GUIDE = """
Options Calculator, strategy builder: several legs (meta.parameters.legs: call, put or
the underlying; long or short; quantity; strike) on one underlying, valued with
Black-Scholes. Market inputs are decimals as in the single-option tab (volatility 0.2 =
20%, time_to_expiry in years). net_cost is what the position costs today (negative = a
credit received); max_profit and max_loss (a positive amount) are at expiry, net of
that cost; when either is unlimited its status is "error" with the reason "Unlimited...".
Greeks delta, gamma, vega, theta, rho are for the whole position (per_dollar, per_vol_point
= per 1 percentage point of volatility, per_day, per_rate_point). Series profit_at_expiry
and profit_today are profit across spot prices; <greek>_vs_spot and <greek>_vs_time show
how the Greeks change with the spot and as expiry nears.
"""

OPTIONS_AMERICAN_GUIDE = """
Options Calculator, American options on a binomial (Cox-Ross-Rubinstein) tree with
meta.parameters.steps steps. For call and put: american_<kind> (tree, early exercise
allowed), european_<kind>_tree (same tree, no early exercise), european_<kind>
(Black-Scholes), and <kind>_early_exercise_premium = american minus european on the same
tree (what the right to exercise early is worth). All in currency per share. Series
american_<kind>_by_steps and european_<kind>_tree_by_steps show the tree price converging
as the number of steps grows (x = steps).
"""

add_explainer("options", OptionsRequest, lambda req, _: options_price(req), OPTIONS_GUIDE)
add_explainer("options-strategy", StrategyRequest, lambda req, _: strategy(req), OPTIONS_STRATEGY_GUIDE)
add_explainer("options-american", AmericanRequest, lambda req, _: american(req), OPTIONS_AMERICAN_GUIDE)
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
unrealized_pnl:portfolio are money in meta.parameters.reporting_currency (valued at the
last close in the range); holdings in another currency are converted at each amount's own
date's exchange rate (Frankfurter). unrealized_return:portfolio is a decimal.
{RISK_METRICS.strip()}
Series: cumulative_return:portfolio and cumulative_return:benchmark (0.25 = up 25% since the start).
"""


class SavedPortfolioRequest(SavedAnalysisSettings):
    """A saved portfolio's result is asked for by its id (the rest of its
    ``meta.parameters``, name and holdings, is reloaded from the database)."""

    portfolio_id: UUID


def _saved_portfolio(req: SavedPortfolioRequest, i: ToolInputs) -> ResultEnvelope:
    settings = SavedAnalysisSettings(**req.model_dump(exclude={"portfolio_id"}))
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
"models" lists the scoring models: altman_z (Altman Z-Score, details.zone safe, grey
or distress, inputs x1..x5), piotroski_f (Piotroski F-Score 0-9, details.zone strong,
neutral or weak) with its nine piotroski_* signals (1 = pass, 0 = fail), beneish_m
(Beneish M-Score, details.zone likely or unlikely earnings manipulation, threshold
-1.78), and the DuPont factors dupont_tax_burden and dupont_interest_burden (which
multiply with net_margin, asset_turnover and equity_multiplier back to
return_on_equity). With several companies, compare them on the same ratios and years.
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


MACRO_GUIDE = """
Macro Dashboard: four US headline indicators from FRED. Metrics latest:gdp_growth (real
GDP growth, quarterly, annualized), latest:cpi_inflation (consumer prices, change from a
year earlier), latest:unemployment_rate and latest:fed_funds_rate (monthly); all in
percent (2.3 means 2.3%). details give the observation date, the series' title, units,
frequency and last update. Series history:<indicator> is the history since
meta.parameters.start (x = date), thinned to a few points here.
"""

MACRO_RATES_GUIDE = """
Macro Dashboard, US Treasury rates (par yield curve). Metrics latest:yield_2y and
latest:yield_10y are percent; latest:spread_10y_2y is the 10-year minus the 2-year yield
in percentage points (below 0 = an inverted curve). Series yield_curve:latest,
yield_curve:1m_ago and yield_curve:1y_ago are the curves (x = maturity in years, y =
yield in percent; details.date = the curve's date), thinned to a few maturities here.
history:spread_10y_2y is the spread over time; its bands are the inversion periods.
"""

SCREEN_GUIDE = """
Screener: US companies filtered on fundamentals from SEC EDGAR for calendar year "year".
"criteria" are the filters (op min = at least, max = at most; value is a decimal for
percentages, 0.1 = 10%, US dollars for revenue, a multiple for ratios). universe =
companies screened, matched = companies passing every criterion, excluded = companies
left out because an input of a criterion was missing, per criterion with reasons.
"rows" lists at most the first {rows} matches in the chosen sort order; "values" holds
each row's figures for the "columns". Price criteria (change_52w = 52-week price
change; from_52w_high = last close vs the 52-week high, 0 or negative; both decimals)
use the user's own price provider (meta.parameters.price_source); the others use SEC EDGAR.
"""

FILINGS_GUIDE = """
Screener, latest SEC filings: scope "market" = the newest filings by any company,
"company" = one company's newest filings. Each filing has a form type (10-K annual
report, 10-Q quarterly report, 8-K current report, 4 insider trade, S-1 registration,
DEF 14A proxy, ...), a title, the company and the filing date. Say what kinds of filings
these are; do not guess at their content.
"""

PROMPT_ROWS = 25
"""Screen rows and filings shown to the model; the counts still cover them all."""


def _screen(req: ScreenRequest, i: ToolInputs) -> ResultEnvelope:
    result = screen(req, i.data, i.ctx)
    return result.model_copy(update={"rows": result.rows[:PROMPT_ROWS]})


def _filings(req: FilingsRequest, i: ToolInputs) -> ResultEnvelope:
    result = filings(req, i.data, i.ctx)
    return result.model_copy(update={"filings": result.filings[:PROMPT_ROWS]})


add_explainer("macro", IndicatorsRequest, lambda req, i: headline_indicators(req, i.data, i.ctx), MACRO_GUIDE)
add_explainer("macro-rates", RatesRequest, lambda req, i: treasury_rates(req, i.data, i.ctx), MACRO_RATES_GUIDE)
add_explainer("screener", ScreenRequest, _screen, SCREEN_GUIDE.format(rows=PROMPT_ROWS))
add_explainer("screener-filings", FilingsRequest, _filings, FILINGS_GUIDE)
