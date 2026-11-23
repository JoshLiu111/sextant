"""The Risk & Performance response stays well under Vercel's 4.5 MB response limit.

The daily chart series (drawdown, GARCH volatility, rolling curves) are thinned
on the server to a bounded number of points; every metric is still computed on
the full daily data.
"""

from __future__ import annotations

import httpx
import numpy as np
import pytest

from sextant_compute.data.service import make_data_service
from sextant_compute.data.synthetic import SyntheticAdapter
from sextant_compute.data.tiingo import TiingoAdapter
from sextant_compute.keys.api import get_tiingo
from tests.test_risk_my_data import ALICE_KEY, TEST_KEY_SECRET, user_with_key

ENDPOINT = "/api/compute/risk/metrics"
BUDGET = 2_000_000  # bytes; Vercel's limit is 4.5 MB
MAX_POINTS = 600
DAILY_SERIES = ("drawdown", "garch_volatility", "rolling_volatility", "rolling_sharpe", "rolling_beta")
DEMO_TICKERS = [f"DEMO-{c}" for c in "ABCDEFGHI"]
REAL_TICKERS = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "LLY", "NFLX", "AVGO", "JPM"]
DAYS = 12_000  # weekdays from 1980-01-01, about 46 years
CRASH = 6_000


def _day(i: int) -> str:
    return str(np.busday_offset("1980-01-01", i, roll="forward"))


def _long_history(request: httpx.Request) -> httpx.Response:
    """Any ticker: a seeded random walk on every weekday from 1980 to 2026, with one
    deep single-day crash."""
    ticker = request.url.path.strip("/").split("/")[2]
    days = np.busday_offset("1980-01-01", np.arange(DAYS), roll="forward").astype(str)
    rng = np.random.default_rng(sum(map(ord, ticker)))
    returns = rng.normal(0.0004, 0.012, DAYS)
    returns[CRASH] = -0.6
    closes = 50 * np.cumprod(1 + returns)
    rows = [
        {"date": f"{d}T00:00:00.000Z", "open": c, "high": c, "low": c, "close": c, "volume": 1e6, "divCash": 0.0}
        for d, c in zip(days, closes.tolist(), strict=True)
    ]
    return httpx.Response(200, json=rows)


@pytest.fixture
def long_tiingo(client, monkeypatch) -> None:
    monkeypatch.setenv("PROVIDER_KEY_SECRET", TEST_KEY_SECRET)
    transport = httpx.MockTransport(
        lambda r: httpx.Response(200, json={"message": "You successfully sent a request"})
        if r.url.path == "/api/test"
        else _long_history(r)
    )
    adapter = TiingoAdapter(base_url="https://tiingo.test", transport=transport, sleep=lambda _s: None)
    client.app.dependency_overrides[get_tiingo] = lambda: adapter
    client.app.state.data_service = make_data_service(
        client.app.state.db, {"synthetic": SyntheticAdapter(), "tiingo": adapter}
    )


def _assert_thinned(body: dict, tickers: list[str]) -> None:
    for ticker in tickers:
        for name in DAILY_SERIES:
            chart = body["series"][f"{name}:{ticker}"]
            assert chart["status"] == "ok", (name, ticker, chart["reason"])
            assert 2 <= len(chart["points"]) <= MAX_POINTS, (name, ticker, len(chart["points"]))


def test_the_largest_demo_request_fits_the_budget(client):
    body = {"tickers": DEMO_TICKERS, "benchmark": "DEMO-MKT", "start": "2016-01-01", "end": "2025-12-31"}

    response = client.post(ENDPOINT, json=body)

    assert response.status_code == 200, response.text
    assert len(response.content) < BUDGET
    _assert_thinned(response.json(), [*DEMO_TICKERS, "DEMO-MKT"])


def test_the_largest_my_data_request_fits_the_budget(client, long_tiingo):
    alice = user_with_key(client, "alice", ALICE_KEY)
    body = {"tickers": REAL_TICKERS, "benchmark": "SPY", "start": "1980-01-01", "end": "2026-11-20", "source": "tiingo"}

    response = client.post(ENDPOINT, json=body, headers=alice)

    assert response.status_code == 200, response.text
    assert len(response.content) < BUDGET
    _assert_thinned(response.json(), [*REAL_TICKERS, "SPY"])


def test_thinned_charts_keep_the_range_and_the_trough_and_metrics_use_every_day(client, long_tiingo):
    alice = user_with_key(client, "alice", ALICE_KEY)
    body = {"tickers": ["AAPL"], "benchmark": "SPY", "start": "1980-01-01", "end": "2026-11-20", "source": "tiingo"}

    out = client.post(ENDPOINT, json=body, headers=alice).json()

    mdd = out["metrics"]["max_drawdown:AAPL"]
    assert mdd["value"] > 0.6  # at least the crash
    points = out["series"]["drawdown:AAPL"]["points"]
    assert len(points) <= MAX_POINTS
    assert (points[0]["x"], points[-1]["x"]) == (_day(0), _day(DAYS - 1))
    # The chart still reaches the max drawdown, on the trough's own day.
    deepest = min(points, key=lambda p: p["y"])
    assert deepest["x"] == mdd["details"]["trough"]
    assert -deepest["y"] == pytest.approx(mdd["value"], abs=1e-5)
    xs = [p["x"] for p in points]
    assert xs == sorted(xs) and len(set(xs)) == len(xs)
