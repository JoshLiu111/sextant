"""Risk & Performance on My data: the user's own Tiingo prices behind ``source: "tiingo"``.

Tiingo is ``FakeTiingo`` (tests/tiingo_fixtures.py) answering from the recorded
responses; the data service is the real one (Postgres per-user cache included).
"""

from __future__ import annotations

import psycopg
import pytest

from sextant_compute.data.service import make_data_service
from sextant_compute.data.synthetic import SyntheticAdapter
from sextant_compute.keys.api import get_tiingo
from tests.auth_helpers import bearer, sign_in
from tiingo_fixtures import FakeTiingo

ENDPOINT = "/api/compute/risk/metrics"
ALICE_KEY = "a1111111111111111111111111111111111111aaa"
BOB_KEY = "b2222222222222222222222222222222222222bbb"
TEST_KEY_SECRET = "test-provider-key-secret-not-for-production-0123456789"
BODY = {
    "tickers": ["AAPL", "MSFT"],
    "benchmark": "SPY",
    "start": "2024-01-01",
    "end": "2024-12-31",
    "source": "tiingo",
}


@pytest.fixture
def tiingo(client, monkeypatch) -> FakeTiingo:
    monkeypatch.setenv("PROVIDER_KEY_SECRET", TEST_KEY_SECRET)
    fake = FakeTiingo({ALICE_KEY, BOB_KEY})
    adapter = fake.adapter()
    client.app.dependency_overrides[get_tiingo] = lambda: adapter
    client.app.state.data_service = make_data_service(
        client.app.state.db, {"synthetic": SyntheticAdapter(), "tiingo": adapter}
    )
    return fake


def user_with_key(client, name: str, key: str | None) -> dict[str, str]:
    headers = bearer(sign_in(client, f"sub-{name}", email=f"{name}@example.test"))
    if key is not None:
        saved = client.put("/api/compute/keys/tiingo", json={"key": key}, headers=headers)
        assert saved.status_code == 200, saved.text
    return headers


@pytest.fixture
def alice(client, tiingo) -> dict[str, str]:
    return user_with_key(client, "alice", ALICE_KEY)


def risk(client, headers=None, **changes):
    return client.post(ENDPOINT, json={**BODY, **changes}, headers=headers)


def test_my_data_names_tiingo_as_the_source_and_is_not_demo_data(client, alice):
    response = risk(client, alice)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source"] == {"id": "tiingo", "name": "Tiingo", "is_demo": False}
    assert body["meta"]["data_cutoff"] == "2024-02-12"
    assert body["meta"]["parameters"]["source"] == "tiingo"
    # AAPL's 4:1 split on 2024-01-30 is not a crash: its max drawdown is the 120 -> 108 dip.
    mdd = body["metrics"]["max_drawdown:AAPL"]
    assert mdd["status"] == "ok"
    assert mdd["value"] == pytest.approx(0.10)
    assert (mdd["details"]["peak"], mdd["details"]["trough"]) == ("2024-01-16", "2024-01-23")
    for metric in ("annualized_volatility", "var", "sharpe", "beta"):
        for ticker in ("AAPL", "MSFT", "SPY"):
            assert body["metrics"][f"{metric}:{ticker}"]["status"] == "ok"
    assert body["metrics"]["beta:SPY"]["value"] == pytest.approx(1.0)


def test_factor_metrics_on_my_data_are_missing_data_not_errors(client, alice):
    """ADR 0003: only the synthetic demo source serves factors."""
    response = risk(client, alice, tickers=["AAPL", "ZZZZ"])

    assert response.status_code == 200, response.text
    metrics = response.json()["metrics"]
    for model in ("ff3", "carhart"):
        for name in (f"{model}_alpha", f"{model}_market", f"{model}_r_squared"):
            assert metrics[f"{name}:AAPL"]["status"] == "missing_data"
            assert metrics[f"{name}:AAPL"]["reason"] == "There is no factor data for Tiingo."
            assert metrics[f"{name}:ZZZZ"]["status"] == "missing_data"
            assert metrics[f"{name}:ZZZZ"]["reason"] == "Tiingo has no ticker ZZZZ."
    assert metrics["carhart_mom:SPY"]["status"] == "missing_data"


