"""Valuation on My data: the share price is the latest close from the user's own provider.

Statements still come from EDGAR (the tiny company from test_valuation.py, served
as MSFT: $120 intrinsic value per share, 10M shares). Tiingo is ``FakeTiingo``,
whose MSFT closes at 402 on its last day (2024-02-12); FMP is ``FakeFmp``, same close. The data service is the
real one, Postgres per-user cache included.
"""

from __future__ import annotations

import pytest

from fmp_fixtures import FakeFmp
from sextant_compute.data.service import make_data_service
from sextant_compute.keys.api import get_fmp, get_tiingo
from tests.auth_helpers import bearer, sign_in
from tests.edgar_fixtures import edgar_adapter, edgar_transport
from tests.test_valuation import M, tiny_facts
from tiingo_fixtures import FakeTiingo

PATH = "/api/compute/valuation/dcf"
ALICE_KEY = "a1111111111111111111111111111111111111aaa"
TEST_KEY_SECRET = "test-provider-key-secret-not-for-production-0123456789"
HAND_COMPUTED = {"growth_rate": 0.10, "terminal_growth": 0.0, "discount_rate": 0.10, "forecast_years": 2}


@pytest.fixture
def tiingo(client, monkeypatch) -> FakeTiingo:
    monkeypatch.setenv("PROVIDER_KEY_SECRET", TEST_KEY_SECRET)
    fake = FakeTiingo({ALICE_KEY})
    adapter = fake.adapter()
    client.app.dependency_overrides[get_tiingo] = lambda: adapter
    edgar = edgar_adapter(edgar_transport(facts_override={"MSFT": tiny_facts()}))
    client.app.state.data_service = make_data_service(client.app.state.db, {"sec_edgar": edgar, "tiingo": adapter})
    return fake


def user(client, name: str, key: str | None) -> dict[str, str]:
    headers = bearer(sign_in(client, f"sub-{name}", email=f"{name}@example.test"))
    if key is not None:
        saved = client.put("/api/compute/keys/tiingo", json={"key": key}, headers=headers)
        assert saved.status_code == 200, saved.text
    return headers


@pytest.fixture
def alice(client, tiingo) -> dict[str, str]:
    return user(client, "alice", ALICE_KEY)


def value(client, headers=None, **changes):
    return client.post(PATH, json={"ticker": "MSFT", **HAND_COMPUTED, "price_source": "tiingo", **changes}, headers=headers)


def test_my_data_fills_the_price_with_the_latest_close_from_the_users_provider(client, alice):
    response = value(client, alice)

    assert response.status_code == 200, response.text
    body = response.json()
    price = body["metrics"]["share_price"]
    assert price["value"] == 402
    assert price["details"] == {"basis": "latest_close", "date": "2024-02-12"}
    assert body["price_source"] == {"id": "tiingo", "name": "Tiingo", "is_demo": False}
    assert body["source"]["id"] == "sec_edgar"
    assert body["metrics"]["market_cap"]["value"] == 402 * 10 * M
    # Intrinsic $120 against a $402 price: (120 - 402) / 120.
    assert body["metrics"]["margin_of_safety"]["value"] == pytest.approx(-2.35)


def test_the_latest_close_also_weights_equity_at_market_value(client, alice):
    body = value(client, alice, discount_rate=None).json()

    # E = 402 x 10M = 4,020M, D = 50M.
    assert body["metrics"]["debt_weight"]["value"] == pytest.approx(50 / 4070)


def test_a_typed_in_price_wins_over_the_provider_and_spends_no_quota(client, tiingo, alice):
    body = value(client, alice, share_price=90).json()

    assert body["metrics"]["share_price"]["value"] == 90
    assert body["metrics"]["share_price"]["details"] == {"basis": "entered"}
    assert body["price_source"] is None
    assert tiingo.price_requests == {}


def test_the_latest_close_is_cached_for_the_user(client, tiingo, alice):
    assert value(client, alice).status_code == 200
    assert value(client, alice).status_code == 200

    assert tiingo.price_requests[(ALICE_KEY, "msft")] == 1


def test_a_ticker_the_provider_does_not_know_only_misses_the_market_comparison(client, tiingo, alice):
    edgar = edgar_adapter(edgar_transport(facts_override={"JPM": tiny_facts()}))
    client.app.state.data_service = make_data_service(
        client.app.state.db, {"sec_edgar": edgar, "tiingo": tiingo.adapter()}
    )

    body = value(client, alice, ticker="JPM").json()

    for metric_id in ("share_price", "market_cap", "margin_of_safety"):
        assert body["metrics"][metric_id]["status"] == "missing_data"
        assert body["metrics"][metric_id]["reason"] == "Tiingo has no ticker JPM."
    assert body["metrics"]["intrinsic_value_per_share"]["value"] == pytest.approx(120)


def test_my_data_without_a_key_is_sent_to_settings(client, tiingo):
    for headers in (None, user(client, "carol", None)):
        response = value(client, headers)

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "key_required"
    assert tiingo.price_requests == {}


ALICE_FMP = "afmp111111111111111111111111111aaa"


@pytest.fixture
def fmp(client, monkeypatch) -> FakeFmp:
    monkeypatch.setenv("PROVIDER_KEY_SECRET", TEST_KEY_SECRET)
    fake = FakeFmp({ALICE_FMP})
    adapter = fake.adapter()
    client.app.dependency_overrides[get_fmp] = lambda: adapter
    edgar = edgar_adapter(edgar_transport(facts_override={"MSFT": tiny_facts(), "JPM": tiny_facts()}))
    client.app.state.data_service = make_data_service(client.app.state.db, {"sec_edgar": edgar, "fmp": adapter})
    return fake


def fmp_user(client) -> dict[str, str]:
    headers = bearer(sign_in(client, "sub-dora", email="dora@example.test"))
    saved = client.put("/api/compute/keys/fmp", json={"key": ALICE_FMP}, headers=headers)
    assert saved.status_code == 200, saved.text
    return headers


def test_my_data_on_fmp_fills_the_price_with_fmps_latest_close(client, fmp):
    dora = fmp_user(client)

    body = value(client, dora, price_source="fmp").json()

    assert body["metrics"]["share_price"]["value"] == 402
    assert body["metrics"]["share_price"]["details"] == {"basis": "latest_close", "date": "2024-02-12"}
    assert body["price_source"] == {"id": "fmp", "name": "FMP", "is_demo": False}
    assert body["metrics"]["margin_of_safety"]["value"] == pytest.approx(-2.35)
    assert fmp.price_requests[(ALICE_FMP, "MSFT")] == 1


def test_a_ticker_fmp_has_no_prices_for_only_misses_the_market_comparison(client, fmp):
    body = value(client, fmp_user(client), ticker="JPM", price_source="fmp").json()

    assert body["metrics"]["margin_of_safety"]["reason"] == "FMP has no JPM, or your FMP plan does not include it."
    assert body["metrics"]["intrinsic_value_per_share"]["value"] == pytest.approx(120)
