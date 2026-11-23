"""Fama-French 3-factor and Carhart 4-factor regressions through POST /risk/metrics."""

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from data_fixtures import FactorFixtureAdapter, FixtureAdapter, price_frame, serving
from main import app
from sextant_compute.data.service import default_adapters
from sextant_compute.data.synthetic import FACTORS, HISTORY_END, HISTORY_START, PERSONALITIES

client = TestClient(app)

ENDPOINT = "/api/compute/risk/metrics"
FULL_HISTORY = {"start": HISTORY_START.isoformat(), "end": HISTORY_END.isoformat()}

FF3 = {"market": "beta", "smb": "smb", "hml": "hml"}
CARHART = {**FF3, "mom": "mom"}
MODELS = {"ff3": FF3, "carhart": CARHART}


def metrics(**body):
    response = client.post(ENDPOINT, json={"benchmark": "DEMO-MKT", **FULL_HISTORY, **body})
    assert response.status_code == 200, response.text
    return response.json()


def ok(body, metric_id):
    result = body["metrics"][metric_id]
    assert result["status"] == "ok", result
    return result


@pytest.mark.parametrize("ticker", ["DEMO-H", "DEMO-I"])
@pytest.mark.parametrize("model", ["ff3", "carhart"])
def test_regressions_recover_the_generators_factor_loadings(model, ticker):
    body = metrics(tickers=[ticker])

    configured = PERSONALITIES[ticker]
    for coefficient, attribute in MODELS[model].items():
        expected = getattr(configured, attribute)
        result = ok(body, f"{model}_{coefficient}:{ticker}")
        assert result["value"] == pytest.approx(expected, abs=0.06), coefficient
        assert result["unit"] == "ratio"
        if expected != 0:
            # A real loading is unmistakable over ten years (FF3 leaves DEMO-I's momentum
            # in the residual, so its t-stats are smaller but still far from zero).
            assert abs(result["details"]["t_stat"]) > 8, coefficient
        else:
            assert abs(result["details"]["t_stat"]) < 3, coefficient


@pytest.mark.parametrize("ticker", ["DEMO-H", "DEMO-I"])
def test_r_squared_is_the_share_of_variance_the_models_factors_explain(ticker):
    body = metrics(tickers=[ticker])

    p = PERSONALITIES[ticker]
    market = PERSONALITIES["DEMO-MKT"].annual_vol ** 2
    size, value_, momentum = (FACTORS[f].annual_vol ** 2 for f in ("SMB", "HML", "MOM"))
    ff3_share = (p.beta**2 * market + p.smb**2 * size + p.hml**2 * value_) / p.annual_vol**2
    carhart_share = ff3_share + p.mom**2 * momentum / p.annual_vol**2
    assert ok(body, f"ff3_r_squared:{ticker}")["value"] == pytest.approx(ff3_share, abs=0.04)
    assert ok(body, f"carhart_r_squared:{ticker}")["value"] == pytest.approx(carhart_share, abs=0.04)


def test_a_ticker_without_factor_tilts_has_insignificant_size_value_and_momentum_loadings():
    body = metrics(tickers=["DEMO-A"])

    assert ok(body, "carhart_market:DEMO-A")["value"] == pytest.approx(PERSONALITIES["DEMO-A"].beta, abs=0.06)
    for coefficient in ("smb", "hml", "mom"):
        result = ok(body, f"carhart_{coefficient}:DEMO-A")
        assert result["value"] == pytest.approx(0.0, abs=0.08), coefficient
        assert abs(result["details"]["t_stat"]) < 3, coefficient


def test_the_market_itself_loads_one_for_one_on_the_market_factor():
    body = metrics(tickers=["DEMO-A"])

    assert ok(body, "ff3_market:DEMO-MKT")["value"] == pytest.approx(1.0, abs=1e-9)
    assert ok(body, "ff3_smb:DEMO-MKT")["value"] == pytest.approx(0.0, abs=1e-9)
    assert ok(body, "ff3_r_squared:DEMO-MKT")["value"] == pytest.approx(1.0, abs=1e-9)


def test_results_carry_t_stats_and_observations_and_are_marked_as_demo_factors():
    body = metrics(tickers=["DEMO-H"], start="2021-01-01", end="2025-12-31")

    alpha = ok(body, "carhart_alpha:DEMO-H")
    assert alpha["unit"] == "decimal"
    assert isinstance(alpha["details"]["t_stat"], float)
    r2 = ok(body, "carhart_r_squared:DEMO-H")
    assert r2["unit"] == "ratio"
    assert r2["details"]["observations"] == 1303  # trading days 2021-01-04..2025-12-31, less the first
    for metric_id, result in body["metrics"].items():
        if metric_id.startswith(("ff3_", "carhart_")):
            assert result["details"]["factor_source"] == "synthetic", metric_id
    assert body["source"]["is_demo"] is True


