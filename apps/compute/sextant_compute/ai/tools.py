"""Sextant's compute endpoints as model tools (AI Analyst).

Each ``Tool`` pairs an endpoint's own request model (its JSON schema becomes the
tool's ``input_schema``, so parameters are typed exactly like the REST API) with
a ``run(req, data, ctx)`` that calls the endpoint function and returns its
result envelope. ``run_tool`` validates the model's input like FastAPI would and
turns expected failures into a message the model can read and act on.

Add a tool: append a ``Tool`` to ``TOOLS``.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, NamedTuple

from pydantic import BaseModel, ValidationError

from sextant_compute.company.api import StatementsRequest
from sextant_compute.company.api import statements as company_statements
from sextant_compute.company.ratios import RatiosRequest
from sextant_compute.company.ratios import ratios as company_ratios
from sextant_compute.data.context import RequestContext
from sextant_compute.data.errors import NoSuchData, SourceUnavailable
from sextant_compute.data.service import DataService
from sextant_compute.data.synthetic import HISTORY_END, HISTORY_START
from sextant_compute.db import Database
from sextant_compute.envelope import ResultEnvelope
from sextant_compute.errors import SOURCE_UNAVAILABLE_MESSAGE, ApiError, field_errors
from sextant_compute.macro.api import IndicatorsRequest, RatesRequest, headline_indicators, treasury_rates
from sextant_compute.options.api import AmericanRequest, OptionsRequest, StrategyRequest, american, strategy
from sextant_compute.options.api import price as options_price
from sextant_compute.portfolio.api import PortfolioRequest, portfolio_metrics
from sextant_compute.risk.api import RiskRequest, risk_metrics
from sextant_compute.screener.api import FilingsRequest, ScreenRequest, filings, screen
from sextant_compute.valuation.api import DcfRequest, dcf

Run = Callable[..., ResultEnvelope]
"""``(request, data, ctx)``, plus ``db`` when the tool ``needs_db``."""


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    request_model: type[BaseModel]
    run: Run
    needs_db: bool = False
    """``run`` takes the database as a fourth argument (risk: a user's uploaded factor files)."""

    def spec(self) -> dict:
        """The tool as the Messages API takes it."""
        return {"name": self.name, "description": self.description, "input_schema": input_schema(self.request_model)}


class ToolOutcome(NamedTuple):
    result: ResultEnvelope | None
    error: str | None
    """Why the call failed, written for the model (and shown in the trace)."""


DEMO = (
    "Market data is synthetic demo data: tickers DEMO-A to DEMO-F and the benchmark DEMO-MKT, daily "
    f"history {HISTORY_START} to {HISTORY_END} (start and end are YYYY-MM-DD in that range)."
)

TOOLS: list[Tool] = [
    Tool(
        "options_price",
        "Options Calculator: European Black-Scholes call and put prices, the five Greeks and, given a "
        "market_price, the implied volatility. Rates, yields and volatility are decimals (0.2 = 20%); "
        "time_to_expiry is in years. Metrics: call_price, put_price, call_delta, put_delta, gamma, vega, "
        "call_theta, put_theta, call_rho, put_rho, implied_volatility.",
        OptionsRequest,
        lambda req, _data, _ctx: options_price(req),
    ),
    Tool(
        "options_strategy",
        "Options Calculator: a multi-leg strategy (long/short calls, puts and the underlying) under "
        "Black-Scholes: net_cost, max_profit, max_loss and the position's delta, gamma, vega, theta, rho. "
        "Same market inputs as options_price.",
        StrategyRequest,
        lambda req, _data, _ctx: strategy(req),
    ),
    Tool(
        "options_american",
        "Options Calculator: American call and put prices from a binomial tree, the European tree prices "
        "and the early-exercise premium. Metrics: american_call, american_put, european_call_tree, "
        "european_put_tree, call_early_exercise_premium, put_early_exercise_premium.",
        AmericanRequest,
        lambda req, _data, _ctx: american(req),
    ),
    Tool(
        "risk_metrics",
        "Risk & Performance for one or more tickers vs a benchmark: annualized return and volatility, max "
        "drawdown, historical VaR/CVaR, Sharpe, Sortino, beta. Metric ids are '<metric>:<TICKER>'; returns, "
        "volatility, drawdown and VaR are decimals (0.18 = 18%). " + DEMO,
        RiskRequest,
        risk_metrics,
        needs_db=True,
    ),
    Tool(
        "portfolio_metrics",
        "My Portfolio: risk and performance of a weighted portfolio (weights are decimals that add up to 1) "
        "vs a benchmark. Metric ids are '<metric>:portfolio' and '<metric>:benchmark'. " + DEMO,
        PortfolioRequest,
        portfolio_metrics,
    ),
    Tool(
        "company_statements",
        "Company Health Check: standardized income statement, balance sheet and cash flow for a US-listed "
        "company from SEC EDGAR filings. Metric ids are '<line item>:<fiscal year end>'; values in USD.",
        StatementsRequest,
        company_statements,
    ),
    Tool(
        "company_ratios",
        "Company Health Check: efficiency, liquidity, profitability, solvency and valuation ratios plus the "
        "Altman Z, Piotroski F and Beneish M scores and the DuPont breakdown for up to 5 US companies side "
        "by side, from SEC EDGAR. Metric ids are '<ratio or score>:<TICKER>:<fiscal year end>' (e.g. "
        "'altman_z:AAPL:2024-09-28'); the ratios and models lists name them. Margins and returns "
        "are decimals (0.25 = 25%). Valuation ratios need a share price per company.",
        RatiosRequest,
        company_ratios,
    ),
    Tool(
        "valuation_dcf",
        "Valuation Calculator: free-cash-flow DCF for a US company from SEC EDGAR, with the WACC breakdown "
        "and a growth x discount rate sensitivity table. Rates are decimals. Null overrides use the "
        "computed WACC components.",
        DcfRequest,
        dcf,
    ),
    Tool(
        "macro_indicators",
        "Macro Dashboard: US real GDP growth, CPI inflation, unemployment rate and fed funds rate from FRED. "
        "Metric ids are 'latest:<indicator>'; values are in percent (3.2 = 3.2%).",
        IndicatorsRequest,
        headline_indicators,
    ),
    Tool(
        "treasury_rates",
        "Macro Dashboard: the US Treasury yield curve (latest, 1 month and 1 year ago) and the 10Y-2Y spread "
        "history with inversion periods. Yields are in percent.",
        RatesRequest,
        treasury_rates,
    ),
    Tool(
        "screen_companies",
        "Screener: filter US companies on fundamentals from SEC EDGAR frames for one calendar year. Each "
        "criterion is {metric, op: min|max, value}; percentages are decimals (0.1 = 10%), revenue is USD. "
        "Matching companies are in rows[].values; cite them as '<metric>:<TICKER>'.",
        ScreenRequest,
        screen,
    ),
    Tool(
        "sec_filings",
        "Latest SEC filings (form, title, filing date, link), market-wide or for one ticker.",
        FilingsRequest,
        filings,
    ),
]

TOOLS_BY_NAME = {t.name: t for t in TOOLS}


def specs() -> list[dict]:
    return [t.spec() for t in TOOLS]


def input_schema(model: type[BaseModel]) -> dict:
    """The request model's JSON schema with every ``$ref`` inlined (models nest, never recurse)."""
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def inline(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                target = copy.deepcopy(defs[node["$ref"].rsplit("/", 1)[-1]])
                rest = {k: v for k, v in node.items() if k != "$ref"}
                return inline({**target, **rest})
            return {k: inline(v) for k, v in node.items()}
        if isinstance(node, list):
            return [inline(v) for v in node]
        return node

    return inline(schema)


def _describe_fields(fields: dict[str, str]) -> str:
    return "Some inputs are invalid: " + "; ".join(f"{name}: {message}" for name, message in fields.items())


def run_tool(
    name: str, arguments: Any, data: DataService, ctx: RequestContext, db: Database | None = None
) -> ToolOutcome:
    """Run tool ``name`` on the model's ``arguments``. Bugs still raise."""
    tool = TOOLS_BY_NAME.get(name)
    if tool is None:
        return ToolOutcome(None, f"There is no tool named {name!r}. Use one of: {', '.join(TOOLS_BY_NAME)}.")
    try:
        req = tool.request_model.model_validate(arguments)
    except ValidationError as exc:
        return ToolOutcome(None, _describe_fields(field_errors(exc.errors())))
    try:
        result = tool.run(req, data, ctx, db) if tool.needs_db else tool.run(req, data, ctx)
        return ToolOutcome(result, None)
    except ApiError as exc:
        return ToolOutcome(None, _describe_fields(exc.fields) if exc.fields else exc.message)
    except NoSuchData as exc:
        return ToolOutcome(None, exc.message)
    except SourceUnavailable:
        return ToolOutcome(None, SOURCE_UNAVAILABLE_MESSAGE)
