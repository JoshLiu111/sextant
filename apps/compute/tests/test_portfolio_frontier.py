import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from data_fixtures import FixtureAdapter, price_frame, serving
from main import app
from sextant_compute.portfolio.api import MAX_HOLDINGS

client = TestClient(app)

ENDPOINT = "/api/compute/portfolio/frontier"
REBALANCING = "/api/compute/portfolio/rebalancing"
RANGE = {"start": "2021-01-01", "end": "2025-12-31"}
DEMO_HOLDINGS = [
    {"ticker": "DEMO-A", "weight": 0.4},
    {"ticker": "DEMO-B", "weight": 0.3},
    {"ticker": "DEMO-E", "weight": 0.3},
]
WHO = ["min_variance", "max_sharpe", "current"]
FUNCTION_BUDGET_SECONDS = 10
"""Well inside a Vercel function's time limit; the optimiser should take a fraction of it."""


def post(**body):
    return client.post(ENDPOINT, json={"benchmark": "DEMO-MKT", **RANGE, **body})


def ok(**body):
    response = post(**body)
    assert response.status_code == 200, response.text
    return response.json()


def value(body, metric_id):
    result = body["metrics"][metric_id]
    assert result["status"] == "ok", (metric_id, result)
    return result["value"]


def frontier_points(body):
    result = body["series"]["frontier"]
    assert result["status"] == "ok", result
    assert result["x_unit"] == "decimal" and result["y_unit"] == "decimal"
    return [(p["x"], p["y"]) for p in result["points"]]


def frontier_weights(body, tickers):
    """Per frontier point: {ticker: weight}, read from the ``frontier_weight:<TICKER>`` series."""
    columns = {t: [p["y"] for p in body["series"][f"frontier_weight:{t}"]["points"]] for t in tickers}
    return [dict(zip(tickers, row)) for row in zip(*columns.values())]


def test_frontier_weights_are_long_only_and_sum_to_one_and_min_variance_is_the_least_volatile():
    body = ok(holdings=DEMO_HOLDINGS)
    tickers = [h["ticker"] for h in DEMO_HOLDINGS]

    assert body["tool"] == "portfolio"
    assert body["source"]["is_demo"] is True
    points = frontier_points(body)
    assert len(points) >= 10
    assert [x for x, _ in points] == sorted(x for x, _ in points)
    rows = frontier_weights(body, tickers)
    assert len(rows) == len(points)
    for row in rows:
        assert all(w >= 0 for w in row.values()), row
        assert sum(row.values()) == pytest.approx(1, abs=1e-9)
    for who in WHO:
        weights = [value(body, f"weight:{t}:{who}") for t in tickers]
        assert all(w >= 0 for w in weights) and sum(weights) == pytest.approx(1, abs=1e-9), who

    min_vol = value(body, "volatility:min_variance")
    assert all(min_vol <= x + 1e-12 for x, _ in points)
    assert min_vol <= value(body, "volatility:current")
    best_sharpe = value(body, "sharpe:max_sharpe")
    assert all(best_sharpe >= y / x - 1e-6 for x, y in points)  # rf = 0
    assert best_sharpe >= value(body, "sharpe:current")
    # The current portfolio is the weights the visitor entered.
    assert [value(body, f"weight:{t}:current") for t in tickers] == pytest.approx([0.4, 0.3, 0.3])


