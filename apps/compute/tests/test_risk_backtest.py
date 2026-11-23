"""VaR backtest (Kupiec) and GARCH(1,1) volatility on POST /risk/metrics."""

import pytest
from fastapi.testclient import TestClient

from data_fixtures import FixtureAdapter, price_frame, serving
from main import app
from sextant_compute.data.synthetic import GARCH_ALPHA, GARCH_BETA, HISTORY_END, HISTORY_START, PERSONALITIES

client = TestClient(app)

ENDPOINT = "/api/compute/risk/metrics"
FULL_HISTORY = {"start": HISTORY_START.isoformat(), "end": HISTORY_END.isoformat()}


def metrics(**body):
    response = client.post(ENDPOINT, json={"benchmark": "DEMO-MKT", **FULL_HISTORY, **body})
    assert response.status_code == 200, response.text
    return response.json()


def ok(body, metric_id):
    result = body["metrics"][metric_id]
    assert result["status"] == "ok", result
    return result


def test_garch_fit_on_the_demo_benchmark_recovers_the_generators_parameters():
    # DEMO-MKT is a pure GARCH(1,1) series (no jumps, no other factor), so the fit should find it.
    body = metrics(tickers=["DEMO-MKT"])

    garch = ok(body, "garch_volatility:DEMO-MKT")
    details = garch["details"]
    assert details["alpha"] == pytest.approx(GARCH_ALPHA, abs=0.02)
    assert details["beta"] == pytest.approx(GARCH_BETA, abs=0.03)
    assert details["persistence"] == pytest.approx(GARCH_ALPHA + GARCH_BETA, abs=0.02)
    assert details["long_run_volatility"] == pytest.approx(PERSONALITIES["DEMO-MKT"].annual_vol, rel=0.1)
    assert garch["unit"] == "decimal"
    # The value is the latest conditional volatility, annualized.
    assert 0.05 < garch["value"] < 0.5


def test_the_garch_chart_is_the_annualized_conditional_volatility_over_time():
    body = metrics(tickers=["DEMO-A"], start="2021-01-01", end="2025-12-31")

    chart = body["series"]["garch_volatility:DEMO-A"]
    assert chart["status"] == "ok"
    assert chart["x_unit"] == "date" and chart["y_unit"] == "decimal"
    assert chart["points"][0]["x"] == "2021-01-04"
    ys = [p["y"] for p in chart["points"]]
    assert all(y > 0 for y in ys)
    # Clustering: the conditional volatility moves around the configured 14% level.
    assert min(ys) < PERSONALITIES["DEMO-A"].annual_vol < max(ys)


def closes_from(returns, start=100.0):
    closes = [start]
    for r in returns:
        closes.append(closes[-1] * (1 + r))
    return closes


def test_a_series_too_short_for_the_garch_fit_is_missing_data_without_breaking_other_metrics():
    # 100 returns: enough for volatility and a 95% VaR, too few for GARCH(1,1).
    frames = {"SHORT": price_frame("2024-01-01", closes_from([0.01, -0.012, 0.004, -0.02, 0.015] * 20))}

    with serving(FixtureAdapter(frames)):
        body = metrics(tickers=["SHORT"], benchmark="SHORT", start="2024-01-01", end="2024-12-31")

    garch = body["metrics"]["garch_volatility:SHORT"]
    assert garch["status"] == "missing_data"
    assert garch["reason"] == "needs at least 250 daily returns for a GARCH(1,1) fit, got 100"
    assert body["series"]["garch_volatility:SHORT"]["status"] == "missing_data"
    assert ok(body, "annualized_volatility:SHORT")
    assert ok(body, "var:SHORT")
