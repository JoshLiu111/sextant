"""Correlation matrix of daily returns: POST /api/compute/risk/correlation."""

import pytest
from fastapi.testclient import TestClient

from data_fixtures import FixtureAdapter, price_frame, serving
from main import app
from sextant_compute.data.synthetic import HISTORY_END, HISTORY_START, PERSONALITIES

client = TestClient(app)

ENDPOINT = "/api/compute/risk/correlation"
FULL_HISTORY = {"start": HISTORY_START.isoformat(), "end": HISTORY_END.isoformat()}


def correlations(**body):
    response = client.post(ENDPOINT, json={"benchmark": "DEMO-MKT", **FULL_HISTORY, **body})
    assert response.status_code == 200, response.text
    return response.json()


def value(body, a, b):
    result = body["metrics"][f"correlation:{a}:{b}"]
    assert result["status"] == "ok", result
    return result["value"]


def prices_from(returns, start=100.0):
    closes = [start]
    for r in returns:
        closes.append(closes[-1] * (1 + r))
    return closes


def test_the_index_hugger_is_highly_correlated_with_the_benchmark():
    body = correlations(tickers=["DEMO-A", "DEMO-C", "DEMO-E"])

    # The generator's correlation with DEMO-MKT is beta * 0.16 / vol.
    for ticker in ["DEMO-A", "DEMO-C", "DEMO-E"]:
        p = PERSONALITIES[ticker]
        assert value(body, ticker, "DEMO-MKT") == pytest.approx(p.beta * 0.16 / p.annual_vol, abs=0.05)
    assert value(body, "DEMO-C", "DEMO-MKT") > 0.9
    assert body["source"]["is_demo"] is True


def test_the_matrix_is_symmetric_with_ones_on_the_diagonal():
    body = correlations(tickers=["DEMO-A", "DEMO-B", "DEMO-D"])

    symbols = ["DEMO-A", "DEMO-B", "DEMO-D", "DEMO-MKT"]
    assert len(body["metrics"]) == len(symbols) ** 2
    for a in symbols:
        assert value(body, a, a) == pytest.approx(1.0)
        for b in symbols:
            assert value(body, a, b) == pytest.approx(value(body, b, a))
            assert body["metrics"][f"correlation:{a}:{b}"]["unit"] == "ratio"


def test_scaled_returns_correlate_perfectly_and_mirrored_returns_negatively():
    base = [0.01, -0.02, 0.015, 0.0, -0.005, 0.02, -0.01]
    frames = {
        "BASE": price_frame("2024-01-01", prices_from(base)),
        "DOUBLE": price_frame("2024-01-01", prices_from([2 * r for r in base])),
        "MIRROR": price_frame("2024-01-01", prices_from([-r for r in base])),
    }
    with serving(FixtureAdapter(frames)):
        body = correlations(tickers=["DOUBLE", "MIRROR"], benchmark="BASE", start="2024-01-01", end="2024-02-01")

    assert value(body, "DOUBLE", "BASE") == pytest.approx(1.0)
    assert value(body, "MIRROR", "BASE") == pytest.approx(-1.0)
    assert value(body, "MIRROR", "DOUBLE") == pytest.approx(-1.0)


def test_a_flat_ticker_is_missing_data_while_the_other_pairs_still_compute():
    frames = {
        "FLAT": price_frame("2024-01-01", [100.0] * 10),
        "UP": price_frame("2024-01-01", prices_from([0.01, -0.02, 0.03, 0.0, 0.01, -0.01, 0.02, 0.01, -0.03])),
        "BENCH": price_frame("2024-01-01", prices_from([0.02, -0.01, 0.01, 0.01, 0.0, -0.02, 0.01, 0.0, -0.01])),
    }
    with serving(FixtureAdapter(frames)):
        body = correlations(tickers=["FLAT", "UP"], benchmark="BENCH", start="2024-01-01", end="2024-02-01")

    flat = body["metrics"]["correlation:FLAT:BENCH"]
    assert flat["status"] == "missing_data"
    assert "do not vary" in flat["reason"]
    assert -1 <= value(body, "UP", "BENCH") <= 1


def test_an_unknown_ticker_is_reported_on_the_tickers_field():
    response = client.post(ENDPOINT, json={"tickers": ["DEMO-ZZ"], "benchmark": "DEMO-MKT", **FULL_HISTORY})

    assert response.status_code == 422
    assert "Unknown ticker DEMO-ZZ" in response.json()["error"]["fields"]["tickers"]