def test_tiingo_prices_fetched_for_one_user_are_never_a_cache_hit_for_another_user_or_a_visitor(
    client, tiingo, alice, db_url
):
    bob = user_with_key(client, "bob", BOB_KEY)

    assert risk(client, alice).status_code == 200
    assert risk(client, alice).status_code == 200
    assert tiingo.price_requests[(ALICE_KEY, "aapl")] == 1  # Alice's repeat came from her own cache

    assert risk(client, bob).status_code == 200
    assert tiingo.price_requests[(BOB_KEY, "aapl")] == 1  # Bob missed Alice's entry and used his own key

    anonymous = risk(client)
    assert anonymous.status_code == 403
    assert anonymous.json()["error"]["code"] == "key_required"
    assert sum(tiingo.price_requests.values()) == 6  # 3 tickers each for Alice and Bob, none for the visitor

    assert len(client.app.state.data_service.shared_cache) == 0
    with psycopg.connect(db_url) as conn:
        owners = conn.execute("SELECT DISTINCT u.email FROM user_data_cache c JOIN users u ON u.id = c.user_id")
        assert sorted(email for (email,) in owners) == ["alice@example.test", "bob@example.test"]


def test_a_signed_in_user_without_a_key_is_sent_to_settings(client, tiingo):
    carol = user_with_key(client, "carol", None)

    response = risk(client, carol)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "key_required"
    assert "Settings" in response.json()["error"]["message"]
    assert tiingo.price_requests == {}


def test_deleting_the_key_stops_my_data_even_when_prices_are_cached(client, tiingo, alice, db_url):
    assert risk(client, alice).status_code == 200

    assert client.delete("/api/compute/keys/tiingo", headers=alice).status_code == 204

    assert risk(client, alice).status_code == 403
    with psycopg.connect(db_url) as conn:
        assert conn.execute("SELECT count(*) FROM user_data_cache").fetchone() == (0,)


def test_an_unknown_ticker_gets_a_missing_data_reason_and_the_rest_still_computes(client, alice):
    response = risk(client, alice, tickers=["AAPL", "ZZZZ"])

    assert response.status_code == 200, response.text
    body = response.json()
    for metric in ("annualized_return", "max_drawdown", "var", "beta"):
        result = body["metrics"][f"{metric}:ZZZZ"]
        assert result["status"] == "missing_data"
        assert result["reason"] == "Tiingo has no ticker ZZZZ."
    assert body["series"]["drawdown:ZZZZ"]["status"] == "missing_data"
    assert body["metrics"]["max_drawdown:AAPL"]["status"] == "ok"


def test_a_range_without_benchmark_prices_is_shown_next_to_the_benchmark_input(client, alice):
    response = risk(client, alice, tickers=["AAPL"], start="2023-01-01", end="2023-12-31")

    assert response.status_code == 422
    assert response.json()["error"]["fields"]["benchmark"] == "No Tiingo prices for SPY between 2023-01-01 and 2023-12-31."


def test_an_unknown_benchmark_is_shown_next_to_the_benchmark_input(client, alice):
    response = risk(client, alice, benchmark="QQQQ")

    assert response.status_code == 422
    assert response.json()["error"]["fields"] == {"benchmark": "Tiingo has no ticker QQQQ."}


@pytest.mark.parametrize("status", [503, 429])
def test_a_tiingo_outage_or_rate_limit_says_the_source_is_temporarily_unavailable(client, tiingo, alice, status):
    tiingo.status = status

    response = risk(client, alice)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "source_unavailable"
    assert "temporarily unavailable" in response.json()["error"]["message"]


def test_a_key_tiingo_stops_accepting_asks_the_user_to_replace_it(client, tiingo, alice):
    tiingo.valid = set()

    response = risk(client, alice)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "key_required"
    assert "Replace it in Settings" in response.json()["error"]["message"]
    assert ALICE_KEY not in response.text
