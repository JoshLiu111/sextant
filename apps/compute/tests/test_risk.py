from datetime import date, timedelta

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from data_fixtures import DownAdapter, FixtureAdapter, price_frame, serving
from main import app
from sextant_compute.data.synthetic import HISTORY_END, HISTORY_START, PERSONALITIES

client = TestClient(app)

ENDPOINT = "/api/compute/risk/metrics"
FULL_HISTORY = {"start": HISTORY_START.isoformat(), "end": HISTORY_END.isoformat()}
NO_CRASH = [t for t, p in PERSONALITIES.items() if p.crash is None and t != "DEMO-MKT"]


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


@pytest.mark.parametrize("ticker", NO_CRASH)
def test_configured_annual_volatility_is_recovered(ticker):
    body = metrics(tickers=[ticker])

    configured = PERSONALITIES[ticker].annual_vol
    assert value(body, f"annualized_volatility:{ticker}") == pytest.approx(configured, rel=0.06)
    assert body["metrics"][f"annualized_volatility:{ticker}"]["unit"] == "decimal"


def test_benchmark_gets_its_own_metrics():
    body = metrics(tickers=["DEMO-A"])

    assert value(body, "annualized_volatility:DEMO-MKT") == pytest.approx(
        PERSONALITIES["DEMO-MKT"].annual_vol, rel=0.06
    )


def test_result_is_flagged_as_demo_data_with_its_cutoff():
    body = metrics(tickers=["DEMO-A"], start="2021-01-01", end="2025-12-31")

    assert body["tool"] == "risk"
    assert body["source"]["is_demo"] is True
    assert body["source"]["id"] == "synthetic"
    assert body["meta"]["data_cutoff"] == "2025-12-31"
    assert body["meta"]["parameters"]["tickers"] == ["DEMO-A"]


CRASH = PERSONALITIES["DEMO-D"].crash
CRASH_DAYS = pd.bdate_range(CRASH.start, periods=CRASH.days)
PRE_CRASH_CLOSE = (pd.Timestamp(CRASH.start) - pd.offsets.BDay(1)).date()
CRASH_BOTTOM = CRASH_DAYS[-1].date()


def test_injected_crash_is_exactly_the_max_drawdown_over_the_crash_window():
    body = metrics(tickers=["DEMO-D"], start=PRE_CRASH_CLOSE.isoformat(), end=CRASH_BOTTOM.isoformat())

    mdd = body["metrics"]["max_drawdown:DEMO-D"]
    assert value(body, "max_drawdown:DEMO-D") == pytest.approx(CRASH.depth, abs=1e-3)
    assert mdd["details"]["peak"] == PRE_CRASH_CLOSE.isoformat()
    assert mdd["details"]["trough"] == CRASH_BOTTOM.isoformat()
    assert mdd["details"]["recovery"] is None


def test_over_the_default_range_the_crash_is_the_max_drawdown():
    body = metrics(tickers=["DEMO-D"], start="2021-01-01", end="2025-12-31")

    mdd = body["metrics"]["max_drawdown:DEMO-D"]
    assert value(body, "max_drawdown:DEMO-D") >= CRASH.depth - 1e-3
    assert date.fromisoformat(mdd["details"]["peak"]) <= PRE_CRASH_CLOSE
    assert mdd["details"]["trough"] == CRASH_BOTTOM.isoformat()
    # The generator climbs back to the pre-crash level over `recovery_days`.
    recovered_by = (pd.Timestamp(CRASH_BOTTOM) + pd.offsets.BDay(CRASH.recovery_days + 60)).date()
    assert date.fromisoformat(mdd["details"]["recovery"]) <= recovered_by


def test_underwater_chart_is_zero_at_highs_and_bottoms_at_the_max_drawdown():
    body = metrics(tickers=["DEMO-D"], start="2021-01-01", end="2025-12-31")

    chart = body["series"]["drawdown:DEMO-D"]
    assert chart["status"] == "ok"
    assert chart["x_unit"] == "date" and chart["y_unit"] == "decimal"
    points = chart["points"]
    assert points[0] == {"x": "2021-01-01", "y": 0.0}
    assert all(p["y"] <= 0 for p in points)
    lowest = min(points, key=lambda p: p["y"])
    assert lowest["x"] == CRASH_BOTTOM.isoformat()
    assert lowest["y"] == pytest.approx(-value(body, "max_drawdown:DEMO-D"))


# Hand-built prices: 253 closes = 252 daily returns = exactly one trading year.
YEAR = 252


def test_annualized_return_compounds_price_growth_and_reinvested_dividends():
    growth = price_frame("2024-01-01", [100 * 1.1 ** (i / YEAR) for i in range(YEAR + 1)])
    flat_with_dividend = price_frame("2024-01-01", [100.0] * (YEAR + 1), dividends={100: 5.0})
    two_years = price_frame("2024-01-01", [100 * 1.21 ** (i / (2 * YEAR)) for i in range(2 * YEAR + 1)])
    frames = {"GROW": growth, "DIV": flat_with_dividend, "TWO": two_years, "BENCH": growth}

    with serving(FixtureAdapter(frames)):
        body = metrics(tickers=["GROW", "DIV", "TWO"], benchmark="BENCH", start="2024-01-01", end="2026-12-31")

    assert value(body, "annualized_return:GROW") == pytest.approx(0.10, abs=1e-9)
    assert value(body, "annualized_return:DIV") == pytest.approx(0.05, abs=1e-9)
    assert value(body, "annualized_return:TWO") == pytest.approx(0.10, abs=1e-9)
    assert body["source"] == {"id": "fixture", "name": "Test fixture", "is_demo": False}