# Hand-built factors: the ticker's excess return is an exact combination of them plus a tiny
# deterministic wobble, so the regression must give back the combination's coefficients.
def hand_built(days: int):
    index = pd.bdate_range("2024-01-01", periods=days + 1, name="date")
    rng = np.random.default_rng(3)
    factors = pd.DataFrame(
        {
            "Mkt-RF": rng.normal(0, 0.01, days + 1),
            "SMB": rng.normal(0, 0.005, days + 1),
            "HML": rng.normal(0, 0.005, days + 1),
            "MOM": rng.normal(0, 0.007, days + 1),
            "RF": 0.0001,
        },
        index=index,
    )
    wobble = rng.normal(0, 1e-5, days + 1)
    excess = 0.0002 + 1.3 * factors["Mkt-RF"] + 0.4 * factors["SMB"] - 0.7 * factors["HML"] + 0.25 * factors["MOM"]
    returns = excess + factors["RF"] + wobble
    closes = list(100 * (1 + returns.iloc[1:]).cumprod())
    market_closes = list(100 * (1 + factors["Mkt-RF"].iloc[1:] + 0.0001).cumprod())
    frames = {
        "TILT": price_frame("2024-01-01", [100.0, *closes]),
        "MKT": price_frame("2024-01-01", [100.0, *market_closes]),
    }
    return frames, factors.iloc[1:]


def fixture_metrics(days: int, **body):
    frames, factors = hand_built(days)
    with serving(FactorFixtureAdapter(frames, factors)):
        response = client.post(
            ENDPOINT, json={"tickers": ["TILT"], "benchmark": "MKT", "start": "2024-01-01", "end": "2030-01-01", **body}
        )
    assert response.status_code == 200, response.text
    return response.json()


def test_the_regression_returns_the_coefficients_of_an_exact_factor_combination():
    body = fixture_metrics(250)

    assert ok(body, "carhart_market:TILT")["value"] == pytest.approx(1.3, abs=1e-3)
    assert ok(body, "carhart_smb:TILT")["value"] == pytest.approx(0.4, abs=1e-3)
    assert ok(body, "carhart_hml:TILT")["value"] == pytest.approx(-0.7, abs=1e-3)
    assert ok(body, "carhart_mom:TILT")["value"] == pytest.approx(0.25, abs=1e-3)
    assert ok(body, "carhart_alpha:TILT")["value"] == pytest.approx(0.0002 * 252, abs=1e-3)
    assert ok(body, "carhart_r_squared:TILT")["value"] == pytest.approx(1.0, abs=1e-4)
    assert ok(body, "carhart_r_squared:TILT")["details"]["observations"] == 250
    # FF3 leaves MOM in the residual, so it explains less.
    assert ok(body, "ff3_r_squared:TILT")["value"] < 0.999


def test_a_series_too_short_for_the_regression_is_missing_data_without_breaking_other_metrics():
    body = fixture_metrics(20)

    for model, coefficients in MODELS.items():
        for name in [*coefficients, "alpha", "r_squared"]:
            result = body["metrics"][f"{model}_{name}:TILT"]
            assert result["status"] == "missing_data", (model, name)
            assert "needs at least 24 daily returns" in result["reason"]
    assert body["metrics"]["annualized_volatility:TILT"]["status"] == "ok"
    assert body["metrics"]["beta:TILT"]["status"] == "ok"


def test_a_source_without_factor_data_leaves_only_the_factor_metrics_missing():
    frames, _ = hand_built(250)
    with serving(FixtureAdapter(frames)):
        response = client.post(
            ENDPOINT, json={"tickers": ["TILT"], "benchmark": "MKT", "start": "2024-01-01", "end": "2030-01-01"}
        )
    body = response.json()

    assert response.status_code == 200, response.text
    result = body["metrics"]["ff3_smb:TILT"]
    assert result["status"] == "missing_data"
    assert "no factor data" in result["reason"]
    assert body["metrics"]["beta:TILT"]["status"] == "ok"


def test_only_the_synthetic_demo_source_serves_factor_data():
    # ADR 0003: Sextant fetches and caches no real factor data.
    serving_factors = [sid for sid, adapter in default_adapters().items() if hasattr(adapter, "daily_factors")]

    assert serving_factors == ["synthetic"]
