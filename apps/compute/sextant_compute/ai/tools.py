"""Every tool's AI Explain endpoint: its request model, how to recompute its
result, and a short guide to its metric ids and units for the model.

Imported by ``ai/api.py`` (last line), so the routes exist before the router is mounted.
"""

from __future__ import annotations

from sextant_compute.ai.api import add_explainer
from sextant_compute.options.api import OptionsRequest
from sextant_compute.options.api import price as options_price
from sextant_compute.risk.api import RiskRequest, risk_metrics

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

