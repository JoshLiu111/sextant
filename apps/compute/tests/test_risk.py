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
        ({"tickers": ["DEMO-A"], "confidence": 1.0}, "confidence", "Enter a confidence level between 50% and 99.9%."),
        ({"tickers": ["DEMO-A"], "confidence": 0.4}, "confidence", "Enter a confidence level between 50% and 99.9%."),
        ({"tickers": ["DEMO-A"], "risk_free_rate": 0.5}, "risk_free_rate", "Enter a risk-free rate between -5% and 20%."),
        ({"tickers": ["DEMO-A"], "risk_free_rate": "abc"}, "risk_free_rate", "Enter a number."),
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


# --- Beta, VaR/CVaR, Sharpe, Sortino (#4) ---


@pytest.mark.parametrize("ticker", NO_CRASH)  # an injected crash is idiosyncratic and biases beta
def test_configured_beta_is_recovered_against_the_demo_benchmark(ticker):
    body = metrics(tickers=[ticker])

    assert value(body, f"beta:{ticker}") == pytest.approx(PERSONALITIES[ticker].beta, abs=0.06)
    assert body["metrics"][f"beta:{ticker}"]["unit"] == "ratio"
    assert value(body, "beta:DEMO-MKT") == pytest.approx(1.0)


def closes_from(returns, start=100.0):
    closes = [start]
    for r in returns:
        closes.append(closes[-1] * (1 + r))
    return closes


# 40 daily returns: 36 gains of 1% and four losses of 2%, 4%, 6% and 10%.
TAIL_RETURNS = [0.01] * 18 + [-0.06, -0.02] + [0.01] * 18 + [-0.10, -0.04]


def tail_metrics(**body):
    frames = {"TAIL": price_frame("2024-01-01", closes_from(TAIL_RETURNS))}
    with serving(FixtureAdapter(frames)):
        return metrics(tickers=["TAIL"], benchmark="TAIL", start="2024-01-01", end="2024-12-31", **body)


@pytest.mark.parametrize(
    ("confidence", "var", "cvar"),
    [
        # 95%: the 5% tail of 40 returns is the 2 worst (-10%, -6%).
        (0.95, 0.06, (0.10 + 0.06) / 2),
        # 90%: the 4 worst.
        (0.90, 0.02, (0.10 + 0.06 + 0.04 + 0.02) / 4),
    ],
)
def test_historical_var_and_cvar_are_losses_at_the_tail_of_the_daily_returns(confidence, var, cvar):
    body = tail_metrics(confidence=confidence)

    assert value(body, "var:TAIL") == pytest.approx(var)
    assert value(body, "cvar:TAIL") == pytest.approx(cvar)
    assert body["metrics"]["var:TAIL"]["unit"] == "decimal"
    assert body["meta"]["parameters"]["confidence"] == confidence


def test_var_defaults_to_95_percent_confidence():
    body = tail_metrics()

    assert value(body, "var:TAIL") == pytest.approx(0.06)


def test_too_few_returns_for_the_confidence_level_is_missing_data_for_var_and_cvar_only():
    # A 99% tail needs at least 100 returns; there are 40.
    body = tail_metrics(confidence=0.99)

    for metric_id in ("var:TAIL", "cvar:TAIL"):
        assert body["metrics"][metric_id]["status"] == "missing_data"
        assert "needs at least 100 daily returns" in body["metrics"][metric_id]["reason"]
    assert body["metrics"]["annualized_volatility:TAIL"]["status"] == "ok"
    assert body["metrics"]["beta:TAIL"]["status"] == "ok"


@pytest.mark.parametrize("ticker", list(PERSONALITIES))
def test_cvar_is_at_least_var_and_higher_confidence_gives_a_larger_var(ticker):
    by_confidence = {c: metrics(tickers=[ticker], confidence=c) for c in (0.90, 0.95, 0.99)}

    vars_ = [value(by_confidence[c], f"var:{ticker}") for c in (0.90, 0.95, 0.99)]
    assert vars_[0] < vars_[1] < vars_[2]
    for body in by_confidence.values():
        assert value(body, f"cvar:{ticker}") >= value(body, f"var:{ticker}") > 0


# 252 daily returns alternating +2 basis points (2u) and 0.
U = 0.0001
ZIGZAG = [2 * U if i % 2 == 0 else 0.0 for i in range(YEAR)]


def zigzag_metrics(**body):
    frames = {"ZZ": price_frame("2024-01-01", closes_from(ZIGZAG))}
    with serving(FixtureAdapter(frames)):
        return metrics(tickers=["ZZ"], benchmark="ZZ", start="2024-01-01", end="2025-12-31", **body)


def annual_rate_for_daily(daily):
    return (1 + daily) ** YEAR - 1


def test_sharpe_is_the_annualized_mean_excess_return_over_its_volatility():
    # rf = 0: mean u, sample std u * sqrt(n / (n - 1)), so Sharpe = sqrt(252) * sqrt((n - 1) / n) = sqrt(251).
    assert value(zigzag_metrics(risk_free_rate=0.0), "sharpe:ZZ") == pytest.approx(251**0.5)
    # A risk-free rate of u a day leaves excess returns of +u, -u: mean 0.
    assert value(zigzag_metrics(risk_free_rate=annual_rate_for_daily(U)), "sharpe:ZZ") == pytest.approx(
        0.0, abs=1e-9
    )


def test_sortino_divides_by_the_downside_deviation_below_the_risk_free_rate():
    # Daily rf u/2: excess +1.5u, -0.5u. Mean u/2; downside deviation sqrt(mean(min(e, 0)^2)) = (u/2) / sqrt(2).
    body = zigzag_metrics(risk_free_rate=annual_rate_for_daily(U / 2))

    assert value(body, "sortino:ZZ") == pytest.approx((2 * YEAR) ** 0.5)
    assert value(body, "sharpe:ZZ") == pytest.approx(0.5 * 251**0.5)
    assert body["metrics"]["sortino:ZZ"]["unit"] == "ratio"
    assert body["meta"]["parameters"]["risk_free_rate"] == pytest.approx(annual_rate_for_daily(U / 2))


def test_sortino_is_missing_data_when_no_return_falls_below_the_risk_free_rate():
    body = zigzag_metrics(risk_free_rate=0.0)

    assert body["metrics"]["sortino:ZZ"]["status"] == "missing_data"
    assert "below the risk-free rate" in body["metrics"]["sortino:ZZ"]["reason"]
    assert body["metrics"]["sharpe:ZZ"]["status"] == "ok"


def test_the_risk_free_rate_defaults_to_zero():
    assert value(zigzag_metrics(), "sharpe:ZZ") == pytest.approx(251**0.5)


def test_a_flat_price_has_no_sharpe_or_beta_but_other_metrics_still_return():
    frames = {"FLAT": price_frame("2024-01-01", [100.0] * 30), "OK": price_frame("2024-01-01", closes_from(ZIGZAG))}

    with serving(FixtureAdapter(frames)):
        body = metrics(tickers=["FLAT", "OK"], benchmark="FLAT", start="2024-01-01", end="2025-12-31")

    assert body["metrics"]["sharpe:FLAT"]["status"] == "missing_data"
    assert body["metrics"]["beta:OK"]["status"] == "missing_data"
    assert "benchmark" in body["metrics"]["beta:OK"]["reason"]
    assert value(body, "sharpe:OK") == pytest.approx(251**0.5)
    assert value(body, "var:FLAT") == 0.0
