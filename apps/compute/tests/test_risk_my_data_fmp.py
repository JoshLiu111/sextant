"""Risk & Performance on My data with FMP: ``source: "fmp"``, and the choice between
Tiingo and FMP when the user has both keys.

FMP and Tiingo are ``FakeFmp`` / ``FakeTiingo`` answering from recorded
responses; the data service is the real one (Postgres per-user cache included).
"""

from __future__ import annotations

import psycopg
import pytest

from fmp_fixtures import FakeFmp
from sextant_compute.data.service import make_data_service
from sextant_compute.data.synthetic import SyntheticAdapter
from sextant_compute.keys.api import get_fmp, get_tiingo
from tests.auth_helpers import bearer, sign_in
from tiingo_fixtures import FakeTiingo

ENDPOINT = "/api/compute/risk/metrics"
ALICE_FMP = "afmp111111111111111111111111111aaa"
BOB_FMP = "bfmp222222222222222222222222222bbb"
ALICE_TIINGO = "a1111111111111111111111111111111111111aaa"
TEST_KEY_SECRET = "test-provider-key-secret-not-for-production-0123456789"
BODY = {
    "tickers": ["AAPL", "MSFT"],
    "benchmark": "SPY",
    "start": "2024-01-01",
    "end": "2024-12-31",
    "source": "fmp",
}


@pytest.fixture
def fakes(client, monkeypatch) -> tuple[FakeFmp, FakeTiingo]:
    monkeypatch.setenv("PROVIDER_KEY_SECRET", TEST_KEY_SECRET)
    fmp, tiingo = FakeFmp({ALICE_FMP, BOB_FMP}), FakeTiingo({ALICE_TIINGO})
    fmp_adapter, tiingo_adapter = fmp.adapter(), tiingo.adapter()
    client.app.dependency_overrides[get_fmp] = lambda: fmp_adapter
    client.app.dependency_overrides[get_tiingo] = lambda: tiingo_adapter
    client.app.state.data_service = make_data_service(
        client.app.state.db, {"synthetic": SyntheticAdapter(), "tiingo": tiingo_adapter, "fmp": fmp_adapter}
    )
    return fmp, tiingo


@pytest.fixture
def fmp(fakes) -> FakeFmp:
    return fakes[0]


@pytest.fixture
def tiingo(fakes) -> FakeTiingo:
    return fakes[1]


def user_with_keys(client, name: str, **keys: str) -> dict[str, str]:
    headers = bearer(sign_in(client, f"sub-{name}", email=f"{name}@example.test"))
    for provider, key in keys.items():
        saved = client.put(f"/api/compute/keys/{provider}", json={"key": key}, headers=headers)
        assert saved.status_code == 200, saved.text
    return headers


def risk(client, headers=None, **changes):
    return client.post(ENDPOINT, json={**BODY, **changes}, headers=headers)


def test_my_data_on_fmp_names_fmp_as_the_source(client, fmp):
    alice = user_with_keys(client, "alice", fmp=ALICE_FMP)

    response = risk(client, alice)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source"] == {"id": "fmp", "name": "FMP", "is_demo": False}
    assert body["meta"]["parameters"]["source"] == "fmp"
    assert body["meta"]["data_cutoff"] == "2024-02-12"
    mdd = body["metrics"]["max_drawdown:AAPL"]
    assert mdd["value"] == pytest.approx(0.10)
    assert (mdd["details"]["peak"], mdd["details"]["trough"]) == ("2024-01-16", "2024-01-23")
    assert body["metrics"]["beta:SPY"]["value"] == pytest.approx(1.0)


def test_with_both_keys_the_request_picks_the_provider_and_the_envelope_names_it(client, fmp, tiingo):
    alice = user_with_keys(client, "alice", tiingo=ALICE_TIINGO, fmp=ALICE_FMP)

    on_tiingo = risk(client, alice, source="tiingo")
    on_fmp = risk(client, alice, source="fmp")

    assert on_tiingo.json()["source"]["name"] == "Tiingo"
    assert on_fmp.json()["source"]["name"] == "FMP"
    assert sum(tiingo.price_requests.values()) == 3
    assert sum(fmp.price_requests.values()) == 3


def test_fmp_without_an_fmp_key_is_sent_to_settings_even_with_a_tiingo_key(client, fmp):
    alice = user_with_keys(client, "alice", tiingo=ALICE_TIINGO)

    response = risk(client, alice)

    assert response.status_code == 403
    assert response.json()["error"] == {
        "code": "key_required",
        "message": "My data needs your own FMP key. Add one in Settings.",
        "fields": {},
    }
    assert fmp.price_requests == {}


def test_fmp_prices_fetched_for_one_user_are_never_a_cache_hit_for_another_user_or_a_visitor(client, fmp, db_url):
    alice = user_with_keys(client, "alice", fmp=ALICE_FMP)
    bob = user_with_keys(client, "bob", fmp=BOB_FMP)

    assert risk(client, alice).status_code == 200
    assert risk(client, alice).status_code == 200
    assert fmp.price_requests[(ALICE_FMP, "AAPL")] == 1  # Alice's repeat came from her own cache

    assert risk(client, bob).status_code == 200
    assert fmp.price_requests[(BOB_FMP, "AAPL")] == 1  # Bob missed Alice's entry and used his own key

    assert risk(client).status_code == 403
    assert sum(fmp.price_requests.values()) == 6

    assert len(client.app.state.data_service.shared_cache) == 0
    with psycopg.connect(db_url) as conn:
        rows = conn.execute(
            "SELECT DISTINCT u.email, c.source FROM user_data_cache c JOIN users u ON u.id = c.user_id"
        ).fetchall()
    assert sorted(rows) == [("alice@example.test", "fmp"), ("bob@example.test", "fmp")]


def test_deleting_the_fmp_key_stops_fmp_but_leaves_tiingo_cached_data_alone(client, fmp, tiingo, db_url):
    alice = user_with_keys(client, "alice", tiingo=ALICE_TIINGO, fmp=ALICE_FMP)
    assert risk(client, alice, source="tiingo").status_code == 200
    assert risk(client, alice, source="fmp").status_code == 200

    assert client.delete("/api/compute/keys/fmp", headers=alice).status_code == 204

    assert risk(client, alice, source="fmp").status_code == 403
    assert risk(client, alice, source="tiingo").status_code == 200
    with psycopg.connect(db_url) as conn:
        sources = {s for (s,) in conn.execute("SELECT DISTINCT source FROM user_data_cache")}
    assert sources == {"tiingo"}


def test_a_symbol_outside_the_fmp_plan_only_marks_its_own_metrics_missing(client, fmp):
    alice = user_with_keys(client, "alice", fmp=ALICE_FMP)
    fmp.premium = {"MSFT"}

    response = risk(client, alice)

    assert response.status_code == 200, response.text
    msft = response.json()["metrics"]["annualized_return:MSFT"]
    assert msft["status"] == "missing_data"
    assert msft["reason"] == "FMP has no MSFT, or your FMP plan does not include it."
    assert response.json()["metrics"]["annualized_return:AAPL"]["status"] == "ok"
