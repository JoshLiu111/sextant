"""Risk & Performance time-scale views (#24): return periods, rolling metrics,
the marked underwater chart and the return distribution. All through the HTTP API."""

import math

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from data_fixtures import FixtureAdapter, price_frame, serving
from main import app
from sextant_compute.data.synthetic import HISTORY_END, HISTORY_START, PERSONALITIES

client = TestClient(app)

ENDPOINT = "/api/compute/risk/metrics"
FULL_HISTORY = {"start": HISTORY_START.isoformat(), "end": HISTORY_END.isoformat()}


def post(**body):
    return client.post(ENDPOINT, json={"benchmark": "DEMO-MKT", **FULL_HISTORY, **body})


def metrics(**body):
    response = post(**body)
    assert response.status_code == 200, response.text
    return response.json()


def value(body, metric_id):
    result = body["metrics"][metric_id]
    assert result["status"] == "ok", result
    return result["value"]


# --- Return periods ---

# Three period returns of +10%, -10% and +20% (prices 100 -> 110 -> 99 -> 118.8).
# Sample mean 0.2/3, sample standard deviation sqrt(0.07/3) = 0.152753.
STEP_RETURNS_STD = math.sqrt(0.07 / 3)
STEP_RETURNS_MEAN = 0.2 / 3
PERIOD_CODES = {"weekly": ("W-FRI", 52), "monthly": ("M", 12), "quarterly": ("Q", 4), "yearly": ("Y", 1)}


def stepped_frame(period_code: str, start: str = "2024-01-01") -> pd.DataFrame:
    """Daily closes that move only on the last trading day of each period (then stay flat)."""
    targets = [110.0, 99.0, 118.8]
    days = pd.bdate_range(start, periods=400 * 3)
    periods = days.to_period(period_code)
    first_three = periods.unique()[:3]
    days = days[periods.isin(first_three)]
    periods = days.to_period(period_code)
    closes = []
    for i, p in enumerate(periods):
        k = list(first_three).index(p)
        last_day_of_first = i + 1 == len(days) or periods[i + 1] != p
        closes.append(100.0 if k == 0 and not last_day_of_first else targets[k])
    return price_frame(start, closes)


@pytest.mark.parametrize("period", list(PERIOD_CODES))
def test_volatility_and_sharpe_use_period_returns_annualized_for_the_period(period):
    code, per_year = PERIOD_CODES[period]
    frames = {"STEP": stepped_frame(code)}

    with serving(FixtureAdapter(frames)):
        body = metrics(tickers=["STEP"], benchmark="STEP", start="2024-01-01", end="2027-12-31", period=period)

    assert value(body, "annualized_volatility:STEP") == pytest.approx(STEP_RETURNS_STD * math.sqrt(per_year))
    assert value(body, "sharpe:STEP") == pytest.approx(STEP_RETURNS_MEAN / STEP_RETURNS_STD * math.sqrt(per_year))
    assert body["meta"]["parameters"]["period"] == period


@pytest.mark.parametrize("period", ["weekly", "monthly"])
def test_the_configured_annual_volatility_is_recovered_at_longer_periods(period):
    body = metrics(tickers=["DEMO-A"], period=period)

    assert value(body, "annualized_volatility:DEMO-A") == pytest.approx(PERSONALITIES["DEMO-A"].annual_vol, rel=0.15)
    assert value(body, "beta:DEMO-A") == pytest.approx(PERSONALITIES["DEMO-A"].beta, abs=0.15)


def test_switching_the_period_changes_the_period_statistics_but_not_return_or_drawdown():
    daily = metrics(tickers=["DEMO-B"], period="daily")
    monthly = metrics(tickers=["DEMO-B"], period="monthly")

    for name in ("annualized_volatility", "sharpe", "sortino", "var", "cvar", "beta"):
        assert value(daily, f"{name}:DEMO-B") != pytest.approx(value(monthly, f"{name}:DEMO-B"), rel=1e-6), name
    for name in ("annualized_return", "max_drawdown"):
        assert value(daily, f"{name}:DEMO-B") == value(monthly, f"{name}:DEMO-B")
    # A one-month loss is larger than a one-day loss.
    assert value(monthly, "var:DEMO-B") > value(daily, "var:DEMO-B")


def test_the_period_defaults_to_daily():
    assert metrics(tickers=["DEMO-A"])["meta"]["parameters"]["period"] == "daily"


def test_too_few_period_returns_name_the_period():
    body = metrics(tickers=["DEMO-A"], start="2021-01-01", end="2025-12-31", period="yearly")

    reason = body["metrics"]["var:DEMO-A"]["reason"]
    assert body["metrics"]["var:DEMO-A"]["status"] == "missing_data"
    assert "needs at least 20 yearly returns" in reason and "got 5" in reason
    assert body["metrics"]["annualized_volatility:DEMO-A"]["status"] == "ok"


def test_an_unknown_period_is_a_field_error():
    response = post(tickers=["DEMO-A"], period="hourly")

    assert response.status_code == 422
    assert response.json()["error"]["fields"]["period"] == "Choose one of the listed options."