def test_annualized_volatility_of_alternating_one_percent_moves():
    closes = [100.0]
    for i in range(YEAR):
        closes.append(closes[-1] * (1.01 if i % 2 == 0 else 0.99))
    frames = {"ZIG": price_frame("2024-01-01", closes)}

    with serving(FixtureAdapter(frames)):
        body = metrics(tickers=["ZIG"], benchmark="ZIG", start="2024-01-01", end="2025-12-31")

    # Returns are +1%, -1%, ... (mean 0): sample std = 0.01 * sqrt(n / (n - 1)).
    assert value(body, "annualized_volatility:ZIG") == pytest.approx(0.01 * (YEAR / (YEAR - 1)) ** 0.5 * YEAR**0.5)


def test_too_little_data_is_missing_data_for_that_ticker_only():
    frames = {"ONE": price_frame("2024-01-01", [100.0]), "OK": price_frame("2024-01-01", [100.0, 101.0, 99.0])}

    with serving(FixtureAdapter(frames)):
        body = metrics(tickers=["ONE", "OK"], benchmark="OK", start="2024-01-01", end="2024-12-31")

    for metric_id in ("annualized_return:ONE", "annualized_volatility:ONE", "max_drawdown:ONE"):
        assert body["metrics"][metric_id]["status"] == "missing_data"
        assert "needs at least" in body["metrics"][metric_id]["reason"]
    assert body["series"]["drawdown:ONE"]["status"] == "missing_data"
    assert value(body, "max_drawdown:OK") == pytest.approx(1 - 99 / 101)


def test_a_repeated_identical_request_is_served_from_the_shared_cache():
    adapter = FixtureAdapter({"AAA": price_frame("2024-01-01", [100.0, 103.0, 98.0, 104.0])})

    with serving(adapter) as service:
        first = metrics(tickers=["AAA"], benchmark="AAA", start="2024-01-01", end="2024-12-31")
        second = metrics(tickers=["aaa"], benchmark="AAA", start="2024-01-01", end="2024-12-31")

    assert adapter.calls == 1
    assert second["metrics"] == first["metrics"]
    assert second["series"] == first["series"]
    assert second["calculation_id"] != first["calculation_id"]


def test_the_demo_data_is_cached_in_the_shared_cache():
    from sextant_compute.data.synthetic import SyntheticAdapter

    with serving(SyntheticAdapter()) as service:
        metrics(tickers=["DEMO-A"], start="2024-01-01", end="2024-12-31")
        assert len(service.shared_cache) == 1
        metrics(tickers=["DEMO-A"], start="2024-01-01", end="2024-12-31")
        assert len(service.shared_cache) == 1


def test_unknown_ticker_is_reported_on_the_field_that_named_it():
    response = post(tickers=["DEMO-A", "demo-zz"], benchmark="NOPE")

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "no_such_data"
    assert "DEMO-ZZ" in error["fields"]["tickers"]
    assert "NOPE" not in error["fields"]["tickers"]
    assert "NOPE" in error["fields"]["benchmark"]


def test_reversed_date_range_is_a_validation_error_on_the_end_date():
    response = post(tickers=["DEMO-A"], start="2024-06-01", end="2024-01-01")

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["fields"] == {"end": "End date must be after the start date."}


def test_a_range_outside_the_demo_history_says_what_is_covered():
    response = post(tickers=["DEMO-A"], start="2030-01-01", end="2030-12-31")

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "no_such_data"
    assert "2016-01-04 to 2025-12-31" in error["fields"]["start"]


@pytest.mark.parametrize(
    ("body", "field", "message"),
    [
        ({"tickers": []}, "tickers", "Enter at least one ticker."),
        ({"tickers": ["DEMO-A", "demo-a"]}, "tickers", "Each ticker can only be listed once."),
        ({"tickers": [f"DEMO-{i}" for i in range(11)]}, "tickers", "Enter at most 10 tickers."),
        ({"tickers": ["DEMO-A"], "start": "last week"}, "start", "Enter a date as YYYY-MM-DD."),
        ({"tickers": ["DEMO-A"], "benchmark": " "}, "benchmark", "Enter a ticker."),
    ],
)
def test_invalid_inputs_get_field_messages(body, field, message):
    response = post(**body)

    assert response.status_code == 422
    assert response.json()["error"]["fields"][field] == message


def test_tickers_are_normalized_to_upper_case():
    body = metrics(tickers=[" demo-a "], benchmark="demo-mkt", start="2024-01-01", end="2024-12-31")

    assert body["meta"]["parameters"]["tickers"] == ["DEMO-A"]
    assert value(body, "annualized_volatility:DEMO-A") > 0


def test_a_provider_outage_is_reported_as_source_unavailable():
    with serving(DownAdapter()):
        response = post(tickers=["DEMO-A"])

    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "source_unavailable"
    assert "temporarily unavailable" in error["message"]
    assert "retry" in error["message"].lower()
