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


# 750 returns between closes of exactly 100 and 99, so every ordinary loss is the
# same float (-1%). In the 500 tested days, ten of the 99 closes are 95 instead
# (a -5% day), 50 days apart: never more than 5 in a 250-day window, so the 95%
# historical VaR (the 13th worst of 250) is always the ordinary 1% loss and
# exactly those ten days breach it.
BIG_LOSS_DAYS = range(255, 751, 50)
METHODS = ("backtest_var", "backtest_parametric_var", "backtest_cornish_fisher_var")


def breach_closes():
    closes = [100.0 if i % 2 == 0 else 99.0 for i in range(751)]
    for i in BIG_LOSS_DAYS:
        closes[i] = 95.0
    return closes


def backtest_metrics(**body):
    frames = {"BRK": price_frame("2022-01-03", breach_closes())}
    with serving(FixtureAdapter(frames)):
        return metrics(tickers=["BRK"], benchmark="BRK", start="2022-01-03", end="2025-12-31", **body)


def test_historical_var_backtest_counts_breaches_and_reports_kupiec():
    body = backtest_metrics(confidence=0.95)

    result = ok(body, "backtest_var:BRK")
    assert result["value"] == 10
    assert result["unit"] == "count"
    d = result["details"]
    assert d["window"] == 250
    assert d["observations"] == 500
    assert d["expected_breaches"] == pytest.approx(25.0)
    assert d["breach_rate"] == pytest.approx(0.02)
    # LR = -2 ln[(0.95^490 0.05^10) / (0.98^490 0.02^10)], chi2(1) tail.
    assert d["kupiec_statistic"] == pytest.approx(12.142961, rel=1e-6)
    assert d["p_value"] == pytest.approx(0.00049273, rel=1e-4)
    assert d["significance"] == pytest.approx(0.05)
    # Too few breaches is a rejection too: the VaR is too conservative.
    assert d["result"] == "reject"


def test_every_var_method_is_backtested():
    body = backtest_metrics()

    for method in METHODS:
        d = ok(body, f"{method}:BRK")["details"]
        assert d["observations"] == 500
        assert d["result"] in ("accept", "reject")
        assert 0 <= d["p_value"] <= 1


@pytest.mark.parametrize("confidence", [0.95, 0.99])
def test_var_models_hold_up_on_the_normal_shocked_demo_benchmark(confidence):
    body = metrics(tickers=["DEMO-MKT"], confidence=confidence)

    for method in METHODS:
        d = ok(body, f"{method}:DEMO-MKT")["details"]
        assert d["expected_breaches"] == pytest.approx(d["observations"] * (1 - confidence))
        assert d["result"] == "accept", (method, d)


def test_normal_var_is_rejected_for_the_fat_tailed_demo_ticker():
    # DEMO-F's jumps make its returns very fat-tailed: a normal 95% VaR sits too far out and is breached too rarely.
    body = metrics(tickers=["DEMO-F"], confidence=0.95)

    parametric = ok(body, "backtest_parametric_var:DEMO-F")
    assert parametric["value"] < parametric["details"]["expected_breaches"]
    assert parametric["details"]["result"] == "reject"
    assert ok(body, "backtest_var:DEMO-F")["details"]["result"] == "accept"


def test_a_series_too_short_to_backtest_is_missing_data_for_the_backtests_only():
    frames = {"SHORT": price_frame("2024-01-01", closes_from([0.01, -0.012, 0.004, -0.02, 0.015] * 20))}

    with serving(FixtureAdapter(frames)):
        body = metrics(tickers=["SHORT"], benchmark="SHORT", start="2024-01-01", end="2024-12-31")

    for method in METHODS:
        result = body["metrics"][f"{method}:SHORT"]
        assert result["status"] == "missing_data"
        assert result["reason"] == "needs at least 251 daily returns to backtest a 250-day VaR, got 100"
    assert ok(body, "parametric_var:SHORT")


def test_a_historical_var_too_far_in_the_tail_for_the_window_is_missing_data_for_that_backtest_only():
    body = backtest_metrics(confidence=0.999)

    result = body["metrics"]["backtest_var:BRK"]
    assert result["status"] == "missing_data"
    assert "needs at least 1000 returns per window" in result["reason"]
    assert ok(body, "backtest_parametric_var:BRK")