def zigzag_frames(mean_a=0.001, mean_b=0.0005, days=400):
    """Two uncorrelated assets with known moments.

    A's daily return is 0.1% +- 2% (pattern +,-,+,-), B's 0.05% +- 1% (pattern +,+,-,-).
    Over whole 4-day cycles the patterns have zero covariance, so the covariance matrix
    is diagonal: var_A = 4 var_B.
    """
    a = [mean_a + 0.02 * s for s in [1, -1, 1, -1]] * (days // 4)
    b = [mean_b + 0.01 * s for s in [1, 1, -1, -1]] * (days // 4)
    closes = lambda r: list(100 * np.cumprod(1 + np.array([0.0, *r])))  # noqa: E731
    return {"AAA": price_frame("2020-01-01", closes(a)), "BBB": price_frame("2020-01-01", closes(b))}


def test_the_optimal_portfolios_of_two_uncorrelated_assets_match_the_closed_form():
    with serving(FixtureAdapter(zigzag_frames())):
        body = ok(
            holdings=[{"ticker": "AAA", "weight": 0.5}, {"ticker": "BBB", "weight": 0.5}],
            benchmark="AAA",
            start="2020-01-01",
            end="2022-12-31",
        )

    # Min variance: w_A = var_B / (var_A + var_B) = 1 / 5.
    assert value(body, "weight:AAA:min_variance") == pytest.approx(0.2, abs=1e-6)
    assert value(body, "weight:BBB:min_variance") == pytest.approx(0.8, abs=1e-6)
    # Max Sharpe (rf = 0): w ~ mu / var = (0.001 / 4, 0.0005 / 1), i.e. 1/3 and 2/3.
    assert value(body, "weight:AAA:max_sharpe") == pytest.approx(1 / 3, abs=1e-5)
    assert value(body, "weight:BBB:max_sharpe") == pytest.approx(2 / 3, abs=1e-5)
    # Annualized mean and volatility of the 50/50 mix: 252 * 0.00075 and sqrt(252 * (0.25 * 4 + 0.25) * var_B).
    var_b = np.var([0.01, 0.01, -0.01, -0.01] * 100, ddof=1)
    assert value(body, "expected_return:current") == pytest.approx(252 * 0.00075, rel=1e-9)
    assert value(body, "volatility:current") == pytest.approx(np.sqrt(252 * 1.25 * var_b), rel=1e-9)
    # The frontier runs from the min-variance mix up to 100% in the higher-return asset A.
    points = frontier_points(body)
    assert points[0][0] == pytest.approx(value(body, "volatility:min_variance"), rel=1e-9)
    assert points[-1][1] == pytest.approx(252 * 0.001, rel=1e-6)
    assert frontier_weights(body, ["AAA", "BBB"])[-1]["AAA"] == pytest.approx(1, abs=1e-6)


def test_max_sharpe_is_missing_when_no_holding_beats_the_risk_free_rate():
    # Expected returns 252 * 0.05% = 12.6% and 252 * 0.02% = 5.04%, both below a 20% risk-free rate.
    with serving(FixtureAdapter(zigzag_frames(mean_a=0.0005, mean_b=0.0002))):
        body = ok(
            holdings=[{"ticker": "AAA", "weight": 0.5}, {"ticker": "BBB", "weight": 0.5}],
            benchmark="AAA",
            start="2020-01-01",
            end="2022-12-31",
            risk_free_rate=0.2,
        )

    assert body["metrics"]["sharpe:max_sharpe"]["status"] == "missing_data"
    assert "risk-free rate" in body["metrics"]["sharpe:max_sharpe"]["reason"]
    assert value(body, "volatility:min_variance") > 0
    assert frontier_points(body)


def test_a_frontier_needs_at_least_two_holdings():
    response = post(holdings=[{"ticker": "DEMO-A", "weight": 1.0}])

    assert response.status_code == 422, response.text
    assert response.json()["error"]["fields"] == {"holdings": "Add at least two holdings to build a frontier."}


def many_frames(count, days=2520, seed=3):
    """``count`` random correlated assets over about ten years of trading days."""
    rng = np.random.default_rng(seed)
    market = rng.normal(0.0003, 0.01, days)
    frames = {}
    for i in range(count):
        r = 0.0002 * (i % 5) + rng.uniform(0.3, 1.5) * market + rng.normal(0, 0.012, days)
        frames[f"T{i:02d}"] = price_frame("2016-01-04", list(100 * np.cumprod(1 + np.array([0.0, *r]))))
    return frames


def test_both_views_finish_well_within_the_function_time_limit_at_the_maximum_holding_count():
    frames = many_frames(MAX_HOLDINGS)
    holdings = [{"ticker": t, "weight": 1 / MAX_HOLDINGS} for t in frames]
    body = {"holdings": holdings, "benchmark": "T00", "start": "2016-01-01", "end": "2025-12-31"}

    with serving(FixtureAdapter(frames)):
        started = time.perf_counter()
        frontier = client.post(ENDPOINT, json=body)
        frontier_seconds = time.perf_counter() - started
        started = time.perf_counter()
        backtest = client.post(REBALANCING, json={**body, "rule": "drift", "drift_threshold": 0.01})
        backtest_seconds = time.perf_counter() - started

    assert frontier.status_code == 200, frontier.text
    assert backtest.status_code == 200, backtest.text
    assert frontier.json()["metrics"]["sharpe:max_sharpe"]["status"] == "ok"
    assert frontier_seconds < FUNCTION_BUDGET_SECONDS
    assert backtest_seconds < FUNCTION_BUDGET_SECONDS
    rows = frontier_weights(frontier.json(), list(frames))
    assert all(min(row.values()) >= 0 and sum(row.values()) == pytest.approx(1, abs=1e-9) for row in rows)
